"""Tipe dasar lead discovery."""
from __future__ import annotations

from dataclasses import dataclass, field


class DiscoveryError(Exception):
    """Gagal mengumpulkan data perusahaan (tidak dikonfigurasi, jaringan, diblokir, input salah)."""


@dataclass
class RawContact:
    """Kontak bisnis publik beserta halaman sumbernya (wajib ada sumber)."""

    contact_type: str  # 'email' | 'phone'
    value: str
    source_url: str


@dataclass
class RawCompany:
    """Data mentah satu perusahaan. Field None = tidak tersedia di sumber."""

    name: str
    source_name: str
    source_url: str
    website: str | None = None
    industry: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    contacts: list[RawContact] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)
