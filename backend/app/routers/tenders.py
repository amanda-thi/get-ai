"""Router tender: listing, detail, koleksi manual, analisis AI, dan export Excel."""
from __future__ import annotations

import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai.client import AIError
from ..ai.validate import AIValidationError
from ..config import get_settings
from ..db import SupabaseClient, SupabaseError
from ..deps import get_current_user, get_db
from ..services import analysis as analysis_service
from ..services import collection
from ..utils.text import JAKARTA

router = APIRouter(prefix="/api/tenders", tags=["tenders"])

# Listing membaca view `tenders_with_analysis` (migrasi 007) yang meratakan analisis
# terkini menjadi kolom `analysis_*` (satu baris per tender). Diperlukan karena
# `tenders -> tender_analysis` satu-ke-banyak sehingga PostgREST tidak bisa mengurutkan
# tender berdasarkan kolom analisis (PGRST118). Detail tetap memakai embed to-many.
_LIST_TABLE = "tenders_with_analysis"
_BASE_SELECT = (
    "id,source_id,external_id,package_name,agency,location,procurement_type,"
    "budget_ceiling,hps,announced_at,registration_start,registration_end,bid_deadline,"
    "status,source_url,matched_keywords,first_seen_at,last_seen_at"
)
_ANALYSIS_COLS = (
    "analysis_id,analysis_category,analysis_relevance_score,analysis_priority,"
    "analysis_score_reason,analysis_deadline_flag,analysis_created_at"
)
_LIST_SELECT = f"{_BASE_SELECT},{_ANALYSIS_COLS}"
_DETAIL_ANALYSIS_SELECT = (
    "tender_analysis(id,category,relevance_score,priority,score_reason,equipment_needs,"
    "cooperation_opportunity,key_requirements,deadline_flag,model,prompt_version,is_current,"
    "created_at,verified_at)"
)

_SORTS = {"announced_at", "bid_deadline", "first_seen_at", "hps", "relevance_score"}
_EXPORT_MAX = 5000
_SANITIZE_RE = re.compile(r"[(),*%]")

_ANALYSIS_KEYS = (
    "analysis_id",
    "analysis_category",
    "analysis_relevance_score",
    "analysis_priority",
    "analysis_score_reason",
    "analysis_deadline_flag",
    "analysis_created_at",
)


def _clean(value: str) -> str:
    """Bersihkan input agar tidak merusak sintaks filter PostgREST."""
    return re.sub(r"\s+", " ", _SANITIZE_RE.sub(" ", value or "")).strip()


def shape_tender(row: dict) -> dict:
    """Ratakan kolom `analysis_*` dari view menjadi `analysis` (dict|None)."""
    row = dict(row)
    analysis_id = row.pop("analysis_id", None)
    if analysis_id:
        row["analysis"] = {
            "id": analysis_id,
            "category": row.pop("analysis_category", None),
            "relevance_score": row.pop("analysis_relevance_score", None),
            "priority": row.pop("analysis_priority", None),
            "score_reason": row.pop("analysis_score_reason", None),
            "deadline_flag": row.pop("analysis_deadline_flag", None),
            "is_current": True,
            "created_at": row.pop("analysis_created_at", None),
        }
    else:
        for key in _ANALYSIS_KEYS:
            row.pop(key, None)
        row["analysis"] = None
    return row


def build_list_filters(
    q: str = "",
    priority: str = "",
    category: str = "",
    source_id: str = "",
    status: str = "",
    agency: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    """Filter PostgREST untuk view listing (kolom analisis sudah rata, tanpa embed)."""
    filters: dict = {}
    if priority:
        filters["analysis_priority"] = f"eq.{_clean(priority).upper()}"
    if category:
        filters["analysis_category"] = f"eq.{_clean(category)}"

    q = _clean(q)
    if q:
        filters["or"] = f"(package_name.ilike.*{q}*,agency.ilike.*{q}*)"
    if source_id:
        filters["source_id"] = f"eq.{_clean(source_id)}"
    if status:
        filters["status"] = f"ilike.*{_clean(status)}*"
    if agency:
        filters["agency"] = f"ilike.*{_clean(agency)}*"

    rng = []
    if date_from:
        rng.append(f"announced_at.gte.{_clean(date_from)}")
    if date_to:
        rng.append(f"announced_at.lte.{_clean(date_to)}")
    if rng:
        filters["and"] = f"({','.join(rng)})"
    return filters


def build_list_params(
    *,
    page: int = 1,
    per_page: int = 20,
    sort: str = "announced_at",
    order: str = "desc",
    **filter_kwargs,
) -> tuple[dict, dict]:
    """Kembalikan (params select, filters) untuk view `tenders_with_analysis`."""
    filters = build_list_filters(**filter_kwargs)
    order = order if order in ("asc", "desc") else "desc"
    if sort == "relevance_score":
        order_by = f"analysis_relevance_score.{order}.nullslast"
    else:
        col = sort if sort in _SORTS else "announced_at"
        order_by = f"{col}.{order}.nullslast"
    params = {
        "select": _LIST_SELECT,
        "order": order_by,
        "limit": str(per_page),
        "offset": str((page - 1) * per_page),
        **filters,
    }
    return params, filters


class CollectRequest(BaseModel):
    source_ids: list[str] | None = None
    years: list[int] | None = None
    keywords: list[str] | None = None
    max_rows: int | None = Field(default=None, ge=1, le=10000)
    enrich_limit: int | None = Field(default=None, ge=0, le=200)


class AnalyzePendingRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)


