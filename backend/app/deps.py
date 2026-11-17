from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .db import SupabaseClient, SupabaseError

bearer = HTTPBearer(auto_error=False)


@lru_cache
def _client() -> SupabaseClient:
    s = get_settings()
    return SupabaseClient(s.supabase_url, s.supabase_service_role_key, s.supabase_anon_key)


def get_db() -> SupabaseClient:
    try:
        return _client()
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: SupabaseClient = Depends(get_db),
) -> dict:
    if creds is None:
        raise HTTPException(401, "Token tidak ada")
    try:
        auth_user = db.get_user(creds.credentials)
        if not auth_user:
            raise HTTPException(401, "Token tidak valid atau kedaluwarsa")
        rows = db.select(
            "users",
            {"id": f"eq.{auth_user['id']}", "select": "id,email,full_name,role,is_active", "limit": "1"},
        )
    except SupabaseError as e:
        raise HTTPException(503, str(e)) from e
    if not rows or not rows[0]["is_active"]:
        raise HTTPException(403, "Akun tidak aktif atau belum terdaftar")
    return rows[0]


def require_role(*roles: str):
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Akses ditolak untuk role ini")
        return user

    return checker
