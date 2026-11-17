"""Layanan kualifikasi lead: panggil model lalu validasi. Tidak menulis DB."""
from __future__ import annotations

from ..config import Settings
from .client import AIClient
from .lead_prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt
from .lead_validate import validate_lead_analysis


def qualify(company: dict, contacts: list[dict] | None, settings: Settings, client=None) -> dict:
    """Kualifikasi satu perusahaan -> dict siap simpan (termasuk model, prompt_version)."""
    with AIClient(settings, client=client) as ai:
        raw = ai.complete_json(build_system_prompt(), build_user_prompt(company, contacts))
    clean = validate_lead_analysis(raw)
    clean["model"] = settings.ai_model_name
    clean["prompt_version"] = PROMPT_VERSION
    clean["raw_ai_output"] = raw
    return clean
