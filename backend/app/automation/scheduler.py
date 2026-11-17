"""Manajer APScheduler untuk automation Fase 4 (singleton per proses).

* Sumber kebenaran jadwal = tabel `automation_configs`; dimuat ulang saat startup
  sehingga jadwal bertahan setelah restart.
* Job berjalan di thread pool terpisah → tidak menghambat event loop FastAPI.
* Anti-ganda antar-instance dijaga di level DB (lihat `runner.create_job`).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from ..config import Settings, get_settings
from ..db import SupabaseClient, SupabaseError
from . import runner
from .registry import build_trigger, get_tz, next_run_at

log = logging.getLogger(__name__)

_SCHED: "AutomationScheduler | None" = None
_PREFIX = "auto:"
_RUN_PREFIX = "run:"


class AutomationScheduler:
    def __init__(self, settings: Settings, db: SupabaseClient):
        self.settings = settings
        self.db = db
        self.scheduler = BackgroundScheduler(
            timezone=get_tz(settings.timezone),
            executors={"default": ThreadPoolExecutor(max_workers=settings.automation_max_workers)},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": settings.automation_misfire_grace,
            },
        )

    # --- siklus hidup ---

    def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.start()
        try:
            reaped = runner.reap_stale_jobs(self.db, self.settings)
            if reaped:
                log.info("Menandai %s job menggantung sebagai gagal (restart).", reaped)
        except Exception as e:  # noqa: BLE001
            log.warning("reaper job gagal: %s", e)
        self.load_configs()
        log.info("Automation scheduler aktif (timezone %s, %s worker).",
                 self.settings.timezone, self.settings.automation_max_workers)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # --- sinkronisasi konfigurasi ---

    def load_configs(self) -> None:
        for job in self.scheduler.get_jobs():
            if job.id.startswith(_PREFIX):
                try:
                    self.scheduler.remove_job(job.id)
                except Exception:  # pragma: no cover
                    pass
        try:
            configs = runner.list_enabled_configs(self.db)
        except SupabaseError as e:
            log.warning("gagal memuat konfigurasi automation: %s", e)
            return
        for cfg in configs:
            self._add_config(cfg)

    def sync_config(self, config: dict) -> None:
        """Terapkan perubahan satu konfigurasi (dipanggil setelah PATCH/enable/disable)."""
        self.remove_config(config["id"])
        if config.get("is_enabled"):
            self._add_config(config)
        else:
            self._set_next_run(config["id"], None)

    def remove_config(self, config_id: str) -> None:
        try:
            self.scheduler.remove_job(_PREFIX + config_id)
        except Exception:
            pass

    def _add_config(self, cfg: dict) -> None:
        tz = cfg.get("timezone") or self.settings.timezone
        try:
            trigger = build_trigger(cfg["schedule_type"], cfg.get("schedule_config") or {}, get_tz(tz))
            nxt = next_run_at(cfg["schedule_type"], cfg.get("schedule_config") or {}, tz)
        except Exception as e:  # noqa: BLE001
            log.warning("jadwal config '%s' tidak valid: %s", cfg.get("automation_type"), e)
            return
        self.scheduler.add_job(
            self._run_config, trigger=trigger, id=_PREFIX + cfg["id"],
            args=[cfg["id"]], replace_existing=True,
        )
        self._set_next_run(cfg["id"], nxt)

    def _set_next_run(self, config_id: str, nxt: datetime | None) -> None:
        value = nxt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if nxt else None
        try:
            self.db.update("automation_configs", {"id": f"eq.{config_id}"}, {"next_run_at": value}, returning=False)
        except SupabaseError as e:  # pragma: no cover - jalur error I/O
            log.warning("gagal memperbarui next_run_at: %s", e)

    # --- eksekusi ---

    def _run_config(self, config_id: str) -> None:
        """Dipanggil APScheduler untuk eksekusi terjadwal."""
        try:
            cfg = runner.get_config(self.db, config_id)
        except SupabaseError as e:
            log.warning("gagal memuat config %s: %s", config_id, e)
            return
        if not cfg or not cfg.get("is_enabled"):
            return
        slot = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        key = f"{cfg['automation_type']}:scheduled:{slot}"
        job = runner.create_job(self.db, cfg, trigger_type="scheduled", idempotency_key=key)
        if not job:
            return  # job aktif lain atau slot sudah dijalankan instance lain
        runner.run_job(self.db, self.settings, job["id"], retry_scheduler=self.schedule_retry)

    def _submit(self, job_id: str, delay_seconds: int = 0) -> None:
        run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        self.scheduler.add_job(
            runner.run_job, "date", run_date=run_at, id=_RUN_PREFIX + job_id,
            args=[self.db, self.settings, job_id],
            kwargs={"retry_scheduler": self.schedule_retry},
            replace_existing=True, misfire_grace_time=None,
        )

    def trigger_manual(self, config_id: str, user_id: str | None) -> dict:
        cfg = runner.get_config(self.db, config_id)
        if not cfg:
            raise LookupError("Konfigurasi automation tidak ditemukan")
        job = runner.create_job(self.db, cfg, trigger_type="manual", triggered_by=user_id)
        if not job:
            raise RuntimeError("Job untuk automation ini sedang berjalan")
        self._submit(job["id"])
        return job

    def retry_job(self, job_id: str, config: dict, user_id: str | None) -> dict | None:
        job = runner.create_job(
            self.db, config, trigger_type="retry", triggered_by=user_id, parent_job_id=job_id,
        )
        if job:
            self._submit(job["id"])
        return job

    def cancel_job(self, job_id: str) -> dict:
        result = runner.request_cancel(self.db, job_id)
        try:
            self.scheduler.remove_job(_RUN_PREFIX + job_id)
        except Exception:
            pass
        return result

    def schedule_retry(self, job: dict, config: dict, delay: int, attempt: int) -> dict | None:
        """Callback runner: jadwalkan percobaan ulang dengan backoff."""
        new_job = runner.create_job(
            self.db, config, trigger_type="retry", parent_job_id=job["id"], attempt=attempt,
        )
        if new_job:
            self._submit(new_job["id"], delay_seconds=delay)
        return new_job


def build_client(settings: Settings) -> SupabaseClient:
    return SupabaseClient(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_anon_key)


def submit_job(job_id: str, db: SupabaseClient, settings: Settings, delay_seconds: int = 0) -> None:
    """Jalankan job di latar belakang. Pakai thread pool scheduler bila ada,
    atau thread mandiri bila scheduler dinonaktifkan (agar eksekusi manual tetap jalan)."""
    sched = _SCHED
    if sched is not None:
        sched._submit(job_id, delay_seconds)
        return
    threading.Thread(
        target=runner.run_job, args=(db, settings, job_id), daemon=True
    ).start()


def start_scheduler(settings: Settings | None = None) -> AutomationScheduler | None:
    global _SCHED
    settings = settings or get_settings()
    if not settings.scheduler_enabled:
        log.info("Scheduler dinonaktifkan (SCHEDULER_ENABLED=false).")
        return None
    if not settings.db_configured:
        log.warning("Scheduler tidak diaktifkan: SUPABASE_URL / SERVICE_ROLE_KEY belum diisi.")
        return None
    if _SCHED is not None:
        return _SCHED
    try:
        db = build_client(settings)
    except SupabaseError as e:  # pragma: no cover
        log.warning("Scheduler tidak diaktifkan: %s", e)
        return None
    _SCHED = AutomationScheduler(settings, db)
    _SCHED.start()
    return _SCHED


def stop_scheduler() -> None:
    global _SCHED
    if _SCHED is not None:
        _SCHED.shutdown()
        _SCHED = None


def get_scheduler() -> AutomationScheduler | None:
    return _SCHED


__all__ = ["AutomationScheduler", "build_client", "get_scheduler", "start_scheduler", "stop_scheduler", "submit_job"]
