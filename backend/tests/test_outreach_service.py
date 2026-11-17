"""Uji layanan outreach & mailer (mock DB + SMTP palsu, tanpa jaringan nyata)."""
import json

import httpx
import pytest

from app.config import Settings
from app.services import mailer, outreach
from tests.fakes import RecordingDB

GOOD_EMAIL = {"subject": "Penawaran", "body": "Halo, kami PT Green Eco Teknologi."}


def ai_client(payload=GOOD_EMAIL):
    body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))


def test_mailer_without_config_raises():
    with pytest.raises(mailer.MailError) as e:
        mailer.send_email(Settings(smtp_host="", smtp_from=""), to="a@b.co.id", subject="s", body="b")
    assert "SMTP belum dikonfigurasi" in str(e.value)


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        self.user = user

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_mailer_sends_with_configured_smtp(monkeypatch):
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()
    s = Settings(smtp_host="smtp.test", smtp_from="no-reply@greeneco.co.id", smtp_user="u", smtp_password="p")
    mid = mailer.send_email(s, to="a@b.co.id", subject="Halo", body="Isi")
    assert mid.startswith("<") and mid.endswith(">")
    assert FakeSMTP.sent[-1]["To"] == "a@b.co.id"


def test_create_message_logs_created():
    db = RecordingDB()
    msg = outreach.create_message(
        db,
        {"email_type": "company_intro", "language": "id", "subject": "s", "body": "b"},
    )
    assert msg["status"] == "draft"
    assert db.inserted_in("outreach_logs")[0]["rows"][0]["event_type"] == "created"


def test_approve_requires_and_sets_approver():
    db = RecordingDB(tables={"outreach_messages": [{"id": "m1", "status": "draft"}]})
    outreach.approve_message(db, "m1", user_id="u1")
    upd = db.updates_in("outreach_messages")[0]
    assert upd["values"]["status"] == "approved"
    assert upd["values"]["approved_by"] == "u1" and upd["values"]["approved_at"]


def test_send_requires_approval():
    db = RecordingDB(tables={"outreach_messages": [{"id": "m1", "status": "draft", "subject": "s", "body": "b"}]})
    with pytest.raises(ValueError) as e:
        outreach.send_message(db, "m1", Settings(), user_id="u1")
    assert "disetujui" in str(e.value)


def test_send_success_marks_sent_and_contacted(monkeypatch):
    db = RecordingDB(
        tables={
            "outreach_messages": [
                {"id": "m1", "status": "approved", "subject": "s", "body": "b", "recipient_email": "a@b.co.id", "lead_id": "l1"}
            ]
        }
    )
    monkeypatch.setattr(outreach, "send_email", lambda s, **kw: "<mid@x>")
    out = outreach.send_message(db, "m1", Settings(), user_id="u1")
    assert out["status"] == "sent"
    assert db.updates_in("outreach_messages")[0]["values"]["status"] == "sent"
    assert db.updates_in("company_leads")[0]["values"]["status"] == "contacted"


def test_send_failure_marks_failed(monkeypatch):
    db = RecordingDB(
        tables={"outreach_messages": [{"id": "m1", "status": "approved", "subject": "s", "body": "b", "recipient_email": "a@b.co.id"}]}
    )

    def boom(s, **kw):
        raise mailer.MailError("koneksi ditolak")

    monkeypatch.setattr(outreach, "send_email", boom)
    with pytest.raises(mailer.MailError):
        outreach.send_message(db, "m1", Settings(), user_id="u1")
    assert db.updates_in("outreach_messages")[0]["values"]["status"] == "failed"


def test_generate_draft_persists_draft():
    db = RecordingDB(
        tables={
            "companies": [{"id": "c1", "name": "PT Acme", "industry": "Sampah"}],
            "company_leads": [{"id": "l1", "company_id": "c1"}],
            "company_contacts": [{"contact_type": "email", "value": "info@acme.co.id"}],
        }
    )
    s = Settings(groq_api_key="k")
    msg = outreach.generate_draft(
        db, s, {"company_id": "c1", "email_type": "company_intro", "language": "id"}, user_id="u1", client=ai_client()
    )
    assert msg["status"] == "draft"
    assert msg["recipient_email"] == "info@acme.co.id"
    assert db.inserted_in("outreach_messages")[0]["rows"][0]["ai_model"] == s.ai_model_name
