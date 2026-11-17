"""Uji runner Fase 4: siklus hidup job, lock/duplikat, retry, cancel, timeout, reaper."""
from datetime import datetime, timezone

import pytest

from app.automation import runner
from app.automation import handlers as handlers_module
from app.automation.errors import JobError
from app.config import Settings
from tests.fakes import AutomationDB

TZ = "Asia/Jakarta"


def settings(**kw) -> Settings:
    base = dict(scheduler_enabled=False, automation_notify_email=False, groq_api_key="")
    base.update(kw)
    return Settings(**base)


def make_config(**over) -> dict:
    cfg = {
        "id": "cfg-1",
        "automation_name": "Tender Monitoring",
        "automation_type": "tender_monitoring",
        "is_enabled": True,
        "schedule_type": "weekly",
        "schedule_config": {"day_of_week": 0, "hour": 8, "minute": 0},
        "cron_expression": "0 8 * * 1",
        "timezone": TZ,
        "params": {},
        "retry_max_attempts": 1,
        "retry_backoff_seconds": 60,
        "timeout_seconds": 900,
        "last_status": None,
        "last_run_at": None,
        "last_job_id": None,
        "next_run_at": None,
    }
    cfg.update(over)
    return cfg


def make_job(config, **over) -> dict:
    job = {
        "id": "job-1",
        "automation_config_id": config["id"],
        "job_name": config["automation_name"],
        "job_type": config["automation_type"],
        "trigger_type": "manual",
        "status": "queued",
        "progress": 0,
        "total_processed": 0,
        "success_count": 0,
        "failed_count": 0,
        "error_message": None,
        "attempt": 1,
        "max_attempts": 2,
        "cancel_requested": False,
        "created_at": "2026-11-17T01:00:00Z",
    }
    job.update(over)
    return job


def db_with(config=None, jobs=None, **tables) -> AutomationDB:
    data = {"automation_configs": [config or make_config()], "automation_jobs": jobs or []}
    data.update(tables)
    return AutomationDB(data)


# --- create_job / lock ---

def test_create_job_rejects_second_active_job_for_same_config():
    cfg = make_config()
    db = db_with(cfg)
    first = runner.create_job(db, cfg, trigger_type="manual")
    assert first and first["status"] == "queued"
    assert runner.create_job(db, cfg, trigger_type="manual") is None  # lock aktif


def test_create_job_rejects_duplicate_idempotency_key():
    cfg = make_config()
    db = db_with(cfg)
    assert runner.create_job(db, cfg, trigger_type="scheduled", idempotency_key="slot-1")
    # slot yang sama dari instance lain -> None
    assert runner.create_job(db, cfg, trigger_type="scheduled", idempotency_key="slot-1") is None


def test_create_job_allows_new_job_after_previous_terminal():
    cfg = make_config()
    db = db_with(cfg, jobs=[make_job(cfg, id="old", status="completed")])
    job = runner.create_job(db, cfg, trigger_type="manual")
    assert job is not None and job["id"] != "old"


def test_create_job_sets_max_attempts_from_retry_config():
    cfg = make_config(retry_max_attempts=3)
    db = db_with(cfg)
    job = runner.create_job(db, cfg, trigger_type="manual")
    assert job["max_attempts"] == 4


# --- run_job hasil ---

def test_run_job_completed(monkeypatch):
    cfg = make_config()
    job = make_job(cfg)
    db = db_with(cfg, [job])
    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring",
                        lambda ctx: {"total": 3, "success": 3, "failed": 0, "message": "3 tender"})

    out = runner.run_job(db, settings(), job["id"])

    assert out["status"] == "completed"
    stored = runner.get_job(db, job["id"])
    assert stored["status"] == "completed" and stored["progress"] == 100
    assert stored["total_processed"] == 3 and stored["success_count"] == 3
    assert stored["completed_at"]
    config = runner.get_config(db, cfg["id"])
    assert config["last_status"] == "completed" and config["last_job_id"] == job["id"]
    assert any(n["notification_type"] == "automation_completed" for n in db.rows("notifications"))


def test_run_job_partially_completed(monkeypatch):
    cfg = make_config()
    job = make_job(cfg)
    db = db_with(cfg, [job])
    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring",
                        lambda ctx: {"total": 3, "success": 2, "failed": 1, "message": "sebagian"})

    out = runner.run_job(db, settings(), job["id"])
    assert out["status"] == "partially_completed"
    assert runner.get_job(db, job["id"])["status"] == "partially_completed"
    assert any(n["notification_type"] == "automation_partial" for n in db.rows("notifications"))


def test_run_job_failure_schedules_retry(monkeypatch):
    cfg = make_config(retry_max_attempts=1)
    job = make_job(cfg, attempt=1, max_attempts=2)
    db = db_with(cfg, [job])
    calls = []

    def boom(ctx):
        raise JobError("Kunci AI belum diisi")

    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring", boom)
    out = runner.run_job(db, settings(), job["id"], retry_scheduler=lambda j, c, d, a: calls.append((j["id"], d, a)))

    assert out["status"] == "failed" and out["retry_in"] == 60
    assert calls == [(job["id"], 60, 2)]
    assert runner.get_job(db, job["id"])["status"] == "failed"
    # belum ada notifikasi final
    assert not any(n["notification_type"] == "job_failed_final" for n in db.rows("notifications"))


