"""Uji handler Fase 4 dengan layanan Phase 2/3 di-mock (tanpa jaringan/AI/email)."""
import pytest

from app.automation import handlers
from app.automation.errors import JobError
from app.config import Settings
from tests.fakes import AutomationDB


def settings(**kw) -> Settings:
    base = dict(scheduler_enabled=False, automation_notify_email=False, groq_api_key="")
    base.update(kw)
    return Settings(**base)


def make_config(automation_type: str, **over) -> dict:
    cfg = {
        "id": "cfg-1",
        "automation_name": automation_type,
        "automation_type": automation_type,
        "is_enabled": True,
        "schedule_type": "weekly",
        "schedule_config": {"day_of_week": 0, "hour": 8, "minute": 0},
        "timezone": "Asia/Jakarta",
        "params": {},
        "retry_max_attempts": 1,
        "retry_backoff_seconds": 60,
        "timeout_seconds": 900,
    }
    cfg.update(over)
    return cfg


class FakeCtx:
    """Konteks palsu: merekam log/progress/notifikasi tanpa menyentuh DB nyata."""

    def __init__(self, db, settings_, config):
        self.db = db
        self.settings = settings_
        self.config = config
        self.job = {"id": "job-1", "job_type": config["automation_type"]}
        self.logs: list = []
        self.progresses: list = []
        self.notifications: list = []

    def check(self):
        return None

    def log(self, level, message, metadata=None):
        self.logs.append((level, message))

    def progress(self, pct, **kw):
        self.progresses.append((pct, kw))

    def notify(self, notification_type, title, message, **kw):
        self.notifications.append((notification_type, title, kw))
        return None


# --- A. Tender Monitoring ---

def test_tender_monitoring_aggregates(monkeypatch):
    db = AutomationDB({})
    monkeypatch.setattr(handlers.collection, "collect_all", lambda db, settings_: {
        "sources_total": 2,
        "sources_ok": 1,
        "upserted_total": 5,
        "sources": [{"status": "ok", "upserted": 5}, {"status": "blocked", "upserted": 0}],
    })
    monkeypatch.setattr(handlers.analysis_service, "analyze_pending",
                        lambda db, settings_, limit: {"analyzed": 4, "failed": 1, "results": []})
    ctx = FakeCtx(db, settings(groq_api_key="k"), make_config("tender_monitoring"))

    out = handlers.tender_monitoring(ctx)

    assert out["total"] == 5
    assert out["analyzed"] == 4
    assert out["failed"] == 2  # 1 sumber blocked + 1 gagal analisis
    assert any(n[0] == "tender_new" for n in ctx.notifications)


def test_tender_monitoring_without_ai_key_still_collects(monkeypatch):
    db = AutomationDB({})
    called = {"analyze": False}
    monkeypatch.setattr(handlers.collection, "collect_all", lambda db, settings_: {
        "sources_total": 1, "sources_ok": 1, "upserted_total": 3,
        "sources": [{"status": "ok", "upserted": 3}],
    })

    def _analyze(db, settings_, limit):
        called["analyze"] = True
        return {"analyzed": 0, "failed": 0, "results": []}

    monkeypatch.setattr(handlers.analysis_service, "analyze_pending", _analyze)
    ctx = FakeCtx(db, settings(groq_api_key=""), make_config("tender_monitoring"))

    out = handlers.tender_monitoring(ctx)

    assert out["total"] == 3 and out["failed"] == 0
    assert called["analyze"] is False  # dilewati tanpa kunci AI
    assert any(level == "warning" for level, _ in ctx.logs)


# --- B. Company Discovery ---

def test_company_discovery_requires_search_key():
    db = AutomationDB({})
    ctx = FakeCtx(db, settings(lead_search_provider="none", lead_search_api_key=""), make_config("company_discovery"))
    with pytest.raises(JobError):
        handlers.company_discovery(ctx)


def test_company_discovery_aggregates(monkeypatch):
    db = AutomationDB({})
    monkeypatch.setattr(handlers.leads_service, "discover",
                        lambda db, settings_, **kw: {"found": 2, "created": 1, "duplicates": 1, "failed": 0, "results": []})
    ctx = FakeCtx(db, settings(lead_search_provider="tavily", lead_search_api_key="k"),
                  make_config("company_discovery", params={"queries": ["solar panel"], "limit": 5}))

    out = handlers.company_discovery(ctx)

    assert out["total"] == 2 and out["success"] == 1 and out["duplicates"] == 1
    assert any(n[0] == "lead_new" for n in ctx.notifications)


