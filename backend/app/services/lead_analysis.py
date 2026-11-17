"""Kualifikasi AI lead + simpan ke `lead_analysis` (riwayat terjaga via `is_current`).

Data perusahaan di `companies` TIDAK pernah diubah AI. Setiap kualifikasi baru
menggantikan yang lama (`is_current=false`) lalu menyisipkan baris baru.
"""
from __future__ import annotations

from ..ai.client import AIError
from ..ai.lead_service import qualify as ai_qualify
from ..ai.lead_validate import AIValidationError
from ..config import Settings
from ..db import SupabaseClient, SupabaseError
from .collection import log_event
from .company_profile import load_profile
from .leads import _ensure_lead

_ANALYSIS_FIELDS = (
    "lead_score",
    "category",
    "industry_classification",
    "potential_products",
    "reason",
    "suggested_approach",
    "model",
    "prompt_version",
    "raw_ai_output",
)

_COMPANY_SELECT = "id,name,industry,description,address,city,province,website,source_name,source_url"


def get_company(db: SupabaseClient, company_id: str) -> dict | None:
    rows = db.select("companies", {"select": _COMPANY_SELECT, "id": f"eq.{company_id}", "limit": "1"})
    return rows[0] if rows else None


def get_lead(db: SupabaseClient, company_id: str) -> dict | None:
    rows = db.select(
        "company_leads",
        {"select": "id,company_id,status", "company_id": f"eq.{company_id}", "limit": "1"},
    )
    return rows[0] if rows else None


def get_contacts(db: SupabaseClient, company_id: str) -> list[dict]:
    return db.select(
        "company_contacts",
        {"select": "contact_type,value,source_url", "company_id": f"eq.{company_id}"},
    )


def store_lead_analysis(db: SupabaseClient, lead_id: str, result: dict) -> dict:
    """Nonaktifkan analisis lama (is_current=false), sisipkan yang baru."""
    db.update(
        "lead_analysis",
        {"lead_id": f"eq.{lead_id}", "is_current": "eq.true"},
        {"is_current": False},
        returning=False,
    )
    row = {"lead_id": lead_id, "is_current": True, **{k: result.get(k) for k in _ANALYSIS_FIELDS}}
    rows = db.insert("lead_analysis", row)
    return rows[0] if rows else row


def analyze_company(db: SupabaseClient, company_id: str, settings: Settings, client=None) -> dict:
    company = get_company(db, company_id)
    if not company:
        raise LookupError("Perusahaan tidak ditemukan")
    lead = get_lead(db, company_id)
    if not lead:
        _ensure_lead(db, company_id)
        lead = get_lead(db, company_id)
    contacts = get_contacts(db, company_id)

    result = ai_qualify(company, contacts, settings, client=client)
    stored = store_lead_analysis(db, lead["id"], result)

    if lead.get("status") == "new":
        db.update("company_leads", {"id": f"eq.{lead['id']}"}, {"status": "qualified"}, returning=False)

    log_event(
        db, "info", "lead_analysis",
        f"Kualifikasi lead: {result['category']} ({result['lead_score']}/100)",
        {"company_id": company_id, "model": result["model"], "prompt_version": result["prompt_version"]},
    )
    return stored


def pending_companies(db: SupabaseClient, limit: int) -> list[dict]:
    """Perusahaan tanpa analisis terkini (dibandingkan di memori; skala kecil)."""
    limit = max(1, int(limit))
    companies = db.select(
        "companies",
        {"select": _COMPANY_SELECT, "order": "created_at.desc", "limit": str(limit * 3)},
    )
    analyzed = db.select(
        "lead_analysis", {"select": "lead_id", "is_current": "eq.true", "limit": "10000"}
    )
    done_lead_ids = {a["lead_id"] for a in analyzed}
    leads = db.select("company_leads", {"select": "id,company_id", "limit": "10000"})
    lead_by_company = {l["company_id"]: l["id"] for l in leads}
    out: list[dict] = []
    for c in companies:
        lid = lead_by_company.get(c["id"])
        if lid and lid in done_lead_ids:
            continue
        out.append(c)
    return out[:limit]


def analyze_pending(db: SupabaseClient, settings: Settings, limit: int = 10, client=None) -> dict:
    """Kualifikasi sekumpulan perusahaan tanpa analisis terkini."""
    companies = pending_companies(db, limit)
    results: list[dict] = []
    for c in companies:
        try:
            result = ai_qualify(c, get_contacts(db, c["id"]), settings, client=client)
            lead = get_lead(db, c["id"])
            if not lead:
                _ensure_lead(db, c["id"])
                lead = get_lead(db, c["id"])
            store_lead_analysis(db, lead["id"], result)
            if lead.get("status") == "new":
                db.update("company_leads", {"id": f"eq.{lead['id']}"}, {"status": "qualified"}, returning=False)
            results.append(
                {"company_id": c["id"], "status": "ok", "category": result["category"], "lead_score": result["lead_score"]}
            )
        except (AIError, AIValidationError) as e:
            results.append({"company_id": c["id"], "status": "error", "error": str(e)})
            if isinstance(e, AIError) and "belum diisi" in str(e):
                break
        except SupabaseError as e:  # pragma: no cover - jalur error I/O
            results.append({"company_id": c["id"], "status": "error", "error": str(e)})
    return {
        "analyzed": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }


__all__ = [
    "analyze_company",
    "analyze_pending",
    "get_company",
    "get_contacts",
    "get_lead",
    "load_profile",
    "pending_companies",
    "store_lead_analysis",
]
