import pytest
from fastapi import HTTPException

from app.deps import require_role


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_health_open(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_invalid_token(client):
    assert client.get("/api/auth/me", headers=auth("bad")).status_code == 401


def test_me_ok(client):
    r = client.get("/api/auth/me", headers=auth("tok-admin"))
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_inactive_user_forbidden(client):
    assert client.get("/api/auth/me", headers=auth("tok-off")).status_code == 403


def test_overview_empty_db_returns_zero_not_dummy(client):
    r = client.get("/api/dashboard/overview", headers=auth("tok-staff"))
    assert r.status_code == 200
    d = r.json()
    assert d["tenders_total"] == 0 and d["recent_activity"] == []
    assert set(d["outreach"]) == {"draft", "saved_for_later", "approved", "sent", "failed"}


def test_overview_requires_auth(client):
    assert client.get("/api/dashboard/overview").status_code == 401


def test_require_role():
    checker = require_role("admin")
    with pytest.raises(HTTPException) as e:
        checker(user={"role": "staff"})
    assert e.value.status_code == 403
    assert checker(user={"role": "admin"})["role"] == "admin"


def test_overview_has_new_sections(client):
    d = client.get("/api/dashboard/overview", headers=auth("tok-staff")).json()
    assert d["tenders_deadline_7d"] == 0
    assert len(d["weekly_tenders"]) == 7 and all(w["count"] == 0 for w in d["weekly_tenders"])
    assert d["top_tenders"] == [] and d["sources"] == []


def test_weekly_buckets_use_local_timezone():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.routers.dashboard import weekly_tenders

    class Rows:
        def select(self, table, params=None):
            return [
                {"first_seen_at": "2026-11-16T02:00:00Z"},  # 09.00 WIB tgl 16
                {"first_seen_at": "2026-11-15T18:00:00Z"},  # 01.00 WIB tgl 16
                {"first_seen_at": "2026-11-12T05:00:00Z"},
            ]

    tz = ZoneInfo("Asia/Jakarta")
    out = weekly_tenders(Rows(), tz, now=datetime(2026, 11, 16, 10, 0, tzinfo=tz))
    by = {w["date"]: w["count"] for w in out}
    assert len(out) == 7 and by["2026-11-16"] == 2 and by["2026-11-12"] == 1
