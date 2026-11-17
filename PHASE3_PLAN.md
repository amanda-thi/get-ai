# Fase 3 — AI Marketing & Business Outreach

Rencana teknis + status verifikasi. Ditulis setelah meninjau kode Fase 1 & Fase 2,
lalu menguji alur discovery + kualifikasi AI **pada situs web nyata** (bukan asumsi).

> Prinsip: **tidak ada data dummy di produksi**, **tidak mengklaim integrasi yang belum diuji**,
> **tidak melewati login/CAPTCHA/paywall**, **menghormati `robots.txt`**,
> **AI tidak boleh mengarang fakta perusahaan** (hanya dari DB & `config/company_profile.yaml`),
> desain, branding, routing, dan auth Fase 1/2 dipertahankan.

---

## 1. Ringkasan hasil inspeksi Fase 1 & Fase 2

| Bagian | Kondisi |
|---|---|
| DB | `001_init.sql` sudah menyediakan **semua tabel Fase 3**: `companies`, `company_contacts`, `company_leads`, `lead_analysis`, `email_templates`, `outreach_campaigns`, `outreach_messages`, `outreach_logs`. Guard DB: email berstatus `approved`/`sent` **wajib** punya `approved_by` + `approved_at` (constraint `chk_approval_required`). |
| Backend | FastAPI. Klien Supabase tipis (`app/db.py`) sudah punya `select/insert/update/upsert/delete/count`. Auth JWT + role admin/staff (`app/deps.py`). |
| Frontend | React 19 + Vite + Tailwind v4. `/leads` & `/outreach` masih `Placeholder.jsx`. |
| Test | 89 test lulus (Fase 1 + Fase 2). |

**Keputusan penting:** **memakai kembali tabel Fase 1** alih-alih membuat tabel baru seperti
yang disarankan draf spesifikasi. Skema Fase 1 sudah lengkap dan menjadi acuan tunggal;
membuat tabel baru akan menduplikasi data & memutus relasi Fase 1.

---

## 2. Riset & verifikasi sumber discovery

Discovery perusahaan tidak punya "sumber publik" tunggal seperti SPSE pada Fase 2. Karena itu
pendekatan dibuat berlapis, dan **hanya yang benar-benar berfungsi yang diaktifkan**:

| Metode | Status | Catatan |
|---|---|---|
| **Tambah manual** | **BERFUNGSI** | Admin mengetik data perusahaan. Sumber ditandai `manual`. |
| **Pengumpulan dari URL situs web** | **BERFUNGSI (teruji live)** | Membuka halaman publik (beranda + halaman kontak/tentang yang ditautkan), mengekstrak email/telepon bisnis yang **tertera publik**. Menghormati `robots.txt`; tidak login, tidak melewati CAPTCHA. |
| **Impor daftar (bulk)** | **BERFUNGSI** | Tempel daftar (dipisah `\|`), dedupe otomatis. |
| **Pencarian kata kunci** | **BERFUNGSI (teruji live)** | Adapter `serper` & `tavily`; aktif setelah `LEAD_SEARCH_PROVIDER` + `LEAD_SEARCH_API_KEY` diisi. Tanpa kunci → pesan jelas, **bukan hasil palsu**. |

**Tidak dilakukan (dan alasannya):**
- Tidak ada sumber "daftar perusahaan" publik & legal yang bisa di-scrape bebas; mengarang hasil
  akan melanggar prinsip no-dummy.
- Tidak menembus `robots.txt` (`utils/web.py::robots_allows`) maupun login/CAPTCHA/paywall.
- Tidak mengekstrak email personal yang tidak dipublikasikan perusahaan.

---

## 3. Arsitektur yang ditambahkan (tanpa membongkar Fase 1/2)

