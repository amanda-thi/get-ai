"""Router Marketing Outreach (Fase 3): template, campaign, pesan, generate AI, approve, kirim."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..ai.client import AIError
from ..ai.outreach_prompts import EMAIL_TYPES, LANGUAGES
from ..config import get_settings
from ..db import SupabaseClient, SupabaseError
from ..deps import get_current_user, get_db, require_role
from ..services import outreach as outreach_service
from ..services.mailer import MailError

router = APIRouter(prefix="/api/outreach", tags=["outreach"])

_MESSAGE_SORTS = {"created_at", "sent_at", "status"}
_SANITIZE_RE = re.compile(r"[(),*%]")

TEMPLATE_SELECT = "id,name,email_type,language,subject,body,is_active,created_at,updated_at"
CAMPAIGN_SELECT = "id,name,description,status,created_at,updated_at"
MESSAGE_SELECT = (
    "id,campaign_id,lead_id,contact_id,email_type,language,recipient_email,subject,body,"
    "status,approved_by,approved_at,sent_at,provider_message_id,error,ai_model,created_at,updated_at"
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", _SANITIZE_RE.sub(" ", value or "")).strip()


def build_message_filters(
    q: str = "", status: str = "", email_type: str = "", language: str = "",
    lead_id: str = "", campaign_id: str = "",
) -> dict:
    filters: dict = {}
    if status:
        filters["status"] = f"eq.{_clean(status)}"
    if email_type:
        filters["email_type"] = f"eq.{_clean(email_type)}"
    if language:
        filters["language"] = f"eq.{_clean(language)}"
    if lead_id:
        filters["lead_id"] = f"eq.{_clean(lead_id)}"
    if campaign_id:
        filters["campaign_id"] = f"eq.{_clean(campaign_id)}"
    q = _clean(q)
    if q:
        filters["or"] = f"(subject.ilike.*{q}*,body.ilike.*{q}*,recipient_email.ilike.*{q}*)"
    return filters


def _resolve_names(db: SupabaseClient, rows: list[dict]) -> list[dict]:
    """Lengkapi nama perusahaan/lead untuk daftar pesan (hindari embed bertingkat)."""
    lead_ids = [r["lead_id"] for r in rows if r.get("lead_id")]
    names: dict[str, dict] = {}
    if lead_ids:
        leads = db.select(
            "company_leads",
            {"select": "id,company_id", "id": f"in.({','.join(sorted(set(lead_ids)))})"},
        )
        company_ids = [l["company_id"] for l in leads if l.get("company_id")]
        companies = {}
        if company_ids:
            companies = {
                c["id"]: c
                for c in db.select(
                    "companies",
                    {"select": "id,name,website", "id": f"in.({','.join(sorted(set(company_ids)))})"},
                )
            }
        for l in leads:
            names[l["id"]] = companies.get(l.get("company_id"), {})
    for r in rows:
        info = names.get(r.get("lead_id")) or {}
        r["company_name"] = info.get("name")
        r["company_website"] = info.get("website")
    return rows


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email_type: str
    language: str
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: str | None = None
    email_type: str | None = None
    language: str | None = None
    subject: str | None = None
    body: str | None = None
    is_active: bool | None = None


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: str = "active"


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class MessageIn(BaseModel):
    email_type: str
    language: str
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    lead_id: str | None = None
    contact_id: str | None = None
    campaign_id: str | None = None
    recipient_email: str | None = None


class MessageUpdate(BaseModel):
    email_type: str | None = None
    language: str | None = None
    subject: str | None = None
    body: str | None = None
    recipient_email: str | None = None
    contact_id: str | None = None
    campaign_id: str | None = None


class GenerateRequest(BaseModel):
    lead_id: str | None = None
    company_id: str | None = None
    email_type: str
    language: str
    template_id: str | None = None
    campaign_id: str | None = None
    recipient_email: str | None = None
    instructions: str | None = None


class StatusIn(BaseModel):
    status: str


def _validate_enum(email_type: str | None = None, language: str | None = None) -> None:
    if email_type and email_type not in EMAIL_TYPES:
        raise HTTPException(400, f"email_type tidak valid. Pilihan: {', '.join(EMAIL_TYPES)}")
    if language and language not in LANGUAGES:
        raise HTTPException(400, f"language tidak valid. Pilihan: {', '.join(LANGUAGES)}")


# --- konfigurasi ---

@router.get("/config")
def outreach_config(user: dict = Depends(get_current_user)):
    """Status fitur: apakah SMTP siap mengirim."""
    settings = get_settings()
    return {
        "smtp_configured": settings.smtp_configured,
        "email_types": list(EMAIL_TYPES),
        "languages": list(LANGUAGES),
        "ai_configured": settings.ai_configured,
    }


# --- template ---

@router.get("/templates")
def list_templates(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        return {"items": db.select("email_templates", {"select": TEMPLATE_SELECT, "order": "email_type.asc,language.asc,name.asc"})}
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/templates")
def create_template(
    payload: TemplateIn,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    _validate_enum(payload.email_type, payload.language)
    try:
        rows = db.insert("email_templates", payload.model_dump())
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return rows[0] if rows else payload.model_dump()


@router.patch("/templates/{template_id}")
def update_template(
    template_id: str,
    payload: TemplateUpdate,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    values = payload.model_dump(exclude_unset=True)
    _validate_enum(values.get("email_type"), values.get("language"))
    if not values:
        raise HTTPException(400, "Tidak ada perubahan.")
    try:
        rows = db.update("email_templates", {"id": f"eq.{template_id}"}, values)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return rows[0] if rows else {"ok": True}


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: str,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    try:
        db.delete("email_templates", {"id": f"eq.{template_id}"})
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True}


# --- campaign ---

@router.get("/campaigns")
def list_campaigns(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        return {"items": db.select("outreach_campaigns", {"select": CAMPAIGN_SELECT, "order": "created_at.desc"})}
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/campaigns")
def create_campaign(
    payload: CampaignIn,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    try:
        rows = db.insert("outreach_campaigns", {**payload.model_dump(), "created_by": user["id"]})
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return rows[0] if rows else payload.model_dump()


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "Tidak ada perubahan.")
    try:
        rows = db.update("outreach_campaigns", {"id": f"eq.{campaign_id}"}, values)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return rows[0] if rows else {"ok": True}


# --- pesan ---

@router.get("/messages")
def list_messages(
    q: str = "",
    status: str = "",
    email_type: str = "",
    language: str = "",
    lead_id: str = "",
    campaign_id: str = "",
    sort: str = "created_at",
    order: str = "desc",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    filters = build_message_filters(
        q=q, status=status, email_type=email_type, language=language, lead_id=lead_id, campaign_id=campaign_id
    )
    order = order if order in ("asc", "desc") else "desc"
    col = sort if sort in _MESSAGE_SORTS else "created_at"
    params = {
        "select": MESSAGE_SELECT,
        "order": f"{col}.{order}.nullslast",
        "limit": str(per_page),
        "offset": str((page - 1) * per_page),
        **filters,
    }
    try:
        rows = db.select("outreach_messages", params)
        total = db.count("outreach_messages", filters, select="id")
        rows = _resolve_names(db, rows)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {
        "items": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.post("/generate")
def generate(
    payload: GenerateRequest,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Buat email via AI dan simpan sebagai draft."""
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(503, "Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    _validate_enum(payload.email_type, payload.language)
    try:
        return outreach_service.generate_draft(
            db, settings, payload.model_dump(), user_id=user["id"]
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except AIError as e:
        raise HTTPException(502, f"Pembuatan email gagal: {e}") from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/messages")
def create_message(
    payload: MessageIn,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Simpan email manual sebagai draft."""
    _validate_enum(payload.email_type, payload.language)
    try:
        return outreach_service.create_message(db, payload.model_dump(), user_id=user["id"])
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/messages/{message_id}")
def get_message(
    message_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    try:
        rows = db.select("outreach_messages", {"select": MESSAGE_SELECT, "id": f"eq.{message_id}", "limit": "1"})
        if not rows:
            raise HTTPException(404, "Email tidak ditemukan")
        logs = db.select(
            "outreach_logs",
            {"select": "id,event_type,details,created_at", "message_id": f"eq.{message_id}", "order": "created_at.desc"},
        )
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {"message": rows[0], "logs": logs}


@router.patch("/messages/{message_id}")
def update_message(
    message_id: str,
    payload: MessageUpdate,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    values = payload.model_dump(exclude_unset=True)
    _validate_enum(values.get("email_type"), values.get("language"))
    try:
        return outreach_service.update_message(db, message_id, values, user_id=user["id"])
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/messages/{message_id}/status")
def set_message_status(
    message_id: str,
    payload: StatusIn,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    try:
        return outreach_service.set_status(db, message_id, payload.status, user_id=user["id"])
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/messages/{message_id}/approve")
def approve_message(
    message_id: str,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    """Setujui email (admin). Wajib sebelum kirim."""
    try:
        return outreach_service.approve_message(db, message_id, user_id=user["id"])
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/messages/{message_id}/send")
def send_message(
    message_id: str,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    """Kirim email yang sudah disetujui via SMTP (admin)."""
    try:
        return outreach_service.send_message(db, message_id, get_settings(), user_id=user["id"])
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except MailError as e:
        raise HTTPException(502, str(e)) from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