def test_company_discovery_falls_back_to_active_keywords(monkeypatch):
    db = AutomationDB({"tender_keywords": [{"keyword": "panel surya", "is_active": True}]})
    seen = {}
    monkeypatch.setattr(handlers.leads_service, "discover",
                        lambda db, settings_, **kw: (seen.update(kw), {"found": 0, "created": 0, "duplicates": 0, "failed": 0})[1])
    ctx = FakeCtx(db, settings(lead_search_provider="tavily", lead_search_api_key="k"),
                  make_config("company_discovery", params={}))

    handlers.company_discovery(ctx)

    assert seen.get("query") == "panel surya"


# --- C. Lead Qualification ---

def test_lead_qualification_requires_ai_key():
    db = AutomationDB({})
    ctx = FakeCtx(db, settings(groq_api_key=""), make_config("lead_qualification"))
    with pytest.raises(JobError):
        handlers.lead_qualification(ctx)


def test_lead_qualification_counts_high_priority(monkeypatch):
    db = AutomationDB({})
    monkeypatch.setattr(handlers.lead_analysis_service, "analyze_pending", lambda db, settings_, limit: {
        "analyzed": 2, "failed": 1,
        "results": [
            {"status": "ok", "category": "HIGH", "lead_score": 92},
            {"status": "ok", "category": "LOW", "lead_score": 12},
            {"status": "error", "error": "x"},
        ],
    })
    ctx = FakeCtx(db, settings(groq_api_key="k"), make_config("lead_qualification"))

    out = handlers.lead_qualification(ctx)

    assert out["total"] == 3 and out["success"] == 2 and out["high"] == 1
    assert any(n[0] == "lead_high_priority" for n in ctx.notifications)


# --- D. Outreach Draft Generation ---

def test_outreach_requires_ai_key():
    db = AutomationDB({})
    ctx = FakeCtx(db, settings(groq_api_key=""), make_config("outreach_draft_generation"))
    with pytest.raises(JobError):
        handlers.outreach_draft_generation(ctx)


def test_outreach_skips_lead_without_email():
    db = AutomationDB({
        "leads_with_analysis": [{
            "id": "c1", "name": "PT A", "lead_id": "l1",
            "lead_status": "qualified", "analysis_category": "HIGH", "analysis_lead_score": 90,
        }],
        "company_contacts": [],
    })
    ctx = FakeCtx(db, settings(groq_api_key="k"), make_config("outreach_draft_generation"))

    out = handlers.outreach_draft_generation(ctx)

    assert out["success"] == 0 and out["skipped_no_email"] == 1


def test_outreach_creates_draft_and_never_sends(monkeypatch):
    db = AutomationDB({
        "leads_with_analysis": [{
            "id": "c1", "name": "PT A", "lead_id": "l1",
            "lead_status": "qualified", "analysis_category": "HIGH", "analysis_lead_score": 90,
        }],
        "company_contacts": [{"company_id": "c1", "contact_type": "email", "value": "a@x.id"}],
    })
    sent = {"n": 0}
    monkeypatch.setattr(handlers.outreach_service, "generate_draft",
                        lambda db, settings_, values: {"id": "m1", "status": "draft", **values})
    # Pastikan tidak ada pemanggilan pengiriman.
    monkeypatch.setattr(handlers.outreach_service, "send_message",
                        lambda *a, **k: sent.__setitem__("n", sent["n"] + 1), raising=False)
    ctx = FakeCtx(db, settings(groq_api_key="k"), make_config("outreach_draft_generation"))

    out = handlers.outreach_draft_generation(ctx)

    assert out["success"] == 1 and sent["n"] == 0
    assert "tidak ada email yang dikirim" in out["message"].lower()
    assert any(n[0] == "outreach_draft_ready" for n in ctx.notifications)


def test_outreach_skips_existing_draft(monkeypatch):
    db = AutomationDB({
        "leads_with_analysis": [{
            "id": "c1", "name": "PT A", "lead_id": "l1",
            "lead_status": "qualified", "analysis_category": "HIGH", "analysis_lead_score": 90,
        }],
        "company_contacts": [{"company_id": "c1", "contact_type": "email", "value": "a@x.id"}],
        "outreach_messages": [{
            "id": "m0", "lead_id": "l1", "email_type": "company_intro", "language": "id", "status": "draft",
        }],
    })
    called = {"n": 0}
    monkeypatch.setattr(handlers.outreach_service, "generate_draft",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    ctx = FakeCtx(db, settings(groq_api_key="k"), make_config("outreach_draft_generation"))

    out = handlers.outreach_draft_generation(ctx)

    assert out["success"] == 0 and out["skipped_duplicate"] == 1 and called["n"] == 0
