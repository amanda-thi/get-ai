"""Uji router Company Leads: filter/params (murni), listing, detail, discovery, kualifikasi."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_db
from app.main import app
from app.routers import leads as leads_router
from app.routers.leads import build_list_filters, build_list_params, shape_lead

USERS = {
    "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
    "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
}


class RouterDB:
    def __init__(self, *, view=None, companies=None, leads=None, contacts=None, analysis=None, messages=None):
        self.data = {
            "users": list(USERS.values()),
            "leads_with_analysis": view or [],
            "companies": companies or [],
            "company_leads": leads or [],
            "company_contacts": contacts or [],
            "lead_analysis": analysis or [],
            "outreach_messages": messages or [],
            "system_logs": [],
        }
        self.inserted, self.updates, self.deleted = [], [], []

    def get_user(self, token):
        u = USERS.get(token)
        return {"id": u["id"]} if u else None

    def select(self, table, params=None):
        rows = list(self.data.get(table, []))
        if params and params.get("id"):
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


VIEW_ROW = {
    "id": "c1",
    "name": "PT Acme Lingkungan",
    "industry": "Daur Ulang",
    "lead_id": "l1",
    "lead_status": "qualified",
    "analysis_id": "a1",
    "analysis_lead_score": 78,
    "analysis_category": "HIGH",
    "analysis_potential_products": ["Mesin pencacah sampah"],
}


# --- fungsi murni ---

def test_build_list_filters_basic():
    f = build_list_filters(q="sampah", status="qualified", category="high")
    assert f["lead_status"] == "eq.qualified"
    assert f["analysis_category"] == "eq.HIGH"
    assert f["or"] == "(name.ilike.*sampah*,description.ilike.*sampah*,website.ilike.*sampah*)"


def test_build_list_filters_sanitizes():
    f = build_list_filters(q="a(b),c*")
    assert f["or"] == "(name.ilike.*a b c*,description.ilike.*a b c*,website.ilike.*a b c*)"


def test_build_list_params_sort_by_score_uses_view_column():
    params, filters = build_list_params(page=2, per_page=10, sort="lead_score", status="qualified")
    assert "analysis_lead_score" in params["select"]
    assert params["order"] == "analysis_lead_score.desc.nullslast"
    assert params["offset"] == "10" and filters["lead_status"] == "eq.qualified"


def test_shape_lead_flattens():
    shaped = shape_lead(dict(VIEW_ROW))
    assert shaped["lead"]["status"] == "qualified"
    assert shaped["analysis"]["category"] == "HIGH"
    assert shaped["analysis"]["lead_score"] == 78
    assert "analysis_id" not in shaped and "lead_id" not in shaped
    assert shape_lead({"id": "x"})["analysis"] is None


# --- endpoint ---

def test_leads_list_requires_auth(make_client):
    assert make_client(RouterDB()).get("/api/leads").status_code == 401


def test_leads_list_shapes(make_client):
    c = make_client(RouterDB(view=[VIEW_ROW]))
    r = c.get("/api/leads", headers=auth("tok-staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["analysis"]["category"] == "HIGH"


def test_discover_requires_input(make_client):
    c = make_client(RouterDB())
    assert c.post("/api/leads/discover", json={}, headers=auth("tok-staff")).status_code == 400


def test_discover_calls_service(make_client, monkeypatch):
    called = {}

    def fake_discover(db, settings, **kwargs):
        called.update(kwargs)
        return {"found": 1, "created": 1, "duplicates": 0, "failed": 0, "results": [], "errors": []}

    monkeypatch.setattr(leads_router.leads_service, "discover", fake_discover)
    c = make_client(RouterDB())
    r = c.post("/api/leads/discover", json={"urls": ["acme.co.id"]}, headers=auth("tok-staff"))
    assert r.status_code == 200 and r.json()["created"] == 1
    assert called["urls"] == ["acme.co.id"]


def test_qualify_without_key_returns_503(make_client, monkeypatch):
    monkeypatch.setattr(leads_router, "get_settings", lambda: Settings(groq_api_key=""))
    c = make_client(RouterDB(companies=[{"id": "c1", "name": "PT Acme"}]))
    assert c.post("/api/leads/c1/qualify", headers=auth("tok-staff")).status_code == 503


def test_update_lead_rejects_bad_status(make_client):
    c = make_client(RouterDB())
    r = c.patch("/api/leads/c1", json={"status": "kacau"}, headers=auth("tok-staff"))
    assert r.status_code == 400


def test_delete_lead_requires_admin(make_client):
    c = make_client(RouterDB())
    assert c.delete("/api/leads/c1", headers=auth("tok-staff")).status_code == 403
    assert c.delete("/api/leads/c1", headers=auth("tok-admin")).status_code == 200


def test_lead_detail_returns_relations(make_client):
    c = make_client(
        RouterDB(
            companies=[{"id": "c1", "name": "PT Acme"}],
            leads=[{"id": "l1", "company_id": "c1", "status": "new"}],
            contacts=[{"id": "k1", "contact_type": "email", "value": "a@acme.co.id", "source_url": "x"}],
            analysis=[{"id": "a1", "is_current": True, "lead_score": 70, "category": "HIGH"}],
        )
    )
    r = c.get("/api/leads/c1", headers=auth("tok-staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["company"]["name"] == "PT Acme"
    assert body["analysis"]["category"] == "HIGH"
    assert body["contacts"][0]["value"] == "a@acme.co.id"
