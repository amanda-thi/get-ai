"""Router Company Leads (Fase 3): listing, detail, discovery, kualifikasi AI, kontak."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..ai.client import AIError
from ..ai.lead_validate import AIValidationError
from ..config import get_settings
from ..db import SupabaseClient, SupabaseError
from ..deps import get_current_user, get_db, require_role
from ..discovery.base import DiscoveryError
from ..services import lead_analysis as analysis_service
from ..services import leads as leads_service

router = APIRouter(prefix="/api/leads", tags=["leads"])

# Listing memakai view `leads_with_analysis` (migrasi 008) yang meratakan analisis
# terkini (`analysis_*`) — sama alasannya dengan view tender Fase 2 (PGRST118).
_LIST_TABLE = "leads_with_analysis"
_BASE_SELECT = (
    "id,name,normalized_name,industry,description,address,city,province,website,"
    "source_name,source_url,created_at,updated_at"
)
_ANALYSIS_COLS = (
    "analysis_id,analysis_lead_score,analysis_category,analysis_industry_classification,"
    "analysis_potential_products,analysis_reason,analysis_suggested_approach,analysis_created_at"
)
_LEAD_COLS = "lead_id,lead_status,lead_notes,lead_assigned_to"
_LIST_SELECT = f"{_BASE_SELECT},{_LEAD_COLS},{_ANALYSIS_COLS}"
_ANALYSIS_KEYS = _ANALYSIS_COLS.split(",")
_LEAD_KEYS = _LEAD_COLS.split(",")

_SORTS = {"created_at", "name", "lead_score"}
_SANITIZE_RE = re.compile(r"[(),*%]")

LEAD_STATUSES = (
    "new", "qualified", "contacted", "responded", "negotiation", "won", "lost", "do_not_contact",
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", _SANITIZE_RE.sub(" ", value or "")).strip()


def shape_lead(row: dict) -> dict:
    """Ratakan kolom `lead_*`/`analysis_*` dari view menjadi `lead` & `analysis`."""
    row = dict(row)
    lead_id = row.pop("lead_id", None)
    lead_status = row.pop("lead_status", None)
    lead_notes = row.pop("lead_notes", None)
    lead_assigned = row.pop("lead_assigned_to", None)
    row["lead"] = (
        {"id": lead_id, "status": lead_status, "notes": lead_notes, "assigned_to": lead_assigned}
        if lead_id
        else None
    )

    analysis_id = row.pop("analysis_id", None)
    if analysis_id:
        row["analysis"] = {
            "id": analysis_id,
            "lead_score": row.pop("analysis_lead_score", None),
            "category": row.pop("analysis_category", None),
            "industry_classification": row.pop("analysis_industry_classification", None),
            "potential_products": row.pop("analysis_potential_products", None),
            "reason": row.pop("analysis_reason", None),
            "suggested_approach": row.pop("analysis_suggested_approach", None),
            "is_current": True,
            "created_at": row.pop("analysis_created_at", None),
        }
    else:
        for key in _ANALYSIS_KEYS:
            row.pop(key, None)
        row["analysis"] = None
    return row


def build_list_filters(
    q: str = "", status: str = "", category: str = "", industry: str = "",
    province: str = "", city: str = "",
) -> dict:
    filters: dict = {}
    if status:
        filters["lead_status"] = f"eq.{_clean(status)}"
    if category:
        filters["analysis_category"] = f"eq.{_clean(category).upper()}"
    if industry:
        filters["industry"] = f"ilike.*{_clean(industry)}*"
    if province:
        filters["province"] = f"ilike.*{_clean(province)}*"
    if city:
        filters["city"] = f"ilike.*{_clean(city)}*"
    q = _clean(q)
    if q:
        filters["or"] = f"(name.ilike.*{q}*,description.ilike.*{q}*,website.ilike.*{q}*)"
    return filters


def build_list_params(
    *, page: int = 1, per_page: int = 20, sort: str = "created_at", order: str = "desc", **filter_kwargs
) -> tuple[dict, dict]:
    filters = build_list_filters(**filter_kwargs)
    order = order if order in ("asc", "desc") else "desc"
    if sort == "lead_score":
        order_by = f"analysis_lead_score.{order}.nullslast"
    else:
        col = sort if sort in _SORTS else "created_at"
        order_by = f"{col}.{order}.nullslast"
    params = {
        "select": _LIST_SELECT,
        "order": order_by,
        "limit": str(per_page),
        "offset": str((page - 1) * per_page),
        **filters,
    }
    return params, filters


class DiscoverRequest(BaseModel):
    items: list[dict] | None = None
    urls: list[str] | None = None
    query: str | None = None
    industry: str | None = None
    location: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    website: str | None = None
    industry: str | None = None
    city: str | None = None
    province: str | None = None
    address: str | None = None
    description: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    source_name: str | None = None
    source_url: str | None = None


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    website: str | None = None
    industry: str | None = None
    city: str | None = None
    province: str | None = None
    address: str | None = None
    description: str | None = None
    status: str | None = None
    notes: str | None = None


class ContactIn(BaseModel):
    contact_type: str
    value: str = Field(min_length=1, max_length=300)
    source_url: str | None = None


class AnalyzePendingRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)


@router.get("")
def list_leads(
    q: str = "",
    status: str = "",
    category: str = "",
    industry: str = "",
    province: str = "",
    city: str = "",
    sort: str = "created_at",
    order: str = "desc",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Listing perusahaan/lead + status CRM + skor kualifikasi AI terkini."""
    params, filters = build_list_params(
        page=page, per_page=per_page, sort=sort, order=order,
        q=q, status=status, category=category, industry=industry, province=province, city=city,
    )
    try:
        rows = db.select(_LIST_TABLE, params)
        total = db.count(_LIST_TABLE, filters, select="id")
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {
        "items": [shape_lead(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.post("/discover")
def discover_leads(
    payload: DiscoverRequest,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Kumpulkan calon perusahaan: manual/impor, dari URL situs, atau pencarian (butuh kunci)."""
    if not (payload.items or payload.urls or (payload.query and payload.query.strip())):
        raise HTTPException(400, "Isi minimal salah satu: items, urls, atau query.")
    try:
        return leads_service.discover(
            db, get_settings(),
            items=payload.items, urls=payload.urls, query=payload.query,
            industry=payload.industry, location=payload.location, limit=payload.limit,
            user_id=user["id"],
        )
    except DiscoveryError as e:
        raise HTTPException(502, str(e)) from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("")
def create_lead(
    payload: LeadIn,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Tambah satu perusahaan manual (dedupe otomatis)."""
    try:
        result = leads_service.discover(
            db, get_settings(), items=[payload.model_dump()], user_id=user["id"]
        )
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return result


@router.post("/analyze-pending")
def analyze_pending(
    payload: AnalyzePendingRequest,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Kualifikasi AI untuk perusahaan yang belum punya analisis terkini (dibatasi batch)."""
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(503, "Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    limit = min(payload.limit, settings.lead_analysis_max_batch)
    try:
        return analysis_service.analyze_pending(db, settings, limit=limit)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/{company_id}")
def get_lead_detail(
    company_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Detail perusahaan + lead + kontak + riwayat kualifikasi AI."""
    try:
        rows = db.select("companies", {"select": "*", "id": f"eq.{company_id}", "limit": "1"})
        if not rows:
            raise HTTPException(404, "Perusahaan tidak ditemukan")
        company = rows[0]
        lead_rows = db.select("company_leads", {"select": "*", "company_id": f"eq.{company_id}", "limit": "1"})
        contacts = db.select(
            "company_contacts", {"select": "id,contact_type,value,source_url", "company_id": f"eq.{company_id}"}
        )
        history: list[dict] = []
        messages: list[dict] = []
        if lead_rows:
            lead_id = lead_rows[0]["id"]
            history = db.select(
                "lead_analysis",
                {"select": "*", "lead_id": f"eq.{lead_id}", "order": "created_at.desc"},
            )
            messages = db.select(
                "outreach_messages",
                {
                    "select": "id,email_type,language,subject,status,recipient_email,created_at,sent_at",
                    "lead_id": f"eq.{lead_id}",
                    "order": "created_at.desc",
                },
            )
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e

    current = next((a for a in history if a.get("is_current")), None)
    return {
        "company": company,
        "lead": lead_rows[0] if lead_rows else None,
        "contacts": contacts,
        "analysis": current,
        "analysis_history": history,
        "messages": messages,
    }


@router.patch("/{company_id}")
def update_lead(
    company_id: str,
    payload: LeadUpdate,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Ubah data perusahaan dan/atau status/notes lead."""
    company_fields = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in ("name", "website", "industry", "city", "province", "address", "description") and v is not None
    }
    status = payload.status
    notes = payload.notes
    if status and status not in LEAD_STATUSES:
        raise HTTPException(400, f"Status tidak valid. Pilihan: {', '.join(LEAD_STATUSES)}")
    try:
        if "name" in company_fields:
            from ..services.leads import normalize_company_name

            company_fields["normalized_name"] = normalize_company_name(company_fields["name"])
        if company_fields:
            db.update("companies", {"id": f"eq.{company_id}"}, company_fields, returning=False)
        lead_fields: dict = {}
        if status:
            lead_fields["status"] = status
        if notes is not None:
            lead_fields["notes"] = notes
        if lead_fields:
            updated = db.update("company_leads", {"company_id": f"eq.{company_id}"}, lead_fields)
            if not updated:
                from ..services.leads import _ensure_lead

                _ensure_lead(db, company_id)
                db.update("company_leads", {"company_id": f"eq.{company_id}"}, lead_fields, returning=False)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True}


@router.post("/{company_id}/contacts")
def add_contact(
    company_id: str,
    payload: ContactIn,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Tambah kontak bisnis publik (wajib ada sumber)."""
    try:
        return leads_service.add_contact(
            db, company_id, payload.contact_type, payload.value, payload.source_url or ""
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.delete("/contacts/{contact_id}")
def delete_contact(
    contact_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Hapus kontak (admin)."""
    try:
        db.delete("company_contacts", {"id": f"eq.{contact_id}"})
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True}


@router.post("/{company_id}/qualify")
def qualify_lead(
    company_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Kualifikasi AI satu perusahaan (butuh kredensial AI)."""
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(503, "Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    try:
        return analysis_service.analyze_company(db, company_id, settings)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except (AIError, AIValidationError) as e:
        raise HTTPException(502, f"Kualifikasi AI gagal: {e}") from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.delete("/{company_id}")
def delete_lead(
    company_id: str,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    """Hapus perusahaan beserta lead/kontak/analisisnya (admin)."""
    try:
        db.delete("companies", {"id": f"eq.{company_id}"})
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True}