def test_run_job_failure_final_without_retry(monkeypatch):
    cfg = make_config(retry_max_attempts=0)
    job = make_job(cfg, attempt=1, max_attempts=1)
    db = db_with(cfg, [job])

    def boom(ctx):
        raise RuntimeError("sumber mati")

    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring", boom)
    out = runner.run_job(db, settings(), job["id"])

    assert out["status"] == "failed" and "sumber mati" in out["error"]
    assert any(n["notification_type"] == "job_failed_final" for n in db.rows("notifications"))
    assert any(n["notification_type"] == "automation_failed" for n in db.rows("notifications"))


def test_run_job_backoff_grows_exponentially(monkeypatch):
    cfg = make_config(retry_max_attempts=3, retry_backoff_seconds=30)
    delays = []
    for attempt in (1, 2, 3):
        job = make_job(cfg, id=f"job-{attempt}", attempt=attempt, max_attempts=4, status="queued")
        db = db_with(cfg, [job])
        monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring",
                            lambda ctx: (_ for _ in ()).throw(JobError("x")))
        runner.run_job(db, settings(), job["id"], retry_scheduler=lambda j, c, d, a: delays.append(d))
    assert delays == [30, 60, 120]


def test_run_job_cancelled(monkeypatch):
    cfg = make_config()
    job = make_job(cfg)
    db = db_with(cfg, [job])

    def cancel_then_check(ctx):
        db.update("automation_jobs", {"id": f"eq.{ctx.job['id']}"}, {"cancel_requested": True}, returning=False)
        ctx.check()
        return {"total": 0, "success": 0, "failed": 0}

    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring", cancel_then_check)
    out = runner.run_job(db, settings(), job["id"])
    assert out["status"] == "cancelled"
    assert runner.get_job(db, job["id"])["status"] == "cancelled"


def test_run_job_timeout_is_cooperative(monkeypatch):
    cfg = make_config(timeout_seconds=-1)  # deadline sudah lewat
    job = make_job(cfg, max_attempts=1)
    db = db_with(cfg, [job])

    def check_once(ctx):
        ctx.check()
        return {"total": 0, "success": 0, "failed": 0}

    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring", check_once)
    out = runner.run_job(db, settings(), job["id"])
    assert out["status"] == "failed" and "batas waktu" in out["error"]


def test_run_job_missing_handler_fails():
    cfg = make_config(automation_type="tidak_ada")
    job = make_job(cfg, job_type="tidak_ada", max_attempts=1)
    db = db_with(cfg, [job])
    out = runner.run_job(db, settings(), job["id"])
    assert out["status"] == "failed" and "handler" in out["error"].lower()


def test_run_job_writes_logs_and_progress(monkeypatch):
    cfg = make_config()
    job = make_job(cfg)
    db = db_with(cfg, [job])

    def with_progress(ctx):
        ctx.log("info", "mulai")
        ctx.progress(50, total=2, success=1)
        return {"total": 2, "success": 2, "failed": 0, "message": "ok"}

    monkeypatch.setitem(handlers_module.HANDLERS, "tender_monitoring", with_progress)
    runner.run_job(db, settings(), job["id"])
    logs = db.rows("automation_job_logs")
    assert any(l["message"] == "mulai" for l in logs)
    assert runner.get_job(db, job["id"])["total_processed"] == 2


# --- cancel ---

def test_request_cancel_queued_immediate():
    cfg = make_config()
    job = make_job(cfg, status="queued")
    db = db_with(cfg, [job])
    res = runner.request_cancel(db, job["id"])
    assert res == {"status": "cancelled", "immediate": True}
    assert runner.get_job(db, job["id"])["status"] == "cancelled"


def test_request_cancel_running_is_cooperative():
    cfg = make_config()
    job = make_job(cfg, status="running")
    db = db_with(cfg, [job])
    res = runner.request_cancel(db, job["id"])
    assert res == {"status": "running", "immediate": False}
    stored = runner.get_job(db, job["id"])
    assert stored["cancel_requested"] is True and stored["status"] == "running"


def test_request_cancel_terminal_raises():
    cfg = make_config()
    job = make_job(cfg, status="completed")
    db = db_with(cfg, [job])
    with pytest.raises(ValueError):
        runner.request_cancel(db, job["id"])


# --- reaper ---

def test_reap_stale_jobs_marks_failed():
    cfg = make_config()
    stale = make_job(cfg, id="stale", status="running", created_at="2020-01-01T00:00:00Z")
    fresh = make_job(cfg, id="fresh", status="queued",
                     created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    db = db_with(cfg, [stale, fresh])
    count = runner.reap_stale_jobs(db, settings(), older_than_seconds=3600)
    assert count == 1
    assert runner.get_job(db, "stale")["status"] == "failed"
    assert runner.get_job(db, "fresh")["status"] == "queued"
