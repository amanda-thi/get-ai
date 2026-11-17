"""Uji router Marketing Outreach: filter (murni), config, template admin-only, approve, kirim."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_db
from app.main import app
from app.routers import outreach as outreach_router
from app.routers.outreach import build_message_filters

USERS = {
    "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
    "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
}


class RouterDB:
    def __init__(self, *, messages=None, templates=None, campaigns=None, logs=None, leads=None, companies=None):
        self.data = {
            "users": list(USERS.values()),
            "outreach_messages": messages or [],
            "email_templates": templates or [],
            "outreach_campaigns": campaigns or [],
            "outreach_logs": logs or [],
            "company_leads": leads or [],
            "companies": companies or [],
        }
        self.inserted, self.updates, self.deleted = [], [], []

    def get_user(self, token):
        u = USERS.get(token)
        return {"id": u["id"]} if u else None

    def select(self, table, params=None):
        rows = list(self.data.get(table, []))
        if params and params.get("id") and params["id"].startswith("eq."):
            rid = params["id"].removeprefix("eq.")
            rows = [r for r in rows if r.get("id") == rid]
        return rows

    def insert(self, table, rows, *, upsert=False, on_conflict=None, returning=True):
        payload = rows if isinstance(rows, list) else [rows]
        self.inserted.append({"table": table, "rows": payload})
        return payload if returning else []

    def update(self, table, filters, values, *, returning=True):
        self.updates.append({"table": table, "filters": filters, "values": values})
        return []

    def delete(self, table, filters):
        self.deleted.append({"table": table, "filters": filters})

    def count(self, table, filters=None, select="id"):
        return len(self.data.get(table, []))


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def make_client():
    def _make(db):
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


# --- fungsi murni ---

def test_build_message_filters_basic():
    f = build_message_filters(q="penawaran", status="draft", language="id", lead_id="l1")
    assert f["status"] == "eq.draft"
    assert f["language"] == "eq.id"
    assert f["lead_id"] == "eq.l1"
    assert f["or"] == "(subject.ilike.*penawaran*,body.ilike.*penawaran*,recipient_email.ilike.*penawaran*)"


def test_build_message_filters_sanitizes():
    f = build_message_filters(q="a(b),c*")
    assert f["or"] == "(subject.ilike.*a b c*,body.ilike.*a b c*,recipient_email.ilike.*a b c*)"


# --- endpoint ---

def test_config_requires_auth(make_client):
    assert make_client(RouterDB()).get("/api/outreach/config").status_code == 401


def test_config_reports_smtp_state(make_client, monkeypatch):
    monkeypatch.setattr(outreach_router, "get_settings", lambda: Settings(smtp_host="", smtp_from=""))
    c = make_client(RouterDB())
    body = c.get("/api/outreach/config", headers=auth("tok-staff")).json()
    assert body["smtp_configured"] is False
    assert "company_intro" in body["email_types"]
    assert set(body["languages"]) == {"id", "en", "ko"}


def test_templates_requires_admin_to_write(make_client):
    c = make_client(RouterDB())
    payload = {"name": "Intro ID", "email_type": "company_intro", "language": "id", "subject": "s", "body": "b"}
    assert c.post("/api/outreach/templates", json=payload, headers=auth("tok-staff")).status_code == 403
    assert c.post("/api/outreach/templates", json=payload, headers=auth("tok-admin")).status_code == 200


def test_templates_rejects_bad_language(make_client):
    c = make_client(RouterDB())
    payload = {"name": "x", "email_type": "company_intro", "language": "fr", "subject": "s", "body": "b"}
    assert c.post("/api/outreach/templates", json=payload, headers=auth("tok-admin")).status_code == 400


def test_messages_list_requires_auth(make_client):
    assert make_client(RouterDB()).get("/api/outreach/messages").status_code == 401


def test_messages_list_returns_items(make_client):
    db = RouterDB(
        messages=[{"id": "m1", "lead_id": "l1", "status": "draft", "subject": "Halo", "email_type": "company_intro", "language": "id"}],
        leads=[{"id": "l1", "company_id": "c1"}],
        companies=[{"id": "c1", "name": "PT Acme", "website": "https://acme.co.id"}],
    )
    c = make_client(db)
    body = c.get("/api/outreach/messages", headers=auth("tok-staff")).json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "PT Acme"


def test_generate_requires_ai_key(make_client, monkeypatch):
    monkeypatch.setattr(outreach_router, "get_settings", lambda: Settings(groq_api_key=""))
    c = make_client(RouterDB())
    r = c.post(
        "/api/outreach/generate",
        json={"company_id": "c1", "email_type": "company_intro", "language": "id"},
        headers=auth("tok-staff"),
    )
    assert r.status_code == 503


def test_approve_requires_admin(make_client):
    db = RouterDB(messages=[{"id": "m1", "status": "draft", "subject": "s", "body": "b"}])
    c = make_client(db)
    assert c.post("/api/outreach/messages/m1/approve", headers=auth("tok-staff")).status_code == 403
    assert c.post("/api/outreach/messages/m1/approve", headers=auth("tok-admin")).status_code == 200


def test_send_unconfigured_smtp_returns_502(make_client, monkeypatch):
    monkeypatch.setattr(
        outreach_router, "get_settings", lambda: Settings(smtp_host="", smtp_from="")
    )
    db = RouterDB(
        messages=[{"id": "m1", "status": "approved", "subject": "s", "body": "b", "recipient_email": "a@b.co.id"}]
    )
    c = make_client(db)
    r = c.post("/api/outreach/messages/m1/send", headers=auth("tok-admin"))
    assert r.status_code == 502
    assert "SMTP belum dikonfigurasi" in r.json()["detail"]


def test_send_requires_approval_status(make_client):
    db = RouterDB(messages=[{"id": "m1", "status": "draft", "subject": "s", "body": "b"}])
    c = make_client(db)
    r = c.post("/api/outreach/messages/m1/send", headers=auth("tok-admin"))
    assert r.status_code == 400
