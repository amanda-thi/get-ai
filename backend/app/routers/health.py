from fastapi import APIRouter

from ..config import get_settings
from ..db import SupabaseError
from ..deps import _client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health():
    return {"status": "ok"}


@router.get("/db")
def health_db():
    if not get_settings().db_configured:
        return {"status": "not_configured"}
    try:
        _client().count("tender_sources")
        return {"status": "ok"}
    except SupabaseError as e:
        return {"status": "error", "detail": str(e)}
