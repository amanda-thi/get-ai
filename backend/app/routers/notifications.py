"""Router Notifikasi (Fase 4): daftar, tandai dibaca, tandai semua dibaca.

Visibilitas: user melihat notifikasi miliknya; admin juga melihat notifikasi
broadcast (`user_id IS NULL`). Penulisan hanya lewat backend (service role).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import SupabaseClient, SupabaseError, is_missing_table_error
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

_SELECT = "id,notification_type,title,message,related_job_id,link,is_read,created_at"


def _db_error(e: SupabaseError) -> HTTPException:
    if is_missing_table_error(e):
        return HTTPException(503, "Tabel notifikasi belum ada. Jalankan migrasi Fase 4 (010) di Supabase SQL Editor.")
    return HTTPException(503, str(e))


def _visibility_filter(user: dict) -> dict:
    """Filter PostgREST untuk baris yang boleh dilihat user ini."""
    if user.get("role") == "admin":
        return {"or": f"(user_id.eq.{user['id']},user_id.is.null)"}
    return {"user_id": f"eq.{user['id']}"}


@router.get("")
def list_notifications(
    unread: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: SupabaseClient = Depends(get_db),
):
    filters = _visibility_filter(user)
    if unread:
        filters["is_read"] = "eq.false"
    params = {
        "select": _SELECT,
        "order": "created_at.desc",
        "limit": str(per_page),
        "offset": str((page - 1) * per_page),
        **filters,
    }
    try:
        rows = db.select("notifications", params)
        total = db.count("notifications", filters)
        unread_count = db.count("notifications", {**_visibility_filter(user), "is_read": "eq.false"})
    except SupabaseError as e:
        raise _db_error(e) from e
    return {
        "items": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "unread_count": unread_count,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/unread-count")
def unread_count(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        return {"unread_count": db.count("notifications", {**_visibility_filter(user), "is_read": "eq.false"})}
    except SupabaseError as e:
        raise _db_error(e) from e


def _may_access(db: SupabaseClient, user: dict, notification_id: str) -> dict:
    rows = db.select("notifications", {"select": "id,user_id", "id": f"eq.{notification_id}", "limit": "1"})
    if not rows:
        raise HTTPException(404, "Notifikasi tidak ditemukan")
    row = rows[0]
    if row.get("user_id") is None:
        if user.get("role") != "admin":
            raise HTTPException(403, "Akses ditolak")
    elif row["user_id"] != user["id"]:
        raise HTTPException(403, "Akses ditolak")
    return row


@router.patch("/{notification_id}/read")
def mark_read(notification_id: str, user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    try:
        _may_access(db, user, notification_id)
        rows = db.update("notifications", {"id": f"eq.{notification_id}"}, {"is_read": True})
    except SupabaseError as e:
        raise _db_error(e) from e
    return rows[0] if rows else {"id": notification_id, "is_read": True}


@router.post("/read-all")
def mark_all_read(user: dict = Depends(get_current_user), db: SupabaseClient = Depends(get_db)):
    updated = 0
    try:
        rows = db.update("notifications", {"user_id": f"eq.{user['id']}", "is_read": "eq.false"}, {"is_read": True})
        updated += len(rows or [])
        if user.get("role") == "admin":
            rows = db.update("notifications", {"user_id": "is.null", "is_read": "eq.false"}, {"is_read": True})
            updated += len(rows or [])
    except SupabaseError as e:
        raise _db_error(e) from e
    return {"ok": True, "updated": updated}
