"""Uji endpoint Fase 4: konfigurasi, job, monitoring, eksekusi manual, notifikasi."""
import pytest
from fastapi.testclient import TestClient

from app.automation import scheduler as sched_module
from app.deps import get_db
from app.main import app
from tests.fakes import AutomationDB

USERS = {
    "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
    "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
}


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


class ApiDB(AutomationDB):
    def get_user(self, token):
        u = USERS.get(token)
        return {"id": u["id"]} if u else None


def base_db(**tables) -> ApiDB:
    data = {"users": list(USERS.values())}
    data.update(tables)
    return ApiDB(data)


def make_config(**over) -> dict:
    cfg = {
        "id": "cfg-1",
        "automation_name": "Tender Monitoring",
        "automation_type": "tender_monitoring",
        "description": "Cari tender",
        "is_enabled": True,
        "schedule_type": "weekly",
        "schedule_config": {"day_of_week": 0, "hour": 8, "minute": 0},
        "cron_expression": "0 8 * * 1",
        "timezone": "Asia/Jakarta",
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
        "trigger_type": "scheduled",
        "status": "queued",
        "progress": 0,
        "total_processed": 0,
        "success_count": 0,
        "failed_count": 0,
        "error_message": None,
        "attempt": 1,
        "max_attempts": 2,
        "cancel_requested": False,
        "parent_job_id": None,
        "started_at": None,
        "completed_at": None,
        "created_at": "2026-11-17T01:00:00Z",
    }
    job.update(over)
    return job


@pytest.fixture
def client_factory():
    def _make(db):
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


# --- auth ---

def test_configs_requires_token(client_factory):
    c = client_factory(base_db(automation_configs=[make_config()]))
    assert c.get("/api/automation/configs").status_code == 401


def test_status_endpoint_ok(client_factory):
    c = client_factory(base_db(automation_configs=[make_config()], automation_schedules=[], tender_sources=[]))
    r = c.get("/api/automation/status", headers=auth("tok-staff"))
    assert r.status_code == 200
    assert r.json()["configs"][0]["automation_type"] == "tender_monitoring"


# --- konfigurasi ---

def test_list_configs_includes_description_and_capabilities(client_factory):
    c = client_factory(base_db(automation_configs=[make_config()]))
    r = c.get("/api/automation/configs", headers=auth("tok-admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["schedule_description"].startswith("Setiap Senin")
    assert set(body["capabilities"]) == {"ai", "lead_search", "inaproc", "smtp"}
    assert body["items"][0]["requires"] == []


def test_patch_config_staff_forbidden(client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg]))
    r = c.patch(f"/api/automation/configs/{cfg['id']}",
                json={"schedule_type": "daily", "schedule_config": {"hour": 6, "minute": 0}},
                headers=auth("tok-staff"))
    assert r.status_code == 403


def test_patch_config_admin_recomputes_cron(client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg]))
    r = c.patch(f"/api/automation/configs/{cfg['id']}",
                json={"schedule_type": "daily", "schedule_config": {"hour": 6, "minute": 30}},
                headers=auth("tok-admin"))
    assert r.status_code == 200
    assert r.json()["cron_expression"] == "30 6 * * *"


def test_patch_config_invalid_schedule_returns_400(client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg]))
    r = c.patch(f"/api/automation/configs/{cfg['id']}",
                json={"schedule_type": "weekly", "schedule_config": {"day_of_week": 9}},
                headers=auth("tok-admin"))
    assert r.status_code == 400


def test_patch_config_not_found(client_factory):
    c = client_factory(base_db(automation_configs=[]))
    r = c.patch("/api/automation/configs/nope", json={"is_enabled": False}, headers=auth("tok-admin"))
    assert r.status_code == 404


def test_disable_and_enable_config(client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg]))
    r = c.post(f"/api/automation/configs/{cfg['id']}/disable", headers=auth("tok-admin"))
    assert r.status_code == 200 and r.json()["is_enabled"] is False
    r2 = c.post(f"/api/automation/configs/{cfg['id']}/enable", headers=auth("tok-admin"))
    assert r2.status_code == 200 and r2.json()["is_enabled"] is True


def test_create_config_rejects_unknown_type(client_factory):
    c = client_factory(base_db(automation_configs=[]))
    r = c.post("/api/automation/configs",
               json={"automation_name": "X", "automation_type": "nope",
                     "schedule_type": "daily", "schedule_config": {"hour": 1, "minute": 0}},
               headers=auth("tok-admin"))
    assert r.status_code == 400


