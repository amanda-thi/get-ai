"""Uji router tender: filter/params (murni), listing, detail, export, collect, analyze."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_db
from app.main import app
from app.routers import tenders as tenders_router
from app.routers.tenders import build_list_filters, build_list_params, shape_tender

USERS = {
    "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
    "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
}


class RouterDB:
    def __init__(self, *, tenders=None, view=None, sources=None, keywords=None, analysis=None):
        self.data = {
            "users": list(USERS.values()),
            "tenders": tenders or [],
            "tenders_with_analysis": view or [],
            "tender_sources": sources or [],
            "tender_keywords": keywords or [],
            "tender_analysis": analysis or [],
            "system_logs": [],
        }
        self.inserted, self.updates, self.deleted = [], [], []

    def get_user(self, token):
        u = USERS.get(token)
        return {"id": u["id"]} if u else None

    def select(self, table, params=None):
        rows = list(self.data.get(table, []))
        if table == "users" and params and params.get("id"):
            uid = params["id"].removeprefix("eq.")
            rows = [u for u in rows if u["id"] == uid]
        if table == "tenders" and params and params.get("id"):
            tid = params["id"].removeprefix("eq.")
            rows = [t for t in rows if t["id"] == tid]
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


TENDER_ROW = {
    "id": "t1",
    "package_name": "Pengadaan Mesin Pencacah Sampah",
    "agency": "DLH",
    "hps": 100000000,
    "tender_analysis": [{"relevance_score": 88, "priority": "HIGH", "is_current": True}],
}

# Baris view `tenders_with_analysis`: analisis terkini sudah diratakan sebagai kolom.
VIEW_ROW = {
    "id": "t1",
    "package_name": "Pengadaan Mesin Pencacah Sampah",
    "agency": "DLH",
    "hps": 100000000,
    "analysis_id": "a1",
    "analysis_priority": "HIGH",
    "analysis_relevance_score": 88,
    "analysis_category": "Waste Management",
}


# --- fungsi murni ---

def test_build_list_filters_basic():
    f = build_list_filters(q="sampah", source_id="s1", status="Berjalan")
    assert f["or"] == "(package_name.ilike.*sampah*,agency.ilike.*sampah*)"
    assert f["source_id"] == "eq.s1" and f["status"] == "ilike.*Berjalan*"
    assert not any(k.startswith("tender_analysis") for k in f)


def test_build_list_filters_sanitizes_input():
    f = build_list_filters(q="a(b),c*")
    assert f["or"] == "(package_name.ilike.*a b c*,agency.ilike.*a b c*)"


def test_build_list_filters_priority_and_category_use_view_columns():
    f = build_list_filters(priority="high", category="Waste Management")
    assert f["analysis_priority"] == "eq.HIGH"
    assert f["analysis_category"] == "eq.Waste Management"


def test_build_list_filters_date_range():
    f = build_list_filters(date_from="2026-01-01", date_to="2026-12-31")
    assert f["and"] == "(announced_at.gte.2026-01-01,announced_at.lte.2026-12-31)"


def test_build_list_params_sort_by_relevance_uses_view_column():
    params, filters = build_list_params(page=2, per_page=10, sort="relevance_score", priority="HIGH")
    assert "analysis_relevance_score" in params["select"]
    assert "tender_analysis" not in params["select"]
    assert params["order"] == "analysis_relevance_score.desc.nullslast"
    assert params["limit"] == "10" and params["offset"] == "10"
    assert filters["analysis_priority"] == "eq.HIGH"


def test_shape_tender_flattens_view_columns():
    shaped = shape_tender({"id": "x", "analysis_id": "a1", "analysis_priority": "LOW", "analysis_relevance_score": 50})
    assert shaped["analysis"]["priority"] == "LOW"
    assert shaped["analysis"]["relevance_score"] == 50
    assert "analysis_id" not in shaped
    assert shape_tender({"id": "x"})["analysis"] is None


# --- endpoint ---

def test_tenders_list_requires_auth(make_client):
    c = make_client(RouterDB())
    assert c.get("/api/tenders").status_code == 401


def test_tenders_list_shapes_analysis(make_client):
    c = make_client(RouterDB(view=[VIEW_ROW]))
    r = c.get("/api/tenders", headers=auth("tok-staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["pages"] == 1
    assert body["items"][0]["analysis"]["priority"] == "HIGH"


def test_tenders_detail_ok_and_404(make_client):
    row = {"id": "t1", "package_name": "X", "tender_analysis": [
        {"id": "a2", "is_current": True, "created_at": "2026-11-10T00:00:00Z", "priority": "HIGH"},
        {"id": "a1", "is_current": False, "created_at": "2026-11-09T00:00:00Z", "priority": "LOW"},
    ]}
    c = make_client(RouterDB(tenders=[row]))
    r = c.get("/api/tenders/t1", headers=auth("tok-staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["id"] == "a2" and len(body["analysis_history"]) == 2
    assert c.get("/api/tenders/missing", headers=auth("tok-staff")).status_code == 404


def test_tenders_export_returns_xlsx(make_client):
    c = make_client(RouterDB(view=[VIEW_ROW]))
    r = c.get("/api/tenders/export", headers=auth("tok-staff"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.content[:2] == b"PK"  # berkas xlsx = arsip zip


def test_collect_calls_service(make_client, monkeypatch):
    called = {}

    def fake_collect_all(db, settings, *, source_ids=None, keywords=None, options=None):
        called["options"] = options
        return {"keywords_used": 0, "sources_total": 0, "sources_ok": 0, "upserted_total": 0, "sources": []}

    monkeypatch.setattr(tenders_router.collection, "collect_all", fake_collect_all)
    c = make_client(RouterDB())
    r = c.post("/api/tenders/collect", json={"years": [2026], "max_rows": 50}, headers=auth("tok-staff"))
    assert r.status_code == 200
    assert called["options"] == {"years": [2026], "max_rows": 50}


def test_analyze_without_key_returns_503(make_client, monkeypatch):
    monkeypatch.setattr(tenders_router, "get_settings", lambda: Settings(groq_api_key="", openai_api_key=""))
    c = make_client(RouterDB(tenders=[TENDER_ROW]))
    assert c.post("/api/tenders/t1/analyze", headers=auth("tok-staff")).status_code == 503
    assert c.post("/api/tenders/analyze-pending", json={"limit": 5}, headers=auth("tok-staff")).status_code == 503
