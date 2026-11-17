"""Prompt kualifikasi lead (Fase 3). Versi disimpan di `lead_analysis.prompt_version`.

Fakta perusahaan diambil dari `config/company_profile.yaml` saat dipanggil (bukan
di-hardcode) supaya perubahan profil langsung berlaku.
"""
from __future__ import annotations

from ..services.company_profile import load_profile, profile_summary, services_list

PROMPT_VERSION = "lead-v1"

SYSTEM_TEMPLATE = """Anda analis bisnis B2B untuk:
{profile}

Tugas: menilai apakah perusahaan berikut cocok sebagai CALON PELANGGAN (lead) untuk layanan di atas.
Kembalikan HANYA objek JSON dengan skema:
{{
  "lead_score": integer,               // 0-100, kecocokan sebagai calon pelanggan
  "category": string,                  // salah satu: "HIGH", "MEDIUM", "LOW"
  "industry_classification": string,   // klasifikasi industri singkat (mis. "Pengelolaan Sampah")
  "potential_products": string[],      // produk/layanan yang mungkin dibutuhkan (HANYA dari daftar layanan di atas)
  "reason": string,                    // alasan skor, sebutkan bukti dari data perusahaan
  "suggested_approach": string         // saran singkat cara mendekati/menawarkan
}}

Aturan:
- JANGAN mengarang fakta perusahaan (sertifikasi, pengalaman, kapasitas, harga, spesifikasi) yang tidak ada di data.
- Bila data minim, beri skor konservatif dan jelaskan keterbatasannya di `reason`.
- Kategori harus konsisten dengan skor: >=70 HIGH, 40-69 MEDIUM, <40 LOW.
- `potential_products` hanya boleh berisi item dari daftar layanan di atas."""


def build_system_prompt(profile: dict | None = None) -> str:
    p = profile if profile is not None else load_profile()
    return SYSTEM_TEMPLATE.format(profile=profile_summary(p) or "(profil perusahaan belum diisi)")


def build_user_prompt(company: dict, contacts: list[dict] | None = None) -> str:
    lines = ["Data perusahaan calon pelanggan:"]
    fields = [
        ("Nama", company.get("name")),
        ("Industri", company.get("industry")),
        ("Kota", company.get("city")),
        ("Provinsi", company.get("province")),
        ("Alamat", company.get("address")),
        ("Website", company.get("website")),
        ("Deskripsi", company.get("description")),
        ("Sumber", company.get("source_name")),
    ]
    for label, value in fields:
        val = (str(value).strip() if value is not None else "")
        if val:
            lines.append(f"- {label}: {val}")

    emails = [c.get("value") for c in (contacts or []) if c.get("contact_type") == "email"]
    phones = [c.get("value") for c in (contacts or []) if c.get("contact_type") == "phone"]
    if emails:
        lines.append(f"- Email publik: {', '.join(str(e) for e in emails)}")
    if phones:
        lines.append(f"- Telepon publik: {', '.join(str(p) for p in phones)}")

    svcs = services_list(load_profile())
    lines.append("")
    lines.append(
        "Daftar layanan perusahaan kita (untuk `potential_products`): "
        + ("; ".join(svcs) if svcs else "(belum diisi)")
    )
    return "\n".join(lines)