# --- monitoring ---

def test_overview_totals_and_avg_duration(client_factory):
    cfg = make_config()
    jobs = [
        make_job(cfg, id="j1", status="completed",
                 started_at="2026-11-17T01:00:00Z", completed_at="2026-11-17T01:02:00Z"),
        make_job(cfg, id="j2", status="failed"),
    ]
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=jobs))
    r = c.get("/api/automation/overview", headers=auth("tok-staff"))
    assert r.status_code == 200
    d = r.json()
    assert d["totals"]["total"] == 2
    assert d["totals"]["completed"] == 1 and d["totals"]["failed"] == 1
    assert d["avg_duration_seconds"] == 120


def test_list_jobs_filters_by_status(client_factory):
    cfg = make_config()
    jobs = [make_job(cfg, id="j1", status="completed"), make_job(cfg, id="j2", status="failed")]
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=jobs))
    r = c.get("/api/automation/jobs?status=failed", headers=auth("tok-admin"))
    assert r.status_code == 200
    assert [j["id"] for j in r.json()["items"]] == ["j2"]
    assert r.json()["total"] == 1


def test_job_detail_includes_logs_and_config(client_factory):
    cfg = make_config()
    job = make_job(cfg, id="j1", status="failed")
    logs = [{"id": "l1", "job_id": "j1", "log_level": "error", "message": "boom",
             "metadata": {}, "created_at": "2026-11-17T01:00:05Z"}]
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[job], automation_job_logs=logs))
    r = c.get("/api/automation/jobs/j1", headers=auth("tok-admin"))
    assert r.status_code == 200
    d = r.json()
    assert d["job"]["id"] == "j1"
    assert d["logs"][0]["message"] == "boom"
    assert d["config"]["id"] == cfg["id"]


def test_job_detail_not_found(client_factory):
    c = client_factory(base_db(automation_jobs=[]))
    assert c.get("/api/automation/jobs/nope", headers=auth("tok-admin")).status_code == 404


def test_list_logs_attaches_job_info(client_factory):
    cfg = make_config()
    job = make_job(cfg, id="j1", status="completed")
    logs = [{"id": "l1", "job_id": "j1", "log_level": "info", "message": "mulai",
             "metadata": {}, "created_at": "2026-11-17T01:00:00Z"}]
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[job], automation_job_logs=logs))
    r = c.get("/api/automation/logs", headers=auth("tok-admin"))
    assert r.status_code == 200
    assert r.json()["items"][0]["job_name"] == "Tender Monitoring"


# --- eksekusi manual / retry / cancel ---

def test_run_now_staff_forbidden(client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg]))
    r = c.post("/api/automation/jobs/run", json={"automation_type": "tender_monitoring"}, headers=auth("tok-staff"))
    assert r.status_code == 403


def test_run_now_admin_creates_job(monkeypatch, client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg]))
    monkeypatch.setattr(sched_module, "submit_job", lambda *a, **k: None)
    r = c.post("/api/automation/jobs/run", json={"automation_type": "tender_monitoring"}, headers=auth("tok-admin"))
    assert r.status_code == 200
    job = r.json()["job"]
    assert job["trigger_type"] == "manual" and job["status"] == "queued"


def test_run_now_requires_identifier(client_factory):
    c = client_factory(base_db(automation_configs=[make_config()]))
    r = c.post("/api/automation/jobs/run", json={}, headers=auth("tok-admin"))
    assert r.status_code == 400


def test_run_now_conflict_when_active(monkeypatch, client_factory):
    cfg = make_config()
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[make_job(cfg, status="running")]))
    monkeypatch.setattr(sched_module, "submit_job", lambda *a, **k: None)
    r = c.post("/api/automation/jobs/run", json={"config_id": "cfg-1"}, headers=auth("tok-admin"))
    assert r.status_code == 409


def test_retry_failed_job_creates_linked_job(monkeypatch, client_factory):
    cfg = make_config()
    job = make_job(cfg, id="j1", status="failed")
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[job]))
    monkeypatch.setattr(sched_module, "submit_job", lambda *a, **k: None)
    r = c.post("/api/automation/jobs/j1/retry", headers=auth("tok-admin"))
    assert r.status_code == 200
    new_job = r.json()["job"]
    assert new_job["trigger_type"] == "retry" and new_job["parent_job_id"] == "j1"


