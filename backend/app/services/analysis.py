"""Analisis AI + penyimpanan ke `tender_analysis` (riwayat terjaga via `is_current`).

Data mentah di `tenders` TIDAK pernah diubah. Setiap analisis baru menggantikan
yang lama dengan menandai `is_current=false` lalu menyisipkan baris baru.
"""
from __future__ import annotations

from ..ai.client import AIError
from ..ai.service import analyze as ai_analyze
from ..ai.validate import AIValidationError
from ..config import Settings
from ..db import SupabaseClient, SupabaseError
from .collection import log_event

_ANALYSIS_FIELDS = (
    "category",
    "relevance_score",
    "priority",
    "score_reason",
    "equipment_needs",
    "cooperation_opportunity",
    "key_requirements",
    "deadline_flag",
    "model",
    "prompt_version",
    "raw_ai_output",
)

_TENDER_SELECT = (
    "id,package_name,agency,location,procurement_type,status,description,technical_specs,"
    "hps,budget_ceiling,participant_requirements,bid_deadline,matched_keywords,created_at"
)


def store_analysis(db: SupabaseClient, tender_id: str, result: dict) -> dict:
    """Simpan analisis: nonaktifkan yang lama (is_current=false), sisipkan yang baru."""
    db.update(
        "tender_analysis",
        {"tender_id": f"eq.{tender_id}", "is_current": "eq.true"},
        {"is_current": False},
        returning=False,
    )
    row = {"tender_id": tender_id, "is_current": True, **{k: result.get(k) for k in _ANALYSIS_FIELDS}}
    rows = db.insert("tender_analysis", row)
    return rows[0] if rows else row


def get_tender(db: SupabaseClient, tender_id: str) -> dict | None:
    rows = db.select("tenders", {"select": "*", "id": f"eq.{tender_id}", "limit": "1"})
    return rows[0] if rows else None


def analyze_tender(db: SupabaseClient, tender_id: str, settings: Settings, client=None) -> dict:
    tender = get_tender(db, tender_id)
    if not tender:
        raise LookupError("Tender tidak ditemukan")
    result = ai_analyze(tender, settings, client=client)
    stored = store_analysis(db, tender_id, result)
    log_event(
        db, "info", "analysis",
        f"Analisis tender: {result['priority']} ({result['relevance_score']}/100)",
        {"tender_id": tender_id, "model": result["model"], "prompt_version": result["prompt_version"]},
    )
    return stored


def pending_tenders(db: SupabaseClient, limit: int) -> list[dict]:
    """Tender tanpa analisis terkini (dibandingkan di memori; skala kecil)."""
    limit = max(1, int(limit))
    tenders = db.select(
        "tenders",
        {"select": _TENDER_SELECT, "order": "created_at.desc", "limit": str(limit * 3)},
    )
    analyzed = db.select(
        "tender_analysis", {"select": "tender_id", "is_current": "eq.true", "limit": "10000"}
    )
    done = {a["tender_id"] for a in analyzed}
    return [t for t in tenders if t["id"] not in done][:limit]


def analyze_pending(db: SupabaseClient, settings: Settings, limit: int = 10, client=None) -> dict:
    """Analisis sekumpulan tender tanpa analisis terkini (dibatasi `analyze_max_batch` di router)."""
    tenders = pending_tenders(db, limit)
    results: list[dict] = []
    for t in tenders:
        try:
            result = ai_analyze(t, settings, client=client)
            store_analysis(db, t["id"], result)
            results.append(
                {"tender_id": t["id"], "status": "ok", "priority": result["priority"], "relevance_score": result["relevance_score"]}
            )
        except (AIError, AIValidationError) as e:
            results.append({"tender_id": t["id"], "status": "error", "error": str(e)})
            if isinstance(e, AIError) and "belum diisi" in str(e):
                break  # masalah konfigurasi: tak perlu mencoba sisa
        except SupabaseError as e:  # pragma: no cover - jalur error I/O
            results.append({"tender_id": t["id"], "status": "error", "error": str(e)})
    return {
        "analyzed": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
