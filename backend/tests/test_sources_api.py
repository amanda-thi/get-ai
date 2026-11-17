"""Uji router sumber & keyword: daftar, health check, dan kontrol akses admin."""
import pytest
from fastapi.testclient import TestClient

from app.deps import get_db
from app.main import app
from app.routers import sources as sources_router
from app.sources.base import HealthResult

USERS = {
    "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
    "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
}


class RouterDB:
    def __init__(self, *, sources=None, keywords=None):
        self.data = {
            "users": list(USERS.values()),
            "tender_sources": sources or [],
            "tender_keywords": keywords or [],
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
        if table == "tender_sources" and params and params.get("id"):
            sid = params["id"].removeprefix("eq.")
            rows = [s for s in rows if s["id"] == sid]
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


SOURCE = {"id": "s1", "name": "SPSE Nasional", "adapter_type": "spse", "base_url": "https://spse.inaproc.id", "is_active": True}


class OkAdapter:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def health_check(self):
        return HealthResult(True, "ok", "datatable OK")


def test_sources_requires_auth(make_client):
    assert make_client(RouterDB()).get("/api/sources").status_code == 401


def test_list_sources(make_client):
    c = make_client(RouterDB(sources=[SOURCE]))
    r = c.get("/api/sources", headers=auth("tok-staff"))
    assert r.status_code == 200 and r.json()["sources"][0]["name"] == "SPSE Nasional"


def test_check_source_updates_health(make_client, monkeypatch):
    db = RouterDB(sources=[SOURCE])
    monkeypatch.setattr(sources_router, "build_adapter", lambda s, st, client=None: OkAdapter())
    c = make_client(db)
    r = c.post("/api/sources/s1/check", headers=auth("tok-staff"))
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert db.updates[-1]["values"]["health_status"] == "ok"
    assert db.inserted  # log system_logs


def test_check_unknown_source_404(make_client):
    c = make_client(RouterDB())
    assert c.post("/api/sources/nope/check", headers=auth("tok-staff")).status_code == 404


def test_keyword_create_requires_admin(make_client):
    c = make_client(RouterDB())
    body = {"keyword": "Mesin crusher", "category": "Industrial Machinery", "language": "id"}
    assert c.post("/api/keywords", json=body, headers=auth("tok-staff")).status_code == 403
    r = c.post("/api/keywords", json=body, headers=auth("tok-admin"))
    assert r.status_code == 200 and r.json()["keyword"] == "Mesin crusher"


def test_keyword_language_validation(make_client):
    c = make_client(RouterDB())
    body = {"keyword": "x", "category": "y", "language": "fr"}
    assert c.post("/api/keywords", json=body, headers=auth("tok-admin")).status_code == 422


def test_keyword_delete(make_client):
    db = RouterDB(keywords=[{"id": "k1", "keyword": "x", "category": "y", "language": "en", "is_active": True}])
    c = make_client(db)
    r = c.delete("/api/keywords/k1", headers=auth("tok-admin"))
    assert r.status_code == 200 and db.deleted[0]["filters"] == {"id": "eq.k1"}
    assert c.delete("/api/keywords/k1", headers=auth("tok-staff")).status_code == 403
