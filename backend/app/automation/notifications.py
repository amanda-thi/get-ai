"""Notifikasi internal (tabel `notifications`) + opsi email admin.

Aturan:
* Notifikasi otomatis bersifat **broadcast admin** (`user_id = NULL`).
* Dedupe memakai `dedupe_key` unik agar event yang sama tidak memicu notifikasi berulang.
* Email admin bersifat OPSIONAL (`AUTOMATION_NOTIFY_EMAIL=true` + SMTP siap). Kegagalan
  mengirim email tidak pernah menggagalkan job.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import Settings
from ..db import SupabaseClient, SupabaseError, is_conflict_error

log = logging.getLogger(__name__)

NOTIFICATION_TYPES = (
    "automation_completed",
    "automation_partial",
    "automation_failed",
    "job_failed_final",
    "tender_new",
    "tender_deadline",
    "lead_new",
    "lead_high_priority",
    "outreach_draft_ready",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_notification(
    db: SupabaseClient,
    *,
    notification_type: str,
    title: str,
    message: str,
    user_id: str | None = None,
    related_job_id: str | None = None,
    link: str | None = None,
    dedupe_key: str | None = None,
) -> dict | None:
    """Simpan notifikasi. Kembalikan None bila duplikat (dedupe) atau gagal simpan."""
    row = {
        "user_id": user_id,
        "notification_type": notification_type,
        "title": title,
        "message": message,
        "related_job_id": related_job_id,
        "link": link,
        "dedupe_key": dedupe_key,
    }
    try:
        rows = db.insert("notifications", row)
    except SupabaseError as e:
        if is_conflict_error(e):
            return None
        log.warning("gagal menulis notifikasi: %s", e)
        return None
    return rows[0] if rows else row


def admin_emails(db: SupabaseClient) -> list[str]:
    """Email admin aktif (untuk notifikasi email opsional)."""
    try:
        rows = db.select(
            "users",
            {"select": "email", "role": "eq.admin", "is_active": "eq.true"},
        )
    except SupabaseError as e:  # pragma: no cover - jalur error I/O
        log.warning("gagal membaca daftar admin: %s", e)
        return []
    return [r["email"] for r in rows if r.get("email")]


def maybe_email_admins(db: SupabaseClient, settings: Settings, subject: str, body: str) -> int:
    """Kirim notifikasi email ke admin bila diaktifkan & SMTP siap. Kembalikan jumlah terkirim."""
    if not getattr(settings, "automation_notify_email", False) or not settings.smtp_configured:
        return 0
    from ..services.mailer import MailError, send_email

    sent = 0
    for email in admin_emails(db):
        try:
            send_email(settings, to=email, subject=subject, body=body)
            sent += 1
        except MailError as e:  # pragma: no cover - jalur SMTP
            log.warning("gagal kirim email notifikasi ke %s: %s", email, e)
    return sent


__all__ = ["NOTIFICATION_TYPES", "create_notification", "admin_emails", "maybe_email_admins"]
