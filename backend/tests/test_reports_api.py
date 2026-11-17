"""Uji router Reports: agregasi ringkasan lintas modul + ekspor Excel/PDF."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import SupabaseError
from app.deps import get_db
from app.main import app
from app.routers.reports import _counts, _job_duration, _trend

USERS = {
    "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
    "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
}


class ReportDB:
    """Fake DB: mengembalikan tabel apa adanya, dapat dipaksa gagal per tabel."""

    def __init__(self, tables=None, fail=()):
        self.data = tables or {}
        self.fail = set(fail)

    def get_user(self, token):
        u = USERS.get(token)
        return {"id": u["id"]} if u else None

    def select(self, table, params=None):
        if table in self.fail:
            raise SupabaseError(
                f"select {table} gagal (404): {{\"code\":\"PGRST205\",\"message\":\"Could not find the table\"}}"
            )
        rows = list(self.data.get(table, []))
        if table == "users" and params and params.get("id"):
            uid = params["id"].removeprefix("eq.")
            rows = [u for u in rows if u["id"] == uid]
        return rows

    def count(self, table, filters=None, select="id"):
        return len(self.data.get(table, []))

    def with_fail(self, *tables):
        """Salinan DB yang memaksa tabel tertentu memunculkan galat 'tabel tidak ada'."""
        return ReportDB(self.data, tables)


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def make_client():
    def _make(db):
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sample_db(**overrides) -> ReportDB:
    now = datetime.now(timezone.utc)
    tables = {
        "users": list(USERS.values()),
        "tenders_with_analysis": [
            {
                "id": "t1", "package_name": "Paket A", "agency": "DLH", "status": "Berjalan",
                "source_id": "s1", "first_seen_at": _iso(now - timedelta(days=1)),
                "bid_deadline": _iso(now + timedelta(days=3)), "analysis_id": "a1",
                "analysis_priority": "HIGH", "analysis_category": "Waste Management",
                "analysis_relevance_score": 90,
            },
            {
                "id": "t2", "package_name": "Paket B", "agency": "PU", "status": "Berjalan",
                "source_id": "s2", "first_seen_at": _iso(now - timedelta(days=2)),
                "bid_deadline": _iso(now + timedelta(days=40)), "analysis_id": None,
            },
        ],
        "tender_sources": [{"id": "s1", "name": "SPSE"}, {"id": "s2", "name": "SIRUP"}],
        "leads_with_analysis": [
            {
                "id": "l1", "name": "PT Hijau", "industry": "Recycling", "city": "Bandung",
                "lead_status": "won", "created_at": _iso(now - timedelta(days=1)),
                "analysis_id": "la1", "analysis_lead_score": 88, "analysis_category": "HIGH",
            },
            {
                "id": "l2", "name": "PT Biru", "industry": "Waste", "city": "Jakarta",
                "lead_status": "new", "created_at": _iso(now - timedelta(days=3)),
                "analysis_id": None,
            },
        ],
        "outreach_messages": [
            {
                "id": "o1", "status": "sent", "email_type": "company_intro", "language": "id",
                "campaign_id": "c1", "created_at": _iso(now - timedelta(days=1)), "sent_at": _iso(now),
            },
            {
                "id": "o2", "status": "draft", "email_type": "follow_up", "language": "en",
                "campaign_id": "c1", "created_at": _iso(now),
            },
        ],
        "outreach_campaigns": [{"id": "c1", "name": "Kampanye A"}],
        "automation_jobs": [
            {
                "id": "j1", "job_type": "lead_qualification", "job_name": "Lead Qualification",
                "status": "completed", "trigger_type": "manual",
                "started_at": _iso(now - timedelta(seconds=30)), "completed_at": _iso(now),
                "created_at": _iso(now), "total_processed": 5, "success_count": 5, "failed_count": 0,
                "attempt": 1, "max_attempts": 3,
            },
            {
                "id": "j2", "job_type": "tender_monitoring", "job_name": "Tender Monitoring",
                "status": "failed", "trigger_type": "scheduled",
                "started_at": _iso(now - timedelta(seconds=10)), "completed_at": _iso(now),
                "created_at": _iso(now), "total_processed": 0, "success_count": 0, "failed_count": 0,
                "attempt": 3, "max_attempts": 3, "error_message": "boom",
            },
        ],
        "automation_configs": [
            {
                "id": "cfg1", "automation_name": "Lead Qualification",
                "automation_type": "lead_qualification", "is_enabled": True, "last_status": "completed",
                "last_run_at": _iso(now), "next_run_at": _iso(now + timedelta(days=7)),
                "cron_expression": "0 10 * * 2", "timezone": "Asia/Jakarta",
            },
        ],
    }
    tables.update(overrides)
    return ReportDB(tables)


# --- fungsi murni ---

def test_counts_defaults_and_blank_label():
    rows = [{"s": "a"}, {"s": "a"}, {"s": None}, {}]
    out = _counts(rows, "s", ("a", "b"), blank="kosong")
    assert out == {"a": 2, "b": 0, "kosong": 2}


def test_trend_fills_zero_days():
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Jakarta")
    now = datetime.now(tz)
    rows = [{"at": now.isoformat()}, {"at": (now - timedelta(days=2)).isoformat()}]
    trend = _trend(rows, "at", 5, tz)
    assert len(trend) == 5
    assert sum(p["count"] for p in trend) == 2
    assert trend[-1]["count"] == 1


def test_job_duration_from_timestamps():
    assert _job_duration({"started_at": "2026-11-17T10:00:00Z", "completed_at": "2026-11-17T10:00:45Z"}) == 45
    assert _job_duration({"started_at": "2026-11-17T10:00:00Z"}) is None


# --- endpoint ---

def test_summary_requires_auth(make_client):
    c = make_client(sample_db())
    assert c.get("/api/reports/summary").status_code == 401


def test_summary_aggregates_all_sections(make_client):
    c = make_client(sample_db())
    r = c.get("/api/reports/summary?days=30", headers=auth("tok-staff"))
    assert r.status_code == 200
    b = r.json()
    assert b["period_days"] == 30

    t = b["tenders"]
    assert t["available"] and t["total"] == 2 and t["analyzed"] == 1 and t["unanalyzed"] == 1
    assert t["high_priority"] == 1 and t["deadline_7d"] == 1
    assert t["by_priority"]["HIGH"] == 1 and t["by_priority"]["Belum dianalisis"] == 1
    assert {s["source"] for s in t["by_source"]} == {"SPSE", "SIRUP"}
    assert t["top"][0]["id"] == "t1" and t["top"][0]["relevance_score"] == 90

    l = b["leads"]
    assert l["total"] == 2 and l["won"] == 1 and l["high_potential"] == 1
    assert l["conversion_rate"] == 50.0 and l["by_status"]["new"] == 1

    o = b["outreach"]
    assert o["total"] == 2 and o["sent"] == 1 and o["pending_approval"] == 1
    assert o["send_success_rate"] == 100.0 and o["by_email_type"]["follow_up"] == 1

    a = b["automation"]
    assert a["total_jobs"] == 2 and a["success_rate"] == 50.0
    assert len(a["by_type"]) == 2
    assert a["recent_failures"][0]["error_message"] == "boom"
    assert a["configs"][0]["automation_name"] == "Lead Qualification"


def test_summary_degrades_when_automation_table_missing(make_client):
    c = make_client(sample_db().with_fail("automation_jobs"))
    r = c.get("/api/reports/summary", headers=auth("tok-admin"))
    assert r.status_code == 200
    b = r.json()
    assert b["automation"]["available"] is False
    assert "PGRST205" in b["automation"]["error"]
    assert b["tenders"]["available"] is True


def test_export_xlsx_returns_workbook(make_client):
    c = make_client(sample_db())
    r = c.get("/api/reports/export.xlsx?days=7", headers=auth("tok-staff"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.content[:2] == b"PK"
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert {"Ringkasan", "Tender", "Leads", "Outreach", "Automation"} <= set(wb.sheetnames)


def test_export_pdf_returns_pdf(make_client):
    c = make_client(sample_db())
    r = c.get("/api/reports/export.pdf?days=30", headers=auth("tok-staff"))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_pdf_handles_missing_section(make_client):
    c = make_client(sample_db().with_fail("outreach_messages"))
    r = c.get("/api/reports/export.pdf", headers=auth("tok-staff"))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