```
backend/app/
  config.py                 (+) SMTP, batas lead/outreach, kunci pencarian, path profil
  services/company_profile.py (+) baca config/company_profile.yaml (satu sumber fakta AI)
  utils/web.py              (+) normalisasi URL, robots.txt, fetch HTML, ekstrak email/telepon/judul/deskripsi
  discovery/
    base.py                 (+) RawCompany, RawContact, DiscoveryError
    website.py              (+) collect_from_url (beranda + halaman kontak)
    search.py               (+) search_companies (Serper; butuh kunci)
  services/leads.py         (+) normalisasi nama, cari duplikat, simpan, discovery, kontak
  ai/lead_prompts.py        (+) prompt kualifikasi + prompt_version
  ai/lead_validate.py       (+) validasi output kualifikasi sebelum disimpan
  ai/lead_service.py        (+) qualify_company() via Groq/OpenAI
  ai/outreach_prompts.py    (+) prompt email (id/en/ko) + EMAIL_TYPES/LANGUAGES
  ai/outreach_service.py    (+) generate_email()
  services/lead_analysis.py (+) analyze_company, analyze_pending, simpan (is_current)
  services/mailer.py        (+) SMTP via stdlib smtplib (kredensial hanya backend)
  services/outreach.py      (+) create/update/status/approve/kirim email + log
  routers/leads.py          (+) listing, detail, discovery, kualifikasi, kontak
  routers/outreach.py       (+) config, template, campaign, pesan, generate, approve, kirim
frontend/src/
  pages/Leads.jsx           (+) listing + panel discovery (manual/URL/impor/pencarian)
  pages/LeadDetail.jsx      (+) detail, kontak, kualifikasi AI, riwayat, email terkait
  pages/Outreach.jsx        (+) tab Pesan / Template / Kampanye
  pages/OutreachMessage.jsx (+) edit, setujui, kirim, riwayat
  lib/format.js, App.jsx, index.css  (ubah minimal, gaya Fase 1 dipertahankan)
```

**Alur discovery:** input (manual/impor/URL/pencarian) → `RawCompany` → normalisasi nama + deteksi
duplikat (`normalized_name` + domain situs) → simpan `companies` → simpan `company_contacts`
(wajib ada `source_url`) → `_ensure_lead` membuat baris `company_leads` status `new`.

**Alur kualifikasi AI:** perusahaan → prompt (data DB + profil perusahaan) → Groq/OpenAI →
**validasi** (skor 0–100, kategori, alasan wajib) → `lead_analysis` (`is_current=true`, versi lama
di-`is_current=false`). Data mentah `companies` **tidak pernah** diubah AI.

**Alur email outreach:** pilih lead + jenis + bahasa (+ template opsional) → AI menulis draft dari
profil perusahaan & data lead → simpan `outreach_messages` status `draft` → admin **menyetujui**
(`approved`, tercatat `approved_by`/`approved_at`) → admin **mengirim** via SMTP → status `sent`
+ `provider_message_id`, atau `failed` + pesan error. Setiap langkah dicatat di `outreach_logs`.

**Anti-mengarang fakta:** prompt menyertakan `config/company_profile.yaml` dan daftar
`forbidden_claims_unless_listed_above` (sertifikasi, pengalaman, kapasitas, harga, spesifikasi).
AI dilarang mengklaim hal di luar daftar `approved_claims`. Output tetap **draft** yang harus
disetujui admin sebelum terkirim.

---

## 4. Kontrak API baru

| Method | Path | Guna |
|---|---|---|
| GET | `/api/leads` | listing (view `leads_with_analysis`): `q, status, category, industry, province, city, sort, order, page, per_page` |
| POST | `/api/leads/discover` | kumpulkan: `{items?}` \| `{urls?}` \| `{query?, industry?, location?, limit?}` |
| POST | `/api/leads` | tambah satu perusahaan manual |
| GET | `/api/leads/{company_id}` | detail + lead + kontak + riwayat kualifikasi + email terkait |
| PATCH | `/api/leads/{company_id}` | ubah data perusahaan dan/atau `status`/`notes` lead |
| DELETE | `/api/leads/{company_id}` | hapus perusahaan (admin, cascade) |
| POST | `/api/leads/{company_id}/qualify` | kualifikasi AI satu perusahaan |
| POST | `/api/leads/analyze-pending` | kualifikasi massal (dibatasi batch) |
| POST | `/api/leads/{company_id}/contacts` | tambah kontak publik |
| DELETE | `/api/leads/contacts/{contact_id}` | hapus kontak |
| GET | `/api/outreach/config` | status fitur (`smtp_configured`, `ai_configured`, jenis email, bahasa) |
| GET/POST/PATCH/DELETE | `/api/outreach/templates` | kelola template (tulis: admin) |
| GET/POST/PATCH | `/api/outreach/campaigns` | kelola kampanye (tulis: admin) |
| GET | `/api/outreach/messages` | listing pesan: `q, status, email_type, language, lead_id, campaign_id, sort, order, page, per_page` |
| POST | `/api/outreach/generate` | buat draft email via AI |
| POST | `/api/outreach/messages` | simpan email manual sebagai draft |
| GET/PATCH | `/api/outreach/messages/{id}` | detail + riwayat, dan edit |
| POST | `/api/outreach/messages/{id}/status` | ubah status (mis. `saved_for_later`) |
| POST | `/api/outreach/messages/{id}/approve` | setujui (admin) |
| POST | `/api/outreach/messages/{id}/send` | kirim via SMTP (admin, wajib sudah disetujui) |

