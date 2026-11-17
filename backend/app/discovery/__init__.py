"""Lead discovery (Fase 3): kumpulkan calon perusahaan dari sumber publik.

Modul ini hanya MENGUMPULKAN data mentah (tidak menulis DB). Penyimpanan + dedupe
ada di `services/leads.py`. Tidak ada data dummy: bila sumber tidak tersedia,
kesalahan dikembalikan apa adanya.
"""
from .base import DiscoveryError, RawCompany, RawContact

__all__ = ["DiscoveryError", "RawCompany", "RawContact"]
