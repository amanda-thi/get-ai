"""Orkestrasi Marketing Outreach (Fase 3): template, campaign, pesan, approve, kirim.

Aturan aman: email hanya boleh dikirim setelah disetujui admin (constraint DB juga
menjamin `approved`/`sent` punya `approved_by`+`approved_at`). Draft tetap bisa
dibuat tanpa SMTP. Semua kejadian dicatat di `outreach_logs`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..ai.outreach_service import generate_email
from ..config import Settings
from ..db import SupabaseClient, SupabaseError
from .collection import log_event
from .mailer import MailError, send_email

EVENT_TYPES = (
    "created", "edited", "approved", "sent", "failed",
    "delivered", "replied", "follow_up_scheduled", "note",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_outreach(
    db: SupabaseClient, message_id: str, event_type: str, details: dict | None = None, user_id: str | None = None
) -> None:
    """Catat kejadian outreach; kegagalan log tidak menggagalkan aksi utama."""
    if event_type not in EVENT_TYPES:
        event_type = "note"
    try:
        db.insert(
            "outreach_logs",
            {"message_id": message_id, "event_type": event_type, "details": details or {}, "created_by": user_id},
            returning=False,
        )
    except SupabaseError as e:  # pragma: no cover - jalur error I/O
        log_event(db, "warning", "outreach", f"Gagal menulis outreach_logs: {e}", {"message_id": message_id})


def get_message(db: SupabaseClient, message_id: str) -> dict | None:
    rows = db.select("outreach_messages", {"select": "*", "id": f"eq.{message_id}", "limit": "1"})
    return rows[0] if rows else None


def create_message(db: SupabaseClient, values: dict, *, user_id: str | None = None) -> dict:
    """Simpan email baru (default status 'draft') lalu catat 'created'."""
    row = {
        "campaign_id": values.get("campaign_id"),
        "lead_id": values.get("lead_id"),
        "contact_id": values.get("contact_id"),
        "email_type": values["email_type"],
        "language": values["language"],
        "recipient_email": values.get("recipient_email"),
        "subject": values["subject"],
        "body": values["body"],
        "status": values.get("status") or "draft",
        "template_id": values.get("template_id"),
        "ai_model": values.get("ai_model"),
    }
    rows = db.insert("outreach_messages", row)
    message = rows[0] if rows else row
    log_outreach(db, message["id"], "created", {"email_type": row["email_type"], "language": row["language"]}, user_id)
    return message


def update_message(db: SupabaseClient, message_id: str, values: dict, *, user_id: str | None = None) -> dict:
    """Ubah isi/status draft. Tidak boleh mengubah email yang sudah terkirim."""
    msg = get_message(db, message_id)
    if not msg:
        raise LookupError("Email tidak ditemukan")
    if msg["status"] == "sent":
        raise ValueError("Email yang sudah terkirim tidak dapat diubah")
    allowed = {
        k: values[k]
        for k in ("subject", "body", "language", "email_type", "recipient_email", "contact_id", "campaign_id")
        if k in values and values[k] is not None
    }
    if not allowed:
        return msg
    rows = db.update("outreach_messages", {"id": f"eq.{message_id}"}, allowed)
    log_outreach(db, message_id, "edited", {"fields": sorted(allowed)}, user_id)
    return rows[0] if rows else {**msg, **allowed}


def set_status(db: SupabaseClient, message_id: str, status: str, *, user_id: str | None = None) -> dict:
    """Ubah status draft (saved_for_later / draft)."""
    if status not in ("draft", "saved_for_later"):
        raise ValueError("Status hanya boleh 'draft' atau 'saved_for_later' di sini")
    msg = get_message(db, message_id)
    if not msg:
        raise LookupError("Email tidak ditemukan")
    if msg["status"] in ("approved", "sent"):
        raise ValueError("Email yang sudah disetujui/terkirim tidak dapat diubah statusnya")
    rows = db.update("outreach_messages", {"id": f"eq.{message_id}"}, {"status": status})
    log_outreach(db, message_id, "note", {"status": status}, user_id)
    return rows[0] if rows else {**msg, "status": status}


def approve_message(db: SupabaseClient, message_id: str, *, user_id: str) -> dict:
    """Setujui email (admin). Menandai approved_by + approved_at (wajib oleh constraint DB)."""
    msg = get_message(db, message_id)
    if not msg:
        raise LookupError("Email tidak ditemukan")
    if msg["status"] == "sent":
        raise ValueError("Email sudah terkirim")
    now = _now_iso()
    rows = db.update(
        "outreach_messages",
        {"id": f"eq.{message_id}"},
        {"status": "approved", "approved_by": user_id, "approved_at": now},
    )
    log_outreach(db, message_id, "approved", {"approved_by": user_id}, user_id)
    return rows[0] if rows else {**msg, "status": "approved"}


def send_message(db: SupabaseClient, message_id: str, settings: Settings, *, user_id: str) -> dict:
    """Kirim email yang SUDAH disetujui via SMTP. Catat 'sent'/'failed'."""
    msg = get_message(db, message_id)
    if not msg:
        raise LookupError("Email tidak ditemukan")
    if msg["status"] != "approved":
        raise ValueError("Email harus disetujui admin sebelum dikirim")

    to = msg.get("recipient_email")
    if not to and msg.get("contact_id"):
        rows = db.select(
            "company_contacts",
            {"select": "value,contact_type", "id": f"eq.{msg['contact_id']}", "limit": "1"},
        )
        if rows and rows[0]["contact_type"] == "email":
            to = rows[0]["value"]

    try:
        provider_id = send_email(settings, to=to, subject=msg["subject"], body=msg["body"])
    except MailError as e:
        db.update(
            "outreach_messages", {"id": f"eq.{message_id}"}, {"status": "failed", "error": str(e)}, returning=False
        )
        log_outreach(db, message_id, "failed", {"error": str(e)}, user_id)
        raise

    db.update(
        "outreach_messages",
        {"id": f"eq.{message_id}"},
        {"status": "sent", "sent_at": _now_iso(), "provider_message_id": provider_id, "error": None, "recipient_email": to},
        returning=False,
    )
    log_outreach(db, message_id, "sent", {"to": to, "provider_message_id": provider_id}, user_id)
    if msg.get("lead_id"):
        db.update("company_leads", {"id": f"eq.{msg['lead_id']}"}, {"status": "contacted"}, returning=False)
    return {"status": "sent", "to": to, "provider_message_id": provider_id}


def _resolve_target(db: SupabaseClient, lead_id: str | None, company_id: str | None) -> tuple[dict | None, dict | None]:
    """Kembalikan (lead, company) dari lead_id atau company_id."""
    if lead_id:
        rows = db.select("company_leads", {"select": "id,company_id", "id": f"eq.{lead_id}", "limit": "1"})
        if rows:
            lead = rows[0]
            comp = db.select("companies", {"select": "*", "id": f"eq.{lead['company_id']}", "limit": "1"})
            return lead, (comp[0] if comp else None)
        return None, None
    if company_id:
        rows = db.select("company_leads", {"select": "id,company_id", "company_id": f"eq.{company_id}", "limit": "1"})
        lead = rows[0] if rows else None
        comp = db.select("companies", {"select": "*", "id": f"eq.{company_id}", "limit": "1"})
        return lead, (comp[0] if comp else None)
    return None, None


def generate_draft(
    db: SupabaseClient,
    settings: Settings,
    payload: dict,
    *,
    user_id: str | None = None,
    client=None,
) -> dict:
    """Buat email via AI untuk satu lead/perusahaan, simpan sebagai draft."""
    lead, company = _resolve_target(db, payload.get("lead_id"), payload.get("company_id"))
    if not company:
        raise LookupError("Perusahaan/lead tidak ditemukan")

    contacts = db.select(
        "company_contacts", {"select": "contact_type,value", "company_id": f"eq.{company['id']}"}
    )
    template = None
    if payload.get("template_id"):
        rows = db.select("email_templates", {"select": "*", "id": f"eq.{payload['template_id']}", "limit": "1"})
        template = rows[0] if rows else None

    result = generate_email(
        company,
        contacts,
        payload["email_type"],
        payload["language"],
        settings,
        instructions=payload.get("instructions"),
        template=template,
        client=client,
    )
    recipient = payload.get("recipient_email")
    if not recipient:
        recipient = next((c["value"] for c in contacts if c["contact_type"] == "email"), None)

    message = create_message(
        db,
        {
            "campaign_id": payload.get("campaign_id"),
            "lead_id": lead["id"] if lead else None,
            "contact_id": payload.get("contact_id"),
            "email_type": payload["email_type"],
            "language": payload["language"],
            "recipient_email": recipient,
            "subject": result["subject"],
            "body": result["body"],
            "status": "draft",
            "template_id": payload.get("template_id"),
            "ai_model": result["model"],
        },
        user_id=user_id,
    )
    message["prompt_version"] = result["prompt_version"]
    return message
