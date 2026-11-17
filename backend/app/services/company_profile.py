"""Profil perusahaan (PT Green Eco Teknologi) untuk AI marketing.

Satu-satunya sumber fakta perusahaan. Dibaca dari `config/company_profile.yaml`.
AI DILARANG mengarang fakta (sertifikasi, pengalaman, kapasitas, harga, spesifikasi)
yang tidak tercantum di sini — lihat `forbidden_claims_unless_listed_above`.
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from ..config import Settings, get_settings


@lru_cache(maxsize=8)
def _load_cached(path_str: str, _mtime: float) -> dict:
    with open(path_str, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def load_profile(settings: Settings | None = None) -> dict:
    """Muat profil. File hilang/kosong -> dict kosong (AI tetap dilarang mengarang)."""
    settings = settings or get_settings()
    path = settings.company_profile_file
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    return _load_cached(str(path), mtime)


def services_list(profile: dict) -> list[str]:
    return [str(s).strip() for s in (profile.get("services") or []) if str(s).strip()]


def forbidden_claims(profile: dict) -> list[str]:
    return [str(s).strip() for s in (profile.get("forbidden_claims_unless_listed_above") or []) if str(s).strip()]


def profile_summary(profile: dict | None = None) -> str:
    """Ringkasan teks untuk prompt. Hanya fakta yang ada; field kosong dilewati."""
    p = profile if profile is not None else load_profile()
    lines: list[str] = []
    name = str(p.get("company_name") or "").strip()
    if name:
        lines.append(f"Perusahaan: {name}")
    website = str(p.get("website") or "").strip()
    if website:
        lines.append(f"Website: {website}")

    contact = p.get("contact") or {}
    if isinstance(contact, dict):
        for key, label in (("email", "Email"), ("phone", "Telepon"), ("address", "Alamat")):
            val = str(contact.get(key) or "").strip()
            if val:
                lines.append(f"{label}: {val}")

    svcs = services_list(p)
    if svcs:
        lines.append("Layanan yang ditawarkan:")
        lines.extend(f"- {s}" for s in svcs)

    approved = [str(a).strip() for a in (p.get("approved_claims") or []) if str(a).strip()]
    if approved:
        lines.append("Klaim terverifikasi (boleh disebut):")
        lines.extend(f"- {a}" for a in approved)

    forbidden = forbidden_claims(p)
    if forbidden:
        lines.append(
            "JANGAN membuat klaim tentang hal berikut kecuali tercantum di atas: "
            + ", ".join(forbidden)
        )
    return "\n".join(lines)


def is_usable(profile: dict | None = None) -> bool:
    """Profil dianggap cukup untuk AI bila ada nama perusahaan (agar prompt tidak kosong)."""
    p = profile if profile is not None else load_profile()
    return bool(str(p.get("company_name") or "").strip())
