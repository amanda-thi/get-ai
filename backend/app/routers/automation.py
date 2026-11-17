"""Router Automation (Fase 4): konfigurasi jadwal, job, monitoring, eksekusi manual.

Semua endpoint butuh autentikasi. Perubahan konfigurasi dan eksekusi manual/retry/cancel
hanya untuk role **admin** (spec: staff tidak boleh mengubah scheduler).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..automation import registry
from ..automation.registry import AUTOMATION_TYPES, SCHEDULE_TYPES, ScheduleError
from ..automation import runner
from ..automation import scheduler as sched_module
from ..config import get_settings
from ..db import SupabaseClient, SupabaseError, is_missing_table_error
from ..deps import get_current_user, get_db, require_role
from ..ratelimit import limiter

router = APIRouter(prefix="/api/automation", tags=["automation"])

_MISSING_TABLES = (
    "Tabel Fase 4 belum ada. Jalankan migrasi "
    "`supabase/migrations/010_phase4_automation.sql` di Supabase SQL Editor, lalu muat ulang halaman ini."
)


def _db_error(e: SupabaseError) -> HTTPException:
    """Ubah galat DB menjadi HTTPException; beri pesan jelas bila migrasi belum dijalankan."""
    if is_missing_table_error(e):
        return HTTPException(503, _MISSING_TABLES)
    return HTTPException(503, str(e))

_SANITIZE_RE = re.compile(r"[(),*%]")
_CONFIG_SELECT = "*"
_JOB_SELECT = "*"
_JOB_STATUSES = ("pending", "queued", "running", "completed", "partially_completed", "failed", "cancelled")


def _clean(value) -> str:
    return re.sub(r"\s+", " ", _SANITIZE_RE.sub(" ", str(value or ""))).strip()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _with_duration(job: dict) -> dict:
    start, end = _parse_iso(job.get("started_at")), _parse_iso(job.get("completed_at"))
    if start and end:
        job["duration_seconds"] = max(0, int((end - start).total_seconds()))
    else:
        job["duration_seconds"] = None
    return job


def _validate_schedule(schedule_type: str, schedule_config: dict, timezone: str) -> str:
    """Validasi jadwal; kembalikan cron standar. Lempar HTTPException(400) bila salah."""
    try:
        tz = registry.get_tz(timezone)
        cron = registry.cron_from_schedule(schedule_type, schedule_config or {})
        registry.build_trigger(schedule_type, schedule_config or {}, tz)
    except ScheduleError as e:
        raise HTTPException(400, str(e)) from e
    return cron


def _apply_scheduler(db: SupabaseClient, config: dict) -> None:
    """Terapkan perubahan jadwal ke scheduler (bila aktif) atau simpan next_run_at."""
    sched = sched_module.get_scheduler()
    if sched is not None:
        sched.sync_config(config)
        return
    nxt = None
    if config.get("is_enabled"):
        try:
            nxt = registry.next_run_at(
                config["schedule_type"], config.get("schedule_config") or {},
                config.get("timezone") or "Asia/Jakarta",
            )
        except ScheduleError:
            nxt = None
    value = nxt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if nxt else None
    db.update("automation_configs", {"id": f"eq.{config['id']}"}, {"next_run_at": value}, returning=False)


# --- model ---

class ConfigIn(BaseModel):
    automation_name: str = Field(min_length=1, max_length=200)
    automation_type: str
    description: str | None = None
    is_enabled: bool = True
    schedule_type: str = "weekly"
    schedule_config: dict = Field(default_factory=dict)
    timezone: str = "Asia/Jakarta"
    params: dict = Field(default_factory=dict)
    retry_max_attempts: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: int = Field(default=60, ge=5, le=86400)
    timeout_seconds: int = Field(default=900, ge=30, le=86400)


class ConfigUpdate(BaseModel):
    automation_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_enabled: bool | None = None
    schedule_type: str | None = None
    schedule_config: dict | None = None
    timezone: str | None = None
    params: dict | None = None
    retry_max_attempts: int | None = Field(default=None, ge=0, le=10)
    retry_backoff_seconds: int | None = Field(default=None, ge=5, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=30, le=86400)


class RunRequest(BaseModel):
    config_id: str | None = None
    automation_type: str | None = None


# --- status lama (kompatibel) ---

@router.get("/status")
def status(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    """Ringkasan cepat: jadwal automation + kesehatan sumber tender."""
    try:
        return {
            "configs": db.select("automation_configs", {"select": _CONFIG_SELECT, "order": "automation_name.asc"}),
            "schedules": db.select("automation_schedules", {"select": "*"}),
            "sources": db.select(
                "tender_sources",
                {"select": "id,name,adapter_type,base_url,is_active,health_status,last_checked_at,last_success_at,last_error"},
            ),
        }
    except SupabaseError as e:
        raise _db_error(e) from e


# --- konfigurasi ---

@router.get("/configs")
def list_configs(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        configs = db.select("automation_configs", {"select": _CONFIG_SELECT, "order": "automation_name.asc"})
    except SupabaseError as e:
        raise _db_error(e) from e
    settings = get_settings()
    ready = {
        "ai": settings.ai_configured,
        "lead_search": settings.lead_search_configured,
        "inaproc": settings.inaproc_configured,
        "smtp": settings.smtp_configured,
    }
    for c in configs:
        meta = AUTOMATION_TYPES.get(c["automation_type"], {})
        c["requires"] = list(meta.get("requires", ()))
        c["requirements_ready"] = all(ready.get(r, True) for r in meta.get("requires", ()))
        c["schedule_description"] = registry.describe_schedule(
            c["schedule_type"], c.get("schedule_config") or {}, c.get("timezone") or "Asia/Jakarta"
        )
    return {"items": configs, "capabilities": ready, "supported_types": sorted(AUTOMATION_TYPES)}


@router.post("/configs")
def create_config(
    payload: ConfigIn,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    if payload.automation_type not in AUTOMATION_TYPES:
        raise HTTPException(400, f"automation_type tidak didukung. Pilihan: {', '.join(sorted(AUTOMATION_TYPES))}")
    if payload.schedule_type not in SCHEDULE_TYPES:
        raise HTTPException(400, f"schedule_type tidak valid. Pilihan: {', '.join(SCHEDULE_TYPES)}")
    cron = _validate_schedule(payload.schedule_type, payload.schedule_config, payload.timezone)
    row = {
        **payload.model_dump(),
        "cron_expression": cron,
    }
    try:
        rows = db.insert("automation_configs", row)
    except SupabaseError as e:
        if "(409)" in str(e) or "23505" in str(e):
            raise HTTPException(409, "automation_type sudah ada") from e
        raise _db_error(e) from e
    config = rows[0] if rows else row
    _apply_scheduler(db, config)
    return config


@router.patch("/configs/{config_id}")
def update_config(
    config_id: str,
    payload: ConfigUpdate,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    try:
        existing = runner.get_config(db, config_id)
    except SupabaseError as e:
        raise _db_error(e) from e
    if not existing:
        raise HTTPException(404, "Konfigurasi automation tidak ditemukan")
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "Tidak ada perubahan.")
    merged = {**existing, **values}
    schedule_type = merged.get("schedule_type") or "weekly"
    schedule_config = merged.get("schedule_config") or {}
    timezone_name = merged.get("timezone") or "Asia/Jakarta"
    if schedule_type not in SCHEDULE_TYPES:
        raise HTTPException(400, f"schedule_type tidak valid. Pilihan: {', '.join(SCHEDULE_TYPES)}")
    values["cron_expression"] = _validate_schedule(schedule_type, schedule_config, timezone_name)
    try:
        rows = db.update("automation_configs", {"id": f"eq.{config_id}"}, values)
    except SupabaseError as e:
        raise _db_error(e) from e
    config = rows[0] if rows else merged
    _apply_scheduler(db, config)
    return config


def _set_enabled(config_id: str, enabled: bool, db: SupabaseClient) -> dict:
    try:
        existing = runner.get_config(db, config_id)
    except SupabaseError as e:
        raise _db_error(e) from e
    if not existing:
        raise HTTPException(404, "Konfigurasi automation tidak ditemukan")
    try:
        rows = db.update("automation_configs", {"id": f"eq.{config_id}"}, {"is_enabled": enabled})
    except SupabaseError as e:
        raise _db_error(e) from e
    config = rows[0] if rows else {**existing, "is_enabled": enabled}
    _apply_scheduler(db, config)
    return config


@router.post("/configs/{config_id}/enable")
def enable_config(config_id: str, user: dict = Depends(require_role("admin")), db: SupabaseClient = Depends(get_db)):
    return _set_enabled(config_id, True, db)


@router.post("/configs/{config_id}/disable")
def disable_config(config_id: str, user: dict = Depends(require_role("admin")), db: SupabaseClient = Depends(get_db)):
    return _set_enabled(config_id, False, db)


# --- monitoring ---

@router.get("/overview")
def overview(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    """Ringkasan dashboard automation."""
    try:
        jobs = db.select(
            "automation_jobs",
            {"select": "*", "order": "created_at.desc", "limit": "300"},
        )
        total = db.count("automation_jobs")
        counts = {s: db.count("automation_jobs", {"status": f"eq.{s}"}) for s in _JOB_STATUSES}
        configs = db.select("automation_configs", {"select": _CONFIG_SELECT, "order": "automation_name.asc"})
    except SupabaseError as e:
        raise _db_error(e) from e

    durations = [j["duration_seconds"] for j in (_with_duration(dict(j)) for j in jobs) if j["duration_seconds"] is not None]
    avg_duration = int(sum(durations) / len(durations)) if durations else 0
    last = _with_duration(dict(jobs[0])) if jobs else None
    upcoming = sorted(
        (c for c in configs if c.get("is_enabled") and c.get("next_run_at")),
        key=lambda c: c["next_run_at"],
    )[:5]
    return {
        "totals": {
            "total": total,
            "running": counts["running"] + counts["queued"],
            "completed": counts["completed"],
            "partial": counts["partially_completed"],
            "failed": counts["failed"],
            "cancelled": counts["cancelled"],
            "pending": counts["pending"],
        },
        "avg_duration_seconds": avg_duration,
        "last_execution": last,
        "upcoming": [
            {
                "id": c["id"],
                "automation_name": c["automation_name"],
                "automation_type": c["automation_type"],
                "next_run_at": c.get("next_run_at"),
                "schedule_description": registry.describe_schedule(
                    c["schedule_type"], c.get("schedule_config") or {}, c.get("timezone") or "Asia/Jakarta"
                ),
            }
            for c in upcoming
        ],
        "recent_jobs": [_with_duration(dict(j)) for j in jobs[:8]],
    }


def _job_filters(job_type: str = "", status: str = "", trigger_type: str = "",
                 date_from: str = "", date_to: str = "") -> dict:
    filters: dict = {}
    if job_type:
        filters["job_type"] = f"eq.{_clean(job_type)}"
    if status:
        filters["status"] = f"eq.{_clean(status)}"
    if trigger_type:
        filters["trigger_type"] = f"eq.{_clean(trigger_type)}"
    rng = []
    if date_from:
        rng.append(f"created_at.gte.{_clean(date_from)}")
    if date_to:
        rng.append(f"created_at.lte.{_clean(date_to)}")
    if rng:
        filters["and"] = f"({','.join(rng)})"
    return filters


@router.get("/jobs")
def list_jobs(
    job_type: str = "",
    status: str = "",
    trigger_type: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    filters = _job_filters(job_type, status, trigger_type, date_from, date_to)
    params = {
        "select": _JOB_SELECT,
        "order": "created_at.desc",
        "limit": str(per_page),
        "offset": str((page - 1) * per_page),
        **filters,
    }
    try:
        rows = db.select("automation_jobs", params)
        total = db.count("automation_jobs", filters)
    except SupabaseError as e:
        raise _db_error(e) from e
    return {
        "items": [_with_duration(dict(r)) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        job = runner.get_job(db, job_id)
        if not job:
            raise HTTPException(404, "Job tidak ditemukan")
        logs = db.select(
            "automation_job_logs",
            {"select": "*", "job_id": f"eq.{job_id}", "order": "created_at.asc", "limit": "500"},
        )
        config = runner.get_config(db, job["automation_config_id"]) if job.get("automation_config_id") else None
        children = db.select(
            "automation_jobs",
            {"select": "id,status,attempt,created_at", "parent_job_id": f"eq.{job_id}", "order": "created_at.asc"},
        )
    except SupabaseError as e:
        raise _db_error(e) from e
    return {
        "job": _with_duration(dict(job)),
        "logs": logs,
        "config": config,
        "retries": children,
    }


@router.get("/logs")
def list_logs(
    job_type: str = "",
    log_level: str = "",
    job_id: str = "",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Log automation (tanpa data kredensial)."""
    filters: dict = {}
    if job_id:
        filters["job_id"] = f"eq.{_clean(job_id)}"
    if log_level:
        filters["log_level"] = f"eq.{_clean(log_level)}"
    params = {
        "select": "*",
        "order": "created_at.desc",
        "limit": str(per_page),
        "offset": str((page - 1) * per_page),
        **filters,
    }
    try:
        rows = db.select("automation_job_logs", params)
        total = db.count("automation_job_logs", filters)
        job_ids = sorted({r["job_id"] for r in rows if r.get("job_id")})
        jobs = {}
        if job_ids:
            for j in db.select("automation_jobs", {"select": "id,job_name,job_type", "id": f"in.({','.join(job_ids)})"}):
                jobs[j["id"]] = j
    except SupabaseError as e:
        raise _db_error(e) from e
    items = []
    for r in rows:
        jt = jobs.get(r.get("job_id"), {})
        if job_type and jt.get("job_type") != job_type:
            continue
        items.append({**r, "job_name": jt.get("job_name"), "job_type": jt.get("job_type")})
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


