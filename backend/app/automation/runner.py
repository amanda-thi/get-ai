"""Siklus hidup job automation: buat, jalankan, progress, retry, cancel, timeout.

Prinsip:
* **Lock DB**: satu job aktif per config dijaga unique partial index
  `uq_automation_jobs_active`. Pembuatan job yang bertabrakan mengembalikan `None`.
* **Idempotensi**: `idempotency_key` unik per slot/eksekusi.
* **Retry**: exponential backoff (`retry_backoff_seconds * 2^(n-1)`) sampai `max_attempts`.
* **Timeout & cancel**: kooperatif — handler memanggil `ctx.check()` di antara langkah.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..config import Settings
from ..db import SupabaseClient, SupabaseError, is_conflict_error
from .errors import JobCancelled, JobError, JobTimeout
from .notifications import create_notification, maybe_email_admins
from .registry import next_run_at

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "partially_completed", "failed", "cancelled")
_JOB_SELECT = "*"
_CONFIG_SELECT = "*"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def get_config(db: SupabaseClient, config_id: str) -> dict | None:
    rows = db.select("automation_configs", {"select": _CONFIG_SELECT, "id": f"eq.{config_id}", "limit": "1"})
    return rows[0] if rows else None


def get_config_by_type(db: SupabaseClient, automation_type: str) -> dict | None:
    rows = db.select(
        "automation_configs",
        {"select": _CONFIG_SELECT, "automation_type": f"eq.{automation_type}", "limit": "1"},
    )
    return rows[0] if rows else None


def get_job(db: SupabaseClient, job_id: str) -> dict | None:
    rows = db.select("automation_jobs", {"select": _JOB_SELECT, "id": f"eq.{job_id}", "limit": "1"})
    return rows[0] if rows else None


def list_enabled_configs(db: SupabaseClient) -> list[dict]:
    """Konfigurasi yang aktif (untuk dimuat scheduler saat startup)."""
    return db.select(
        "automation_configs",
        {"select": _CONFIG_SELECT, "is_enabled": "eq.true", "order": "automation_name.asc"},
    )


def create_job(
    db: SupabaseClient,
    config: dict,
    *,
    trigger_type: str,
    triggered_by: str | None = None,
    parent_job_id: str | None = None,
    idempotency_key: str | None = None,
    attempt: int = 1,
) -> dict | None:
    """Buat baris job 'queued'. None bila sudah ada job aktif untuk config ini."""
    retry_attempts = max(0, int(config.get("retry_max_attempts") or 0))
    key = idempotency_key or f"{config['automation_type']}:{trigger_type}:{uuid4()}"
    row = {
        "automation_config_id": config.get("id"),
        "job_name": config.get("automation_name") or config.get("automation_type"),
        "job_type": config.get("automation_type"),
        "trigger_type": trigger_type,
        "status": "queued",
        "progress": 0,
        "attempt": attempt,
        "max_attempts": 1 + retry_attempts,
        "idempotency_key": key,
        "parent_job_id": parent_job_id,
        "triggered_by": triggered_by,
    }
    try:
        rows = db.insert("automation_jobs", row)
    except SupabaseError as e:
        if is_conflict_error(e):
            log.info("job untuk '%s' sedang aktif atau slot sudah dipakai; dilewati", config.get("automation_type"))
            return None
        raise
    return rows[0] if rows else row


@dataclass
class JobContext:
    """Konteks yang diberikan ke handler: progress, log, notifikasi, pembatalan."""

    db: SupabaseClient
    settings: Settings
    config: dict
    job: dict
    deadline: float
    _cancelled: bool = False

    def log(self, level: str, message: str, metadata: dict | None = None) -> None:
        level = level if level in ("debug", "info", "warning", "error") else "info"
        try:
            self.db.insert(
                "automation_job_logs",
                {"job_id": self.job["id"], "log_level": level, "message": message, "metadata": metadata or {}},
                returning=False,
            )
        except SupabaseError as e:  # pragma: no cover - jalur error I/O
            log.warning("gagal menulis job log: %s", e)

    def progress(self, pct: int, *, total: int | None = None, success: int | None = None,
                 failed: int | None = None) -> None:
        values: dict = {"progress": max(0, min(100, int(pct)))}
        if total is not None:
            values["total_processed"] = int(total)
        if success is not None:
            values["success_count"] = int(success)
        if failed is not None:
            values["failed_count"] = int(failed)
        try:
            self.db.update("automation_jobs", {"id": f"eq.{self.job['id']}"}, values, returning=False)
        except SupabaseError as e:  # pragma: no cover - jalur error I/O
            log.warning("gagal memperbarui progress job: %s", e)

    def notify(self, notification_type: str, title: str, message: str, *,
               link: str | None = None, dedupe_key: str | None = None) -> dict | None:
        return create_notification(
            self.db, notification_type=notification_type, title=title, message=message,
            related_job_id=self.job["id"], link=link, dedupe_key=dedupe_key,
        )

    def should_cancel(self) -> bool:
        if self._cancelled:
            return True
        try:
            rows = self.db.select(
                "automation_jobs",
                {"select": "cancel_requested,status", "id": f"eq.{self.job['id']}", "limit": "1"},
            )
        except SupabaseError:  # pragma: no cover - jalur error I/O
            return False
        if not rows:
            return False
        self._cancelled = bool(rows[0].get("cancel_requested")) or rows[0].get("status") == "cancelled"
        return self._cancelled

    def check(self) -> None:
        """Titik pemeriksaan kooperatif: batalkan / timeout bila perlu."""
        if self.should_cancel():
            raise JobCancelled("Dibatalkan oleh admin")
        if time.monotonic() > self.deadline:
            raise JobTimeout("Job melewati batas waktu")


def _status_from_result(result: dict) -> str:
    success = int(result.get("success") or 0)
    failed = int(result.get("failed") or 0)
    if failed <= 0:
        return "completed"
    return "partially_completed" if success > 0 else "failed"


def _recompute_next_run(config: dict) -> str | None:
    try:
        nxt = next_run_at(config["schedule_type"], config.get("schedule_config") or {}, config.get("timezone") or "Asia/Jakarta")
    except Exception:  # pragma: no cover - jadwal rusak
        return None
    return nxt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if nxt else None


def _finish(db: SupabaseClient, settings: Settings, config: dict, job: dict, status: str,
            result: dict | None = None) -> None:
    result = result or {}
    now = _now_iso()
    db.update(
        "automation_jobs",
        {"id": f"eq.{job['id']}"},
        {
            "status": status,
            "progress": 100,
            "total_processed": int(result.get("total") or 0),
            "success_count": int(result.get("success") or 0),
            "failed_count": int(result.get("failed") or 0),
            "completed_at": now,
            "error_message": result.get("message") if status == "failed" else None,
        },
        returning=False,
    )
    if config.get("id"):
        values = {"last_run_at": now, "last_status": status, "last_job_id": job["id"]}
        if config.get("is_enabled", True):
            values["next_run_at"] = _recompute_next_run(config)
        db.update("automation_configs", {"id": f"eq.{config['id']}"}, values, returning=False)

    _notify_outcome(db, settings, config, job, status, result)


def _notify_outcome(db: SupabaseClient, settings: Settings, config: dict, job: dict,
                    status: str, result: dict) -> None:
    name = config.get("automation_name") or job.get("job_name") or job.get("job_type")
    summary = result.get("message") or ""
    dedupe = f"job:{job['id']}:{status}"
    if status == "completed":
        create_notification(
            db, notification_type="automation_completed",
            title=f"{name} selesai",
            message=summary or "Automation berhasil dijalankan.",
            related_job_id=job["id"], link=f"/automation?job={job['id']}", dedupe_key=dedupe,
        )
    elif status == "partially_completed":
        create_notification(
            db, notification_type="automation_partial",
            title=f"{name} selesai sebagian",
            message=summary or "Sebagian data gagal diproses.",
            related_job_id=job["id"], link=f"/automation?job={job['id']}", dedupe_key=dedupe,
        )
    elif status == "failed":
        create_notification(
            db, notification_type="automation_failed",
            title=f"{name} gagal",
            message=summary or "Automation gagal dijalankan.",
            related_job_id=job["id"], link=f"/automation?job={job['id']}", dedupe_key=dedupe,
        )
        maybe_email_admins(db, settings, f"[Green Eco AI] {name} gagal", summary or "Automation gagal dijalankan.")


def _backoff_seconds(config: dict, attempt: int) -> int:
    base = max(5, int(config.get("retry_backoff_seconds") or 60))
    return min(base * (2 ** max(0, attempt - 1)), 86400)


def _fail(db: SupabaseClient, settings: Settings, config: dict, job: dict, error: str,
          retry_scheduler, ctx: JobContext) -> dict:
    attempt = int(job.get("attempt") or 1)
    max_attempts = int(job.get("max_attempts") or 1)
    if attempt < max_attempts and retry_scheduler is not None:
        delay = _backoff_seconds(config, attempt)
        _finish(db, settings, config, job, "failed", {"message": error})
        try:
            retry_scheduler(job, config, delay, attempt + 1)
        except Exception as e:  # pragma: no cover - jalur scheduler
            log.warning("gagal menjadwalkan retry: %s", e)
        ctx.log("warning", f"Percobaan {attempt}/{max_attempts} gagal: {error}. Coba lagi dalam {delay}s.")
        return {"job_id": job["id"], "status": "failed", "error": error, "retry_in": delay}

    _finish(db, settings, config, job, "failed", {"message": error})
    ctx.log("error", f"Job gagal final setelah {attempt} percobaan: {error}")
    create_notification(
        db, notification_type="job_failed_final",
        title=f"{config.get('automation_name') or job.get('job_type')} gagal (final)",
        message=error, related_job_id=job["id"], link=f"/automation?job={job['id']}",
        dedupe_key=f"job:{job['id']}:final",
    )
    maybe_email_admins(db, settings,
                       f"[Green Eco AI] {config.get('automation_name') or job.get('job_type')} gagal",
                       error)
    return {"job_id": job["id"], "status": "failed", "error": error}


def run_job(db: SupabaseClient, settings: Settings, job_id: str, *, retry_scheduler=None) -> dict:
    """Jalankan satu job (sinkron). Dipanggil dari thread scheduler atau thread manual."""
    from .handlers import HANDLERS  # impor lokal: hindari impor melingkar

    job = get_job(db, job_id)
    if not job:
        raise LookupError("Job tidak ditemukan")

    config = None
    if job.get("automation_config_id"):
        config = get_config(db, job["automation_config_id"])
    if config is None:
        config = {
            "id": None,
            "automation_name": job.get("job_name") or job.get("job_type"),
            "automation_type": job.get("job_type"),
            "is_enabled": True,
            "schedule_type": "weekly",
            "schedule_config": {},
            "timezone": settings.timezone,
            "timeout_seconds": settings.automation_default_timeout,
            "retry_max_attempts": 0,
            "retry_backoff_seconds": settings.automation_default_timeout,
        }

    db.update(
        "automation_jobs", {"id": f"eq.{job_id}"},
        {"status": "running", "started_at": _now_iso(), "progress": 1, "error_message": None},
        returning=False,
    )
    if config.get("id"):
        db.update("automation_configs", {"id": f"eq.{config['id']}"}, {"last_status": "running"}, returning=False)

    timeout = int(config.get("timeout_seconds") or settings.automation_default_timeout)
    ctx = JobContext(db=db, settings=settings, config=config, job=job, deadline=time.monotonic() + timeout)
    ctx.log("info", f"Job dimulai (timeout {timeout}s, percobaan {job.get('attempt')}/{job.get('max_attempts')}).")

    handler = HANDLERS.get(config.get("automation_type"))
    try:
        if handler is None:
            raise JobError(f"Tidak ada handler untuk tipe '{config.get('automation_type')}'")
        result = handler(ctx) or {}
        status = _status_from_result(result)
        _finish(db, settings, config, job, status, result)
        ctx.log("info", f"Job selesai dengan status '{status}': {result.get('message') or ''}".strip())
        return {"job_id": job_id, "status": status, **result}
    except JobCancelled as e:
        _finish(db, settings, config, job, "cancelled", {"message": str(e)})
        ctx.log("warning", f"Job dibatalkan: {e}")
        return {"job_id": job_id, "status": "cancelled"}
    except (JobTimeout, JobError) as e:
        return _fail(db, settings, config, job, str(e), retry_scheduler, ctx)
    except Exception as e:  # noqa: BLE001 - semua kegagalan harus tercatat, bukan "sukses"
        log.exception("job %s gagal", job_id)
        return _fail(db, settings, config, job, f"{type(e).__name__}: {e}", retry_scheduler, ctx)


def request_cancel(db: SupabaseClient, job_id: str) -> dict:
    """Batalkan job. Job queued langsung dibatalkan; job running diberi flag kooperatif."""
    job = get_job(db, job_id)
    if not job:
        raise LookupError("Job tidak ditemukan")
    if job["status"] in ("pending", "queued"):
        db.update(
            "automation_jobs", {"id": f"eq.{job_id}"},
            {"status": "cancelled", "cancel_requested": True, "completed_at": _now_iso(),
             "error_message": "Dibatalkan admin"},
            returning=False,
        )
        return {"status": "cancelled", "immediate": True}
    if job["status"] == "running":
        db.update("automation_jobs", {"id": f"eq.{job_id}"}, {"cancel_requested": True}, returning=False)
        return {"status": "running", "immediate": False}
    raise ValueError("Job yang sudah selesai tidak dapat dibatalkan")


def reap_stale_jobs(db: SupabaseClient, settings: Settings, *, older_than_seconds: int | None = None) -> int:
    """Tandai job queued/running yang menggantung (proses mati/restart) sebagai failed."""
    threshold = older_than_seconds or max(3600, settings.automation_default_timeout * 2)
    cutoff = (_now() - timedelta(seconds=threshold)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = db.select(
            "automation_jobs",
            {"select": "id", "status": "in.(queued,running)", "created_at": f"lt.{cutoff}"},
        )
    except SupabaseError as e:  # pragma: no cover - jalur error I/O
        log.warning("gagal membaca job menggantung: %s", e)
        return 0
    for r in rows:
        db.update(
            "automation_jobs", {"id": f"eq.{r['id']}"},
            {"status": "failed", "completed_at": _now_iso(),
             "error_message": "Dihentikan otomatis: proses sebelumnya terputus (restart)."},
            returning=False,
        )
    return len(rows)


__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "JobContext",
    "create_job",
    "get_config",
    "get_config_by_type",
    "get_job",
    "list_enabled_configs",
    "reap_stale_jobs",
    "request_cancel",
    "run_job",
]
