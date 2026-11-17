"""Klien tipis untuk Supabase (PostgREST + Auth) memakai service role key. Hanya dipakai backend."""
from __future__ import annotations

import httpx


class SupabaseError(Exception):
    pass


def is_conflict_error(exc: Exception) -> bool:
    """True bila galat berasal dari pelanggaran unique/duplikat (HTTP 409/23505).

    Dipakai untuk mendeteksi tabrakan lock job (job aktif ganda) dan dedupe
    notifikasi tanpa harus membedah tipe galat.
    """
    s = str(exc)
    return "(409)" in s or "23505" in s or "duplicate key" in s.lower()


def is_missing_table_error(exc: Exception) -> bool:
    """True bila tabel belum ada (migrasi belum dijalankan): PostgREST PGRST205 / Postgres 42P01."""
    s = str(exc)
    return "PGRST205" in s or "42P01" in s or "schema cache" in s


class SupabaseClient:
    def __init__(self, url: str, service_key: str, anon_key: str = "", timeout: float = 10.0):
        if not url or not service_key:
            raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY belum diisi")
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.anon_key = anon_key or service_key
        self.http = httpx.Client(timeout=timeout)

    def _rest_headers(self, extra: dict | None = None) -> dict:
        h = {"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"}
        if extra:
            h.update(extra)
        return h

    def get_user(self, token: str) -> dict | None:
        """Validasi JWT user ke Supabase Auth. None jika token tidak valid."""
        try:
            r = self.http.get(
                f"{self.url}/auth/v1/user",
                headers={"apikey": self.anon_key, "Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as e:
            raise SupabaseError(f"Auth service tidak terjangkau: {e}") from e
        if r.status_code in (401, 403):
            return None
        if r.status_code != 200:
            raise SupabaseError(f"Auth service error {r.status_code}")
        return r.json()

    def select(self, table: str, params: dict | None = None) -> list[dict]:
        try:
            r = self.http.get(f"{self.url}/rest/v1/{table}", params=params or {}, headers=self._rest_headers())
        except httpx.HTTPError as e:
            raise SupabaseError(f"DB tidak terjangkau: {e}") from e
        if r.status_code != 200:
            raise SupabaseError(f"select {table} gagal ({r.status_code}): {r.text[:200]}")
        return r.json()

    def insert(
        self,
        table: str,
        rows: dict | list[dict],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
        returning: bool = True,
    ) -> list[dict]:
        """INSERT (atau UPSERT) via PostgREST. Mengembalikan baris hasil bila returning."""
        payload = rows if isinstance(rows, list) else [rows]
        prefer = "resolution=merge-duplicates," if upsert else ""
        prefer += "return=representation" if returning else "return=minimal"
        params = {"on_conflict": on_conflict} if on_conflict else {}
        try:
            r = self.http.post(
                f"{self.url}/rest/v1/{table}",
                params=params,
                headers=self._rest_headers({"Content-Type": "application/json", "Prefer": prefer}),
                json=payload,
            )
        except httpx.HTTPError as e:
            raise SupabaseError(f"DB tidak terjangkau: {e}") from e
        if r.status_code not in (200, 201, 204):
            raise SupabaseError(f"insert {table} gagal ({r.status_code}): {r.text[:300]}")
        return r.json() if returning and r.text else []

    def update(self, table: str, filters: dict, values: dict, *, returning: bool = True) -> list[dict]:
        """UPDATE ... WHERE (filters PostgREST, mis. {'id': 'eq.<uuid>'})."""
        prefer = "return=representation" if returning else "return=minimal"
        try:
            r = self.http.patch(
                f"{self.url}/rest/v1/{table}",
                params=filters,
                headers=self._rest_headers({"Content-Type": "application/json", "Prefer": prefer}),
                json=values,
            )
        except httpx.HTTPError as e:
            raise SupabaseError(f"DB tidak terjangkau: {e}") from e
        if r.status_code not in (200, 204):
            raise SupabaseError(f"update {table} gagal ({r.status_code}): {r.text[:300]}")
        return r.json() if returning and r.text else []

    def delete(self, table: str, filters: dict) -> None:
        try:
            r = self.http.delete(
                f"{self.url}/rest/v1/{table}", params=filters, headers=self._rest_headers()
            )
        except httpx.HTTPError as e:
            raise SupabaseError(f"DB tidak terjangkau: {e}") from e
        if r.status_code not in (200, 204):
            raise SupabaseError(f"delete {table} gagal ({r.status_code}): {r.text[:300]}")

    def count(self, table: str, filters: dict | None = None, select: str = "id") -> int:
        params = {"select": select, "limit": "1", **(filters or {})}
        try:
            r = self.http.get(
                f"{self.url}/rest/v1/{table}",
                params=params,
                headers=self._rest_headers({"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"}),
            )
        except httpx.HTTPError as e:
            raise SupabaseError(f"DB tidak terjangkau: {e}") from e
        if r.status_code not in (200, 206):
            raise SupabaseError(f"count {table} gagal ({r.status_code}): {r.text[:200]}")
        total = r.headers.get("content-range", "*/0").split("/")[-1]
        return int(total) if total.isdigit() else 0