# --- eksekusi manual / retry / cancel ---

@router.post("/jobs/run")
@limiter.limit("10/minute")
def run_job_now(
    payload: RunRequest,
    request: Request,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    """Jalankan automation secara manual (di latar belakang, tidak menunggu selesai)."""
    try:
        if payload.config_id:
            config = runner.get_config(db, payload.config_id)
        elif payload.automation_type:
            config = runner.get_config_by_type(db, payload.automation_type)
        else:
            raise HTTPException(400, "Isi config_id atau automation_type.")
    except SupabaseError as e:
        raise _db_error(e) from e
    if not config:
        raise HTTPException(404, "Konfigurasi automation tidak ditemukan")

    settings = get_settings()
    sched = sched_module.get_scheduler()
    try:
        if sched is not None:
            job = sched.trigger_manual(config["id"], user["id"])
        else:
            job = runner.create_job(db, config, trigger_type="manual", triggered_by=user["id"])
            if not job:
                raise RuntimeError("Job untuk automation ini sedang berjalan")
            sched_module.submit_job(job["id"], db, settings)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    except SupabaseError as e:
        raise _db_error(e) from e
    return {"ok": True, "job": _with_duration(dict(job))}


@router.post("/jobs/{job_id}/retry")
@limiter.limit("10/minute")
def retry_job(
    job_id: str,
    request: Request,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    try:
        job = runner.get_job(db, job_id)
        if not job:
            raise HTTPException(404, "Job tidak ditemukan")
        if job["status"] not in ("failed", "partially_completed", "cancelled"):
            raise HTTPException(400, "Hanya job gagal/sebagian/dibatalkan yang dapat dijalankan ulang.")
        config = runner.get_config(db, job["automation_config_id"]) if job.get("automation_config_id") else None
    except SupabaseError as e:
        raise _db_error(e) from e
    if not config:
        raise HTTPException(400, "Konfigurasi job tidak ditemukan; tidak dapat diulang.")
    settings = get_settings()
    sched = sched_module.get_scheduler()
    try:
        if sched is not None:
            new_job = sched.retry_job(job_id, config, user["id"])
        else:
            new_job = runner.create_job(db, config, trigger_type="retry", triggered_by=user["id"], parent_job_id=job_id)
            if new_job:
                sched_module.submit_job(new_job["id"], db, settings)
    except SupabaseError as e:
        raise _db_error(e) from e
    if not new_job:
        raise HTTPException(409, "Job untuk automation ini sedang berjalan")
    return {"ok": True, "job": _with_duration(dict(new_job))}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: dict = Depends(require_role("admin")), db: SupabaseClient = Depends(get_db)):
    try:
        job = runner.get_job(db, job_id)
        if not job:
            raise HTTPException(404, "Job tidak ditemukan")
        sched = sched_module.get_scheduler()
        result = sched.cancel_job(job_id) if sched is not None else runner.request_cancel(db, job_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except SupabaseError as e:
        raise _db_error(e) from e
    return {"ok": True, **result}