@router.get("")
def list_tenders(
    q: str = "",
    priority: str = "",
    category: str = "",
    source_id: str = "",
    status: str = "",
    agency: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "announced_at",
    order: str = "desc",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Listing tender dengan filter, urutan, dan paginasi. Analisis AI terkini disertakan."""
    params, filters = build_list_params(
        page=page, per_page=per_page, sort=sort, order=order,
        q=q, priority=priority, category=category, source_id=source_id,
        status=status, agency=agency, date_from=date_from, date_to=date_to,
    )
    try:
        rows = db.select(_LIST_TABLE, params)
        total = db.count(_LIST_TABLE, filters, select="id")
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    return {
        "items": [shape_tender(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


def _export_rows(db: SupabaseClient, filters: dict) -> list[dict]:
    rows: list[dict] = []
    chunk = 1000
    offset = 0
    while len(rows) < _EXPORT_MAX:
        batch = db.select(
            _LIST_TABLE,
            {"select": _LIST_SELECT, "order": "announced_at.desc.nullslast", "limit": str(chunk), "offset": str(offset), **filters},
        )
        rows.extend(batch)
        if len(batch) < chunk:
            break
        offset += chunk
    return rows[: _EXPORT_MAX]


@router.get("/export")
def export_tenders(
    q: str = "",
    priority: str = "",
    category: str = "",
    source_id: str = "",
    status: str = "",
    agency: str = "",
    date_from: str = "",
    date_to: str = "",
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Export hasil filter ke Excel (.xlsx)."""
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover - hanya bila dependensi hilang
        raise HTTPException(503, "openpyxl belum terpasang di backend") from e

    filters = build_list_filters(
        q=q, priority=priority, category=category, source_id=source_id,
        status=status, agency=agency, date_from=date_from, date_to=date_to,
    )
    try:
        rows = [shape_tender(r) for r in _export_rows(db, filters)]
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tenders"
    headers = [
        "Nama Paket", "Instansi", "Lokasi", "Jenis", "HPS", "Pagu",
        "Deadline", "Status", "Prioritas", "Skor", "Kategori", "URL Sumber",
    ]
    ws.append(headers)
    for r in rows:
        a = r.get("analysis") or {}
        ws.append([
            r.get("package_name"), r.get("agency"), r.get("location"), r.get("procurement_type"),
            r.get("hps"), r.get("budget_ceiling"), r.get("bid_deadline"), r.get("status"),
            a.get("priority"), a.get("relevance_score"), a.get("category"), r.get("source_url"),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"tenders-{datetime.now(JAKARTA).strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/collect")
def collect_tenders(
    payload: CollectRequest,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Pencarian manual: jalankan adapter sumber lalu simpan tender yang cocok keyword."""
    settings = get_settings()
    options: dict = {}
    if payload.years:
        options["years"] = payload.years
    if payload.max_rows:
        options["max_rows"] = payload.max_rows
    if payload.enrich_limit is not None:
        options["enrich_limit"] = payload.enrich_limit
    try:
        return collection.collect_all(
            db, settings,
            source_ids=payload.source_ids,
            keywords=payload.keywords or None,
            options=options,
        )
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/analyze-pending")
def analyze_pending(
    payload: AnalyzePendingRequest,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Analisis AI untuk tender yang belum punya analisis terkini (dibatasi batch)."""
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(503, "Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    limit = min(payload.limit, settings.analyze_max_batch)
    try:
        return analysis_service.analyze_pending(db, settings, limit=limit)
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/{tender_id}")
def get_tender_detail(
    tender_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Detail satu tender + riwayat analisis AI (yang terkini ditandai)."""
    try:
        rows = db.select(
            "tenders",
            {"select": f"*,{_DETAIL_ANALYSIS_SELECT}", "id": f"eq.{tender_id}", "limit": "1"},
        )
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    if not rows:
        raise HTTPException(404, "Tender tidak ditemukan")
    row = rows[0]
    history = row.pop("tender_analysis", None) or []
    if isinstance(history, dict):
        history = [history]
    history.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    current = next((a for a in history if a.get("is_current")), None)
    return {"tender": row, "analysis": current, "analysis_history": history}


@router.post("/{tender_id}/analyze")
def analyze_one(
    tender_id: str,
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    """Analisis AI satu tender (butuh kredensial AI)."""
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(503, "Kunci AI belum diisi (GROQ_API_KEY / OPENAI_API_KEY).")
    try:
        return analysis_service.analyze_tender(db, tender_id, settings)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except (AIError, AIValidationError) as e:
        raise HTTPException(502, f"Analisis AI gagal: {e}") from e
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
