"""Prompt analisis tender + versi prompt. Versi disimpan di `tender_analysis.prompt_version`."""
from __future__ import annotations

PROMPT_VERSION = "tender-v1"

# Profil singkat perusahaan (dari konteks proyek): PT Green Eco Teknologi bergerak di
# pengelolaan sampah, mesin daur ulang, dan fasilitas lingkungan.
COMPANY_PROFILE = """PT Green Eco Teknologi (Indonesia) — perusahaan teknologi lingkungan.
Fokus:
- Peralatan & mesin pengelolaan sampah (pencacah/shredder, crusher, conveyor, replacement blade, spare part).
- Mesin & lini daur ulang plastik, Material Recovery Facility (MRF), waste sorting.
- Fasilitas lingkungan: pengolahan air limbah (IPAL), pengolahan limbah, incinerator, TPST.
- Peluang kerja sama pengadaan, penyediaan alat, instalasi, dan layanan terkait."""

SYSTEM_PROMPT = f"""Anda analis tender B2B untuk:
{COMPANY_PROFILE}

Tugas: menilai relevansi satu paket pengadaan terhadap kemampuan perusahaan di atas.
Kembalikan HANYA objek JSON dengan skema:
{{
  "category": string,            // salah satu: "Waste Management", "Recycling Equipment",
                                 // "Industrial Machinery", "Environmental Facilities",
                                 // "Water Treatment", "Other"
  "relevance_score": integer,    // 0-100, seberapa relevan dengan perusahaan
  "priority": string,            // "HIGH" | "MEDIUM" | "LOW"
  "score_reason": string,        // alasan singkat skor (wajib, 1-3 kalimat)
  "equipment_needs": string,     // peralatan/produk yang mungkin dibutuhkan
  "cooperation_opportunity": string, // bentuk kerja sama yang mungkin
  "key_requirements": string,    // syarat penting (kualifikasi, sertifikat, dll.)
  "deadline_flag": string        // catatan urgensi tenggat, mis. "Deadline dekat" / "Tidak mendesak"
}}

Aturan: nilai jujur berdasarkan teks yang tersedia; jangan mengarang fakta. Jika data
minim, beri skor rendah dan jelaskan keterbatasannya. Bahasa alasan: Indonesia."""


def build_user_prompt(tender: dict) -> str:
    """Bentuk prompt pengguna dari baris `tenders` (data mentah, apa adanya)."""
    fields = [
        ("Nama paket", tender.get("package_name")),
        ("Instansi", tender.get("agency")),
        ("Lokasi", tender.get("location")),
        ("Jenis pengadaan", tender.get("procurement_type")),
        ("Status/tahap", tender.get("status")),
        ("Deskripsi", tender.get("description")),
        ("Spesifikasi teknis", tender.get("technical_specs")),
        ("Nilai HPS", tender.get("hps")),
        ("Pagu", tender.get("budget_ceiling")),
        ("Syarat kualifikasi", tender.get("participant_requirements")),
        ("Deadline penawaran", tender.get("bid_deadline")),
        ("Keyword cocok", ", ".join(tender.get("matched_keywords") or [])),
    ]
    lines = [f"- {label}: {value}" for label, value in fields if value not in (None, "", [])]
    return "Data paket pengadaan:\n" + "\n".join(lines) + "\n\nNilai relevansi paket ini."
