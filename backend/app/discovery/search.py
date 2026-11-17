"""Discovery perusahaan berbasis kata kunci via API pencarian (butuh kunci).

Tidak ada sumber pencarian gratis yang legal untuk daftar perusahaan, jadi fitur ini
aktif HANYA bila `LEAD_SEARCH_API_KEY` diisi (provider `serper` atau `tavily`,
lihat .env.example). Tanpa kunci -> `DiscoveryError` yang jelas, bukan hasil palsu.
"""
from __future__ import annotations

import httpx

from ..config import Settings
from ..utils.web import normalize_url
from .base import DiscoveryError, RawCompany

# Provider yang didukung. `search_companies` memilih adapter sesuai
# `LEAD_SEARCH_PROVIDER`; provider lain -> pesan jelas, bukan hasil kosong.
_SUPPORTED = ("serper", "tavily")


def _build_query(keyword: str, industry: str | None, location: str | None) -> str:
    parts = [keyword.strip()]
    if industry:
        parts.append(industry.strip())
    if location:
        parts.append(location.strip())
    q = " ".join(p for p in parts if p)
    if "perusahaan" not in q.lower() and "company" not in q.lower():
        q = f"{q} perusahaan"
    return q


def _raise_for_status(r: httpx.Response, provider: str) -> None:
    """Terjemahkan kode error HTTP provider jadi `DiscoveryError` yang informatif."""
    if r.status_code in (401, 403):
        raise DiscoveryError(
            f"API pencarian {provider} menolak kunci (401/403) — periksa LEAD_SEARCH_API_KEY."
        )
    if r.status_code == 429:
        raise DiscoveryError(f"Kuota API pencarian {provider} habis (429) — coba lagi nanti.")
    if r.status_code in (432, 433, 434):
        raise DiscoveryError(
            f"Batas paket API pencarian {provider} tercapai ({r.status_code}) — periksa kuota/plan."
        )
    if r.status_code != 200:
        raise DiscoveryError(f"API pencarian {provider} error {r.status_code}: {r.text[:200]}")


def _serper(query: str, limit: int, settings: Settings, client: httpx.Client) -> list[dict]:
    """Adapter Serper (google.serper.dev). Kembalikan item ternormalisasi."""
    try:
        r = client.post(
            f"{settings.lead_search_base_url.rstrip('/')}/search",
            headers={"X-API-KEY": settings.lead_search_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": min(max(limit, 1), 20), "gl": "id", "hl": "id"},
        )
    except httpx.HTTPError as e:
        raise DiscoveryError(f"Layanan pencarian tidak terjangkau: {e}") from e
    _raise_for_status(r, "serper")
    try:
        data = r.json().get("organic") or []
    except ValueError as e:
        raise DiscoveryError(f"Respons API pencarian tak terduga: {e}") from e
    return [
        {
            "title": (it.get("title") or "").strip(),
            "url": it.get("link") or it.get("url"),
            "content": (it.get("snippet") or "").strip(),
        }
        for it in data
    ]


def _tavily(query: str, limit: int, settings: Settings, client: httpx.Client) -> list[dict]:
    """Adapter Tavily (api.tavily.com). Auth via header Bearer; `max_results` maks 20."""
    try:
        r = client.post(
            f"{settings.lead_search_base_url.rstrip('/')}/search",
            headers={"Authorization": f"Bearer {settings.lead_search_api_key}", "Content-Type": "application/json"},
            json={
                "query": query,
                "max_results": min(max(limit, 1), 20),
                "search_depth": "basic",
                "topic": "general",
                "country": "indonesia",
            },
        )
    except httpx.HTTPError as e:
        raise DiscoveryError(f"Layanan pencarian tidak terjangkau: {e}") from e
    _raise_for_status(r, "tavily")
    try:
        data = r.json().get("results") or []
    except ValueError as e:
        raise DiscoveryError(f"Respons API pencarian tak terduga: {e}") from e
    return [
        {
            "title": (it.get("title") or "").strip(),
            "url": it.get("url"),
            "content": (it.get("content") or "").strip(),
        }
        for it in data
    ]


_ADAPTERS = {"serper": _serper, "tavily": _tavily}


def search_companies(
    keyword: str,
    *,
    industry: str | None = None,
    location: str | None = None,
    limit: int = 10,
    settings: Settings,
    client: httpx.Client | None = None,
) -> list[RawCompany]:
    """Cari calon perusahaan berdasarkan kata kunci + industri + lokasi."""
    if not keyword or not keyword.strip():
        raise DiscoveryError("Kata kunci wajib diisi untuk pencarian.")
    if not settings.lead_search_configured:
        raise DiscoveryError(
            "Pencarian perusahaan butuh kunci API (LEAD_SEARCH_API_KEY, provider serper/tavily). "
            "Sementara itu, tambah perusahaan secara manual atau lewat URL situs web."
        )

    provider = (settings.lead_search_provider or "").strip().lower()
    if provider not in _ADAPTERS:
        raise DiscoveryError(
            f"Provider pencarian '{provider}' belum didukung (tersedia: {', '.join(_SUPPORTED)})."
        )

    query = _build_query(keyword, industry, location)
    owns = client is None
    client = client or httpx.Client(timeout=settings.http_timeout, follow_redirects=True)
    try:
        items = _ADAPTERS[provider](query, limit, settings, client)
    finally:
        if owns:
            client.close()

    results: list[RawCompany] = []
    for item in items[:limit]:
        link = item.get("url")
        website = normalize_url(link)
        title = item.get("title") or ""
        if not title or not website:
            continue
        results.append(
            RawCompany(
                name=title,
                website=website,
                description=item.get("content") or None,
                industry=industry,
                source_name=f"search:{provider}",
                source_url=link,
                raw_payload={"query": query, "provider": provider},
            )
        )
    return results
