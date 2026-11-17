"""Tipe dasar & antarmuka adapter sumber tender.

Setiap adapter mengambil data dari satu portal resmi/terbuka dan mengembalikan
`RawTender` yang belum diubah AI. Adapter TIDAK menulis ke database — itu tugas
`services/collection.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

from ..config import Settings


class SourceError(Exception):
    """Gagal mengambil data dari sumber (jaringan, parsing, diblokir, tidak dikonfigurasi)."""


@dataclass
class RawTender:
    """Data mentah satu tender dari sumber. Field None = tidak tersedia di sumber."""

    package_name: str
    source_url: str
    external_id: str | None = None
    agency: str | None = None
    location: str | None = None
    procurement_type: str | None = None
    description: str | None = None
    technical_specs: str | None = None
    budget_ceiling: float | None = None
    hps: float | None = None
    announced_at: date | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    bid_deadline: datetime | None = None
    participant_requirements: str | None = None
    status: str | None = None
    matched_keywords: list[str] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)


@dataclass
class HealthResult:
    ok: bool
    status: str  # ok | failed | blocked | manual_only
    message: str = ""


class SourceAdapter:
    """Kelas dasar adapter. Subclass mengisi `adapter_type` dan `discover()`."""

    adapter_type = "generic"

    def __init__(self, source: dict, settings: Settings, client: httpx.Client | None = None):
        self.source = source
        self.settings = settings
        self.base_url = (source.get("base_url") or "").rstrip("/")
        self.config = source.get("config") or {}
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.spse_user_agent},
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "SourceAdapter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def health_check(self) -> HealthResult:  # pragma: no cover - override
        raise NotImplementedError

    def discover(self, keywords: list[str], options: dict | None = None) -> list[RawTender]:
        raise NotImplementedError

    def enrich(self, tender: RawTender) -> RawTender:  # pragma: no cover - opsional
        return tender
