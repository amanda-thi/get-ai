"""Prompt pembuatan email outreach (Fase 3). Versi disimpan di `outreach_messages.prompt_version`.

Fakta perusahaan hanya dari `config/company_profile.yaml`. AI dilarang mengarang
sertifikasi/pengalaman/kapasitas/harga/spesifikasi.
"""
from __future__ import annotations

from ..services.company_profile import load_profile, profile_summary

PROMPT_VERSION = "outreach-v1"

EMAIL_TYPES = (
    "company_intro",
    "product_intro",
    "partnership_proposal",
    "service_offering",
    "follow_up",
)
LANGUAGES = ("id", "en", "ko")

_EMAIL_TYPE_LABEL = {
    "company_intro": "Perkenalan perusahaan",
    "product_intro": "Perkenalan produk",
    "partnership_proposal": "Proposal kerja sama",
    "service_offering": "Penawaran layanan",
    "follow_up": "Tindak lanjut (follow-up)",
}
_LANGUAGE_LABEL = {"id": "Bahasa Indonesia", "en": "English", "ko": "한국어 (Korean)"}

SYSTEM_TEMPLATE = """Anda penulis email bisnis B2B untuk:
{profile}

Tugas: tulis SATU email penawaran kepada perusahaan calon pelanggan.
Kembalikan HANYA objek JSON dengan skema:
{{
  "subject": string,   // subjek email, singkat dan spesifik
  "body": string       // isi email teks biasa (bukan HTML), dengan salam, isi, ajakan, dan tanda tangan
}}

Aturan:
- Tulis dalam bahasa yang diminta.
- JANGAN mengarang fakta: sertifikasi, pengalaman proyek, kapasitas, harga, spesifikasi, atau nama kontak yang tidak ada.
- Sebutkan HANYA layanan yang tercantum di profil di atas.
- Sertakan tanda tangan dengan nama perusahaan; sertakan kontak HANYA bila ada di profil.
- Nada profesional, ringkas (maks ~180 kata), tanpa klaim berlebihan."""


def build_system_prompt(profile: dict | None = None) -> str:
    p = profile if profile is not None else load_profile()
    return SYSTEM_TEMPLATE.format(profile=profile_summary(p) or "(profil perusahaan belum diisi)")


def build_user_prompt(
    company: dict,
    contacts: list[dict] | None,
    email_type: str,
    language: str,
    *,
    instructions: str | None = None,
    template: dict | None = None,
) -> str:
    lines = [
        f"Jenis email: {_EMAIL_TYPE_LABEL.get(email_type, email_type)}",
        f"Bahasa: {_LANGUAGE_LABEL.get(language, language)}",
        "",
        "Perusahaan tujuan:",
    ]
    fields = [
        ("Nama", company.get("name")),
        ("Industri", company.get("industry")),
        ("Kota", company.get("city")),
        ("Provinsi", company.get("province")),
        ("Website", company.get("website")),
        ("Deskripsi", company.get("description")),
    ]
    for label, value in fields:
        val = (str(value).strip() if value is not None else "")
        if val:
            lines.append(f"- {label}: {val}")

    emails = [c.get("value") for c in (contacts or []) if c.get("contact_type") == "email"]
    if emails:
        lines.append(f"- Email tujuan: {', '.join(str(e) for e in emails)}")

    if template:
        lines.append("")
        lines.append("Contoh/kerangka dari template (patuhi gaya, perbarui isi agar spesifik):")
        lines.append(f"Subjek contoh: {template.get('subject', '')}")
        lines.append(f"Isi contoh:\n{template.get('body', '')}")

    if instructions:
        lines.append("")
        lines.append(f"Instruksi tambahan dari admin: {instructions.strip()}")

    return "\n".join(lines)
