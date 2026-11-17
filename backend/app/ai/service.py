"""Layanan analisis AI: panggil model lalu validasi. Tidak menulis DB (lihat services/analysis.py)."""
from __future__ import annotations

from ..config import Settings
from .client import AIClient
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from .validate import validate_analysis


def analyze(tender: dict, settings: Settings, client=None) -> dict:
    """Analisis satu tender -> dict siap simpan (termasuk model, prompt_version, raw_ai_output)."""
    with AIClient(settings, client=client) as ai:
        raw = ai.complete_json(SYSTEM_PROMPT, build_user_prompt(tender))
    clean = validate_analysis(raw)
    clean["model"] = settings.ai_model_name
    clean["prompt_version"] = PROMPT_VERSION
    clean["raw_ai_output"] = raw
    return clean
