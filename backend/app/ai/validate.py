"""Validasi & normalisasi output AI sebelum ditulis ke DB. Mencegah data tak masuk akal tersimpan."""
from __future__ import annotations

VALID_PRIORITIES = ("HIGH", "MEDIUM", "LOW")
MAX_TEXT = 4000  # batas panjang agar baris DB tetap wajar


class AIValidationError(Exception):
    """Output AI tidak memenuhi skema minimum."""


def _text(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s[:MAX_TEXT] if s else None


def derive_priority(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def validate_analysis(raw) -> dict:
    """Kembalikan dict ternormalisasi siap simpan, atau AIValidationError."""
    if not isinstance(raw, dict):
        raise AIValidationError("output AI bukan objek JSON")

    score_raw = raw.get("relevance_score")
    try:
        score = int(round(float(score_raw)))
    except (TypeError, ValueError):
        raise AIValidationError(f"relevance_score tidak valid: {score_raw!r}") from None
    score = max(0, min(100, score))  # jaga batas kolom check (0..100)

    priority = str(raw.get("priority") or "").strip().upper()
    if priority not in VALID_PRIORITIES:
        priority = derive_priority(score)

    reason = _text(raw.get("score_reason"))
    if not reason:
        raise AIValidationError("score_reason wajib diisi")

    return {
        "category": _text(raw.get("category")) or "Other",
        "relevance_score": score,
        "priority": priority,
        "score_reason": reason,
        "equipment_needs": _text(raw.get("equipment_needs")),
        "cooperation_opportunity": _text(raw.get("cooperation_opportunity")),
        "key_requirements": _text(raw.get("key_requirements")),
        "deadline_flag": _text(raw.get("deadline_flag")),
    }
