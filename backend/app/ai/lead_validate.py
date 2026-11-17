"""Validasi & normalisasi output AI kualifikasi lead sebelum disimpan ke `lead_analysis`."""
from __future__ import annotations

from .validate import AIValidationError, MAX_TEXT, derive_priority

VALID_CATEGORIES = ("HIGH", "MEDIUM", "LOW")
MAX_PRODUCTS = 12


def _text(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s[:MAX_TEXT] if s else None


def _products(value) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for item in items:
        s = str(item).strip()[:200]
        if s and s not in out:
            out.append(s)
    return out[:MAX_PRODUCTS]


def validate_lead_analysis(raw) -> dict:
    """Kembalikan dict ternormalisasi siap simpan, atau AIValidationError."""
    if not isinstance(raw, dict):
        raise AIValidationError("output AI bukan objek JSON")

    score_raw = raw.get("lead_score")
    try:
        score = int(round(float(score_raw)))
    except (TypeError, ValueError):
        raise AIValidationError(f"lead_score tidak valid: {score_raw!r}")
    score = max(0, min(100, score))

    reason = _text(raw.get("reason"))
    if not reason:
        raise AIValidationError("reason wajib diisi")

    category = derive_priority(score)  # HIGH >=70, MEDIUM >=40, LOW <40 (konsisten dgn dashboard)
    given = str(raw.get("category") or "").strip().upper()
    if given in VALID_CATEGORIES and given != category:
        # Paksa konsisten dengan skor; kategori liar dari AI tidak dipercaya.
        category = derive_priority(score)

    return {
        "lead_score": score,
        "category": category,
        "industry_classification": _text(raw.get("industry_classification")),
        "potential_products": _products(raw.get("potential_products")),
        "reason": reason,
        "suggested_approach": _text(raw.get("suggested_approach")),
    }
