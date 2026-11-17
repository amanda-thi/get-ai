"""Registry adapter: `adapter_type` (kolom `tender_sources.adapter_type`) -> kelas adapter.

Tipe yang didukung otomatis: `spse` (SPSE Nasional, publik, teruji) dan `inaproc`
(API Gateway resmi, butuh token). Tipe lain dikenali skema tapi belum/tidak bisa
diambil otomatis — dijelaskan alasannya, bukan dibiarkan gagal tanpa pesan.
"""
from __future__ import annotations

from ..config import Settings
from .base import SourceAdapter, SourceError
from .inaproc_api import InaprocApiAdapter
from .spse_nasional import SpseNasionalAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "spse": SpseNasionalAdapter,
    "inaproc": InaprocApiAdapter,
}

# Tipe yang dikenal skema tapi belum didukung otomatis (butuh login / HTML kustom / manual).
UNSUPPORTED: dict[str, str] = {
    "sirup": "SIRUP (sirup.inaproc.id) butuh login; tidak ada endpoint RUP publik.",
    "generic_html": "Adapter HTML generik belum diimplementasikan.",
    "manual": "Sumber manual: data dimasukkan admin, bukan diambil otomatis.",
}


def adapter_class(adapter_type: str | None) -> type[SourceAdapter] | None:
    return ADAPTERS.get((adapter_type or "").strip().lower())


def build_adapter(
    source: dict, settings: Settings, client=None
) -> SourceAdapter:
    """Bangun adapter untuk satu baris `tender_sources`. SourceError bila tipe tak didukung."""
    atype = (source.get("adapter_type") or "").strip().lower()
    cls = adapter_class(atype)
    if cls is None:
        reason = UNSUPPORTED.get(atype, f"adapter_type '{atype}' tidak dikenal")
        raise SourceError(reason)
    return cls(source, settings, client=client)
