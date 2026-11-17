"""Pembuatan email outreach via AI (validasi output). Tidak menulis DB."""
from __future__ import annotations

from ..config import Settings
from .client import AIClient, AIError
from .outreach_prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt

MAX_SUBJECT = 300
MAX_BODY = 20000


def validate_email(raw) -> dict:
    if not isinstance(raw, dict):
        raise AIError("output AI bukan objek JSON")
    subject = str(raw.get("subject") or "").strip()[:MAX_SUBJECT]
    body = str(raw.get("body") or "").strip()[:MAX_BODY]
    if not subject or not body:
        raise AIError("output AI tidak punya subject/body")
    return {"subject": subject, "body": body}


def generate_email(
    company: dict,
    contacts: list[dict] | None,
    email_type: str,
    language: str,
    settings: Settings,
    *,
    instructions: str | None = None,
    template: dict | None = None,
    client=None,
) -> dict:
    """Buat email (subject+body) untuk satu perusahaan. AIError bila gagal."""
    with AIClient(settings, client=client) as ai:
        raw = ai.complete_json(
            build_system_prompt(),
            build_user_prompt(company, contacts, email_type, language, instructions=instructions, template=template),
            temperature=0.4,
        )
    clean = validate_email(raw)
    clean["model"] = settings.ai_model_name
    clean["prompt_version"] = PROMPT_VERSION
    clean["raw_ai_output"] = raw
    return clean