def test_retry_rejects_completed_job(client_factory):
    cfg = make_config()
    job = make_job(cfg, id="j1", status="completed")
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[job]))
    r = c.post("/api/automation/jobs/j1/retry", headers=auth("tok-admin"))
    assert r.status_code == 400


def test_cancel_queued_job(client_factory):
    cfg = make_config()
    job = make_job(cfg, id="j1", status="queued")
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[job]))
    r = c.post("/api/automation/jobs/j1/cancel", headers=auth("tok-admin"))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_cancel_completed_job_400(client_factory):
    cfg = make_config()
    job = make_job(cfg, id="j1", status="completed")
    c = client_factory(base_db(automation_configs=[cfg], automation_jobs=[job]))
    r = c.post("/api/automation/jobs/j1/cancel", headers=auth("tok-admin"))
    assert r.status_code == 400


# --- notifikasi ---

def notes():
    return [
        {"id": "n1", "user_id": None, "notification_type": "automation_completed",
         "title": "T", "message": "M", "related_job_id": None, "link": None,
         "is_read": False, "created_at": "2026-11-17T01:00:00Z"},
        {"id": "n2", "user_id": "u2", "notification_type": "automation_failed",
         "title": "S", "message": "M", "related_job_id": None, "link": None,
         "is_read": False, "created_at": "2026-11-17T02:00:00Z"},
        {"id": "n3", "user_id": "u1", "notification_type": "lead_new",
         "title": "A", "message": "M", "related_job_id": None, "link": None,
         "is_read": False, "created_at": "2026-11-17T03:00:00Z"},
    ]


def test_notifications_admin_sees_broadcast_and_own(client_factory):
    c = client_factory(base_db(notifications=notes()))
    r = c.get("/api/notifications", headers=auth("tok-admin"))
    assert r.status_code == 200
    d = r.json()
    # admin: broadcast (user_id NULL) + miliknya sendiri, bukan notifikasi staff lain
    assert {n["id"] for n in d["items"]} == {"n1", "n3"}
    assert d["unread_count"] == 2


def test_notifications_staff_sees_only_own(client_factory):
    c = client_factory(base_db(notifications=notes()))
    r = c.get("/api/notifications", headers=auth("tok-staff"))
    assert r.status_code == 200
    assert {n["id"] for n in r.json()["items"]} == {"n2"}


def test_unread_count_endpoint(client_factory):
    c = client_factory(base_db(notifications=notes()))
    r = c.get("/api/notifications/unread-count", headers=auth("tok-staff"))
    assert r.status_code == 200 and r.json()["unread_count"] == 1


def test_mark_own_notification_read(client_factory):
    c = client_factory(base_db(notifications=notes()))
    r = c.patch("/api/notifications/n2/read", headers=auth("tok-staff"))
    assert r.status_code == 200 and r.json()["is_read"] is True


def test_staff_cannot_mark_broadcast_read(client_factory):
    c = client_factory(base_db(notifications=notes()))
    r = c.patch("/api/notifications/n1/read", headers=auth("tok-staff"))
    assert r.status_code == 403


def test_read_all_marks_visible_notifications(client_factory):
    c = client_factory(base_db(notifications=notes()))
    r = c.post("/api/notifications/read-all", headers=auth("tok-admin"))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["updated"] == 2  # broadcast + milik admin


# --- tabel belum ada (migrasi 010 belum dijalankan) ---

class MissingTableDB(ApiDB):
    """Mensimulasikan tabel Fase 4 yang belum ada: PostgREST PGRST205."""

    def __init__(self, missing, tables=None):
        super().__init__(tables or {"users": list(USERS.values())})
        self._missing = set(missing)

    def select(self, table, params=None):
        if table in self._missing:
            from app.db import SupabaseError
            raise SupabaseError(
                f"GET /rest/v1/{table} gagal (404): "
                '{"code":"PGRST205","message":"Could not find the table in the schema cache"}'
            )
        return super().select(table, params)


def test_configs_missing_table_returns_friendly_503(client_factory):
    c = client_factory(MissingTableDB({"automation_configs"}))
    r = c.get("/api/automation/configs", headers=auth("tok-admin"))
    assert r.status_code == 503
    assert "010" in r.json()["detail"] and "migrasi" in r.json()["detail"].lower()


def test_notifications_missing_table_returns_friendly_503(client_factory):
    c = client_factory(MissingTableDB({"notifications"}))
    r = c.get("/api/notifications", headers=auth("tok-admin"))
    assert r.status_code == 503
    assert "010" in r.json()["detail"]