---

## 5. Status vocabulary (keputusan)

Nilai status di DB Fase 1 dipertahankan (tidak mengubah CHECK constraint). UI memetakan sebagian
label ke istilah spesifikasi:

| Nilai DB | Label UI |
|---|---|
| `new` | New |
| `qualified` | Qualified |
| `contacted` | Contacted |
| `responded` | Responded |
| `negotiation` | Interested |
| `won` | Converted |
| `lost` | Not Interested |
| `do_not_contact` | Do Not Contact |

---

## 6. Migrasi

`008_phase3_leads_view.sql` (jalankan **setelah** 001–007, non-destruktif & idempoten):
1. Membuat **view `leads_with_analysis`** (`security_invoker=true`) yang meratakan lead
   (`lead_*`) + analisis terkini (`analysis_*`) — agar listing bisa mengurutkan berdasarkan
   skor & memfilter kategori/status (relasi `company_leads → lead_analysis` satu-ke-banyak,
   PostgREST menolak order via embed: PGRST118). Pola sama dengan `tenders_with_analysis` (007).
2. `grant select` ke `authenticated`/`service_role` + `notify pgrst, 'reload schema'`.

`009_phase3_outreach_columns.sql` (jalankan **setelah** 008, non-destruktif & idempoten):
1. Menambah `outreach_messages.template_id` dan `outreach_messages.ai_model` (audit).
   Perbaikan untuk DB yang menjalankan 008 versi lama (view saja).
2. `notify pgrst, 'reload schema'`.

**Tanpa migrasi ini:** `GET /api/leads` → 503 (`view tidak ditemukan`) dan
`GET /api/outreach/messages` → 503 (`kolom ai_model tidak ada`). Fitur lain (config, template,
kampanye, discovery, kualifikasi, detail lead) tetap berfungsi.

---

## 7. Rencana implementasi bertahap (tiap langkah diuji sebelum lanjut)

1. **Fondasi** — `config.py`, `utils/web.py`, `services/company_profile.py`. Test unit.
2. **Discovery** — `discovery/{base,website,search}.py` + `services/leads.py`. Test mock + uji live terkontrol.
3. **AI kualifikasi** — prompt, validasi, service, `services/lead_analysis.py`. Test mock + validasi.
4. **Router leads** — listing/detail/discovery/kualifikasi/kontak. Test API.
5. **Outreach** — `services/mailer.py`, `services/outreach.py`, prompt email. Test mock SMTP.
6. **Router outreach** — config/template/campaign/pesan/generate/approve/kirim. Test API.
7. **Frontend** — Leads, LeadDetail, Outreach (3 tab), OutreachMessage. Build lulus.
8. **Dokumentasi** — README/TESTING/GUIDE diperbarui (apa yang teruji, apa yang butuh kredensial).

---

## 8. Yang TIDAK diklaim berfungsi tanpa kredensial

- **Kirim email** — butuh `SMTP_*`. Tanpa itu draft tetap bisa dibuat & disetujui, tetapi
  `send` mengembalikan 502 dengan pesan jelas.
- **Pencarian perusahaan berbasis kata kunci** — butuh `LEAD_SEARCH_API_KEY` (provider `serper` atau `tavily`); sudah teruji live dengan Tavily.
- **Kualifikasi & penulisan email AI** — butuh `GROQ_API_KEY`/`OPENAI_API_KEY`.
  (Di lingkungan ini kunci AI **sudah terisi**, jadi kedua fitur AI teruji live.)
- **SIRUP / INAPROC** — sama seperti Fase 2 (login / butuh token).
