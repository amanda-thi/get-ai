"""Uji manajer scheduler Fase 4 dengan DB palsu (scheduler tidak dijalankan/thread nyata)."""
import pytest

from app.automation import runner
from app.automation import scheduler as sched_module
from app.automation.scheduler import AutomationScheduler
from app.config import Settings
from tests.fakes import AutomationDB


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
        "timezone": "Asia/Jakarta",
        "params": {},
        "retry_max_attempts": 1,
        "retry_backoff_seconds": 60,
        "timeout_seconds": 900,
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
        "trigger_type": "scheduled",
        "status": "queued",
        "progress": 0,
        "attempt": 1,
        "max_attempts": 2,
        "cancel_requested": False,
        "idempotency_key": None,
    }
    job.update(over)
    return job


# --- pemuatan konfigurasi ---

def test_load_configs_adds_enabled_only_and_sets_next_run():
    db = AutomationDB({"automation_configs": [
        make_config(id="cfg-1", automation_name="A"),
        make_config(id="cfg-2", automation_name="B", automation_type="company_discovery", is_enabled=False),
    ]})
    sched = AutomationScheduler(settings(), db)

    sched.load_configs()

    ids = {j.id for j in sched.scheduler.get_jobs()}
    assert ids == {"auto:cfg-1"}
    assert runner.get_config(db, "cfg-1")["next_run_at"]  # terisi
    assert runner.get_config(db, "cfg-2")["next_run_at"] is None


def test_sync_config_disable_removes_job():
    cfg = make_config(id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)
    sched.load_configs()
    assert sched.scheduler.get_job("auto:cfg-1") is not None

    sched.sync_config({**cfg, "is_enabled": False})

    assert sched.scheduler.get_job("auto:cfg-1") is None
    assert runner.get_config(db, "cfg-1")["next_run_at"] is None


def test_sync_config_enable_adds_job():
    cfg = make_config(id="cfg-1", is_enabled=False)
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)

    sched.sync_config({**cfg, "is_enabled": True})

    assert sched.scheduler.get_job("auto:cfg-1") is not None


def test_add_config_invalid_schedule_is_skipped():
    db = AutomationDB({"automation_configs": []})
    sched = AutomationScheduler(settings(), db)
    sched._add_config(make_config(id="cfg-x", schedule_config={"day_of_week": 9}))
    assert sched.scheduler.get_jobs() == []


# --- eksekusi terjadwal ---

def test_run_config_creates_and_runs_job(monkeypatch):
    cfg = make_config(id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)
    ran = []
    monkeypatch.setattr(runner, "run_job", lambda db, s, job_id, **kw: ran.append(job_id))

    sched._run_config("cfg-1")

    jobs = db.rows("automation_jobs")
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"
    assert jobs[0]["trigger_type"] == "scheduled"
    assert ran == [jobs[0]["id"]]


def test_run_config_skips_when_disabled():
    cfg = make_config(id="cfg-1", is_enabled=False)
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)
    sched._run_config("cfg-1")
    assert db.rows("automation_jobs") == []


def test_run_config_skips_duplicate_slot(monkeypatch):
    cfg = make_config(id="cfg-1")
    existing = make_job(cfg, id="running", status="running", automation_config_id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg], "automation_jobs": [existing]})
    sched = AutomationScheduler(settings(), db)
    ran = []
    monkeypatch.setattr(runner, "run_job", lambda *a, **k: ran.append(1))

    sched._run_config("cfg-1")

    assert len(db.rows("automation_jobs")) == 1 and ran == []


# --- eksekusi manual / retry / cancel ---

def test_trigger_manual_creates_and_submits(monkeypatch):
    cfg = make_config(id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)
    submitted = []
    monkeypatch.setattr(sched, "_submit", lambda job_id, delay_seconds=0: submitted.append(job_id))

    job = sched.trigger_manual("cfg-1", "u1")

    assert job["trigger_type"] == "manual" and job["triggered_by"] == "u1"
    assert submitted == [job["id"]]


def test_trigger_manual_conflict_raises():
    cfg = make_config(id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg], "automation_jobs": [make_job(cfg, status="running")]})
    sched = AutomationScheduler(settings(), db)
    with pytest.raises(RuntimeError):
        sched.trigger_manual("cfg-1", "u1")


def test_trigger_manual_unknown_config():
    db = AutomationDB({"automation_configs": []})
    sched = AutomationScheduler(settings(), db)
    with pytest.raises(LookupError):
        sched.trigger_manual("nope", "u1")


def test_schedule_retry_creates_linked_job(monkeypatch):
    cfg = make_config(id="cfg-1")
    job = make_job(cfg, id="job-1", status="failed")
    db = AutomationDB({"automation_configs": [cfg], "automation_jobs": [job]})
    sched = AutomationScheduler(settings(), db)
    submitted = []
    monkeypatch.setattr(sched, "_submit", lambda job_id, delay_seconds=0: submitted.append((job_id, delay_seconds)))

    new_job = sched.schedule_retry(job, cfg, 60, 2)

    assert new_job["trigger_type"] == "retry"
    assert new_job["parent_job_id"] == "job-1"
    assert new_job["attempt"] == 2
    assert submitted == [(new_job["id"], 60)]


def test_cancel_job_delegates_to_runner():
    cfg = make_config(id="cfg-1")
    job = make_job(cfg, id="job-1", status="queued")
    db = AutomationDB({"automation_configs": [cfg], "automation_jobs": [job]})
    sched = AutomationScheduler(settings(), db)

    res = sched.cancel_job("job-1")

    assert res["status"] == "cancelled"
    assert runner.get_job(db, "job-1")["status"] == "cancelled"


def test_submit_adds_one_off_job():
    cfg = make_config(id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)
    sched._submit("job-1")
    assert sched.scheduler.get_job("run:job-1") is not None


# --- singleton start/stop ---

def test_start_scheduler_disabled_returns_none():
    sched_module.stop_scheduler()
    assert sched_module.start_scheduler(settings(scheduler_enabled=False)) is None


def test_start_scheduler_without_db_returns_none():
    sched_module.stop_scheduler()
    s = settings(scheduler_enabled=True, supabase_url="", supabase_service_role_key="")
    assert sched_module.start_scheduler(s) is None


def test_submit_job_uses_global_scheduler_when_present(monkeypatch):
    cfg = make_config(id="cfg-1")
    db = AutomationDB({"automation_configs": [cfg]})
    sched = AutomationScheduler(settings(), db)
    calls = []
    monkeypatch.setattr(sched, "_submit", lambda job_id, delay_seconds=0: calls.append(job_id))
    monkeypatch.setattr(sched_module, "_SCHED", sched)
    try:
        sched_module.submit_job("job-1", db, settings())
    finally:
        monkeypatch.setattr(sched_module, "_SCHED", None)
    assert calls == ["job-1"]
