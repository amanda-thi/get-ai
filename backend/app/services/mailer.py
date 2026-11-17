"""Pengiriman email via SMTP (stdlib smtplib). Kredensial HANYA di backend.

Tanpa konfigurasi SMTP, pengiriman gagal dengan pesan jelas — draft tetap bisa
dibuat & disimpan, jadi alur kerja tidak terblokir.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from ..config import Settings


class MailError(Exception):
    """Gagal mengirim email (SMTP belum dikonfigurasi, auth gagal, jaringan, dsb.)."""


def send_email(
    settings: Settings,
    *,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> str:
    """Kirim satu email. Mengembalikan Message-ID. MailError bila gagal."""
    if not settings.smtp_configured:
        raise MailError(
            "SMTP belum dikonfigurasi (SMTP_HOST/SMTP_FROM). Email tersimpan sebagai draft; "
            "isi variabel SMTP_* di .env untuk mengaktifkan pengiriman."
        )
    if not to or "@" not in to:
        raise MailError("Alamat email tujuan tidak valid")

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout) as smtp:
            smtp.ehlo()
            if settings.smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Pengiriman gagal: {e}") from e
    return str(msg["Message-ID"])
