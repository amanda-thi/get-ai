"""Router sumber tender & keyword: daftar, health check, dan kelola keyword (admin)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import SupabaseClient, SupabaseError
from ..deps import get_current_user, get_db, require_role
from ..services.collection import log_event
from ..sources.base import HealthResult, SourceError
from ..sources.registry import build_adapter

router = APIRouter(prefix="/api", tags=["sources"])

_SOURCE_SELECT = "id,name,adapter_type,base_url,config,is_active,health_status,last_checked_at,last_success_at,last_error,created_at"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    adapter_type: str
    base_url: str = Field(min_length=1, max_length=500)
    config: dict = Field(default_factory=dict)
    is_active: bool = True


class SourcePatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class KeywordIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    language: str = "en"
    is_active: bool = True


class KeywordPatch(BaseModel):
    keyword: str | None = None
    category: str | None = None
    language: str | None = None
    is_active: bool | None = None


@router.get("/sources")
def list_sources(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        return {"sources": db.select("tender_sources", {"select": _SOURCE_SELECT, "order": "name.asc"})}
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/sources")
def create_source(
    payload: SourceIn,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    if payload.adapter_type not in ("sirup", "inaproc", "spse", "generic_html", "manual", "pyproc"):
        raise HTTPException(422, "adapter_type tidak dikenal")
    try:
        rows = db.insert("tender_sources", payload.model_dump())
    except SupabaseError as e:
        raise HTTPException(409, str(e)) from e
    return rows[0] if rows else {}


@router.patch("/sources/{source_id}")
def update_source(
    source_id: str,
    payload: SourcePatch,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    values = payload.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(422, "Tidak ada perubahan")
    try:
        rows = db.update("tender_sources", {"id": f"eq.{source_id}"}, values)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    if not rows:
        raise HTTPException(404, "Sumber tidak ditemukan")
    return rows[0]


@router.post("/sources/{source_id}/check")
def check_source(
    source_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Uji kesehatan satu sumber sekarang, perbarui statusnya, dan catat ke system_logs."""
    try:
        rows = db.select("tender_sources", {"select": "*", "id": f"eq.{source_id}", "limit": "1"})
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    if not rows:
        raise HTTPException(404, "Sumber tidak ditemukan")
    source = rows[0]

    try:
        adapter = build_adapter(source, get_settings())
    except SourceError as e:
        result = HealthResult(False, "manual_only", str(e))
    else:
        with adapter:
            result = adapter.health_check()

    now = _now()
    values = {"health_status": result.status, "last_checked_at": now, "last_error": None if result.ok else result.message}
    if result.ok:
        values["last_success_at"] = now
    try:
        db.update("tender_sources", {"id": f"eq.{source_id}"}, values, returning=False)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    log_event(
        db, "info" if result.ok else "warning", "source_health",
        f"{source.get('name')}: {result.status}", {"source_id": source_id, "message": result.message},
    )
    return {"source_id": source_id, "status": result.status, "ok": result.ok, "message": result.message, "checked_at": now}


@router.get("/keywords")
def list_keywords(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        return {
            "keywords": db.select(
                "tender_keywords",
                {"select": "id,keyword,category,language,is_active,created_at", "order": "category.asc,keyword.asc"},
            )
        }
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/keywords")
def create_keyword(
    payload: KeywordIn,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    if payload.language not in ("en", "id"):
        raise HTTPException(422, "language harus 'en' atau 'id'")
    try:
        rows = db.insert("tender_keywords", payload.model_dump())
    except SupabaseError as e:
        raise HTTPException(409, str(e)) from e
    return rows[0] if rows else {}


@router.patch("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: str,
    payload: KeywordPatch,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    values = payload.model_dump(exclude_none=True)
    if values.get("language") and values["language"] not in ("en", "id"):
        raise HTTPException(422, "language harus 'en' atau 'id'")
    if not values:
        raise HTTPException(422, "Tidak ada perubahan")
    try:
        rows = db.update("tender_keywords", {"id": f"eq.{keyword_id}"}, values)
    except SupabaseError as e:
        raise HTTPException(409, str(e)) from e
    if not rows:
        raise HTTPException(404, "Keyword tidak ditemukan")
    return rows[0]


@router.delete("/keywords/{keyword_id}")
def delete_keyword(
    keyword_id: str,
    user: dict = Depends(require_role("admin")),
    db: SupabaseClient = Depends(get_db),
):
    try:
        db.delete("tender_keywords", {"id": f"eq.{keyword_id}"})
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {"deleted": True}
