# Green Eco AI Business Automation — PT Green Eco Teknologi

Aplikasi internal: monitoring tender lingkungan + marketing outreach berbasis AI.

**Status: Fase 1 (Foundation), Fase 2 (AI Tender Monitoring), Fase 3 (AI Marketing & Business
Outreach), Fase 4 (Automation & Intelligent Scheduling) selesai, dan halaman Reports (laporan
lintas modul + ekspor Excel/PDF) sudah tersedia.** Sisa fitur Fase 5 di luar Reports belum dibangun.

## Yang sudah berfungsi (Fase 1)
- Skema Supabase PostgreSQL: 16 tabel, UUID, FK, unique constraint, index, trigger `updated_at`, RLS.
- Guard di DB: email berstatus `approved`/`sent` wajib punya `approved_by` dan `approved_at`.
- Backend FastAPI: auth (validasi JWT Supabase), role admin/staff, rate limiting, CORS, health check,
  `GET /api/auth/me`, `GET /api/dashboard/overview`, `GET /api/automation/status`.
- Frontend React + Vite + Tailwind: desain dashboard baru (palet dari logo, font Poppins lokal, mode gelap otomatis), login, layout responsif, Overview (kartu, grafik 7 hari, tender prioritas, status sumber, jadwal) dengan angka real dari DB.
- Docker Compose (api + frontend).

## Yang sudah berfungsi (Fase 2 — AI Tender Monitoring)
- **Sumber nyata, bukan dummy**: adapter **SPSE Nasional** (`spse.inaproc.id`, publik, terverifikasi).
  Adapter **INAPROC API Gateway** resmi (aktif otomatis begitu `INAPROC_API_KEY` diisi).
  SIRUP dinyatakan **tidak didukung** (butuh login) dan didokumentasikan di `PHASE2_PLAN.md`.
- **Koleksi**: `POST /api/tenders/collect` — keyword dari DB atau manual, ekstraksi daftar + detail + jadwal,
  simpan URL sumber, dedupe (`dedupe_hash` unik → upsert idempoten), catat kesehatan sumber & `system_logs`.
- **AI**: `POST /api/tenders/{id}/analyze` dan `/analyze-pending` (Groq/OpenAI) → kategori, skor relevansi 0–100,
  prioritas HIGH/MEDIUM/LOW, alasan, kebutuhan peralatan, peluang kerja sama. Output divalidasi sebelum disimpan;
  data mentah `tenders` tidak pernah diubah AI (analisis disimpan terpisah dengan riwayat `is_current`).
- **Frontend**: halaman **Tender Monitoring** (cari, filter, urut, paginasi), **detail tender** (data + analisis AI),
  kontrol **pencarian manual**, dan **export Excel (.xlsx)**.
- Migrasi opsional `003_phase2_indexes.sql` (indeks non-destruktif) dan `004_phase2_sources.sql` (menambah sumber SPSE, koreksi SIRUP).
- `006_phase2_keywords_id.sql` menambah **keyword berbahasa Indonesia** (judul paket SPSE berbahasa Indonesia, sedangkan seed `002` banyak frasa Inggris) — idempoten.
- `007_phase2_tender_view.sql` membuat **view `tenders_with_analysis`** yang meratakan analisis terkini (kolom `analysis_*`, satu baris per tender). Diperlukan agar listing bisa **mengurutkan berdasarkan skor relevansi** dan memfilter prioritas/kategori (relasi `tenders → tender_analysis` satu-ke-banyak, sehingga PostgREST menolak order via embed: PGRST118).

## Yang sudah berfungsi (Fase 3 — AI Marketing & Business Outreach)
- **Company Leads**: discovery berlapis — **tambah manual**, **pengumpulan dari URL situs web**
  (ambil email/telepon bisnis publik; hormati `robots.txt`; tanpa login/CAPTCHA), **impor daftar**,
  dan **pencarian kata kunci** (aktif setelah `LEAD_SEARCH_PROVIDER` + `LEAD_SEARCH_API_KEY` provider `serper`/`tavily` diisi).
  Duplikat dicegah (`normalized_name` + domain situs). Memakai kembali tabel Fase 1
  (`companies`, `company_contacts`, `company_leads`, `lead_analysis`) — **tanpa tabel baru**.
- **Kualifikasi AI**: `POST /api/leads/{id}/qualify` dan `/analyze-pending` (Groq/OpenAI) →
  skor 0–100, kategori HIGH/MEDIUM/LOW, klasifikasi industri, produk yang mungkin dibutuhkan,
  alasan, saran pendekatan. Output divalidasi; data mentah `companies` tidak pernah diubah AI.
- **Marketing Outreach**: `POST /api/outreach/generate` menulis draft email **id/en/ko** dari
  `config/company_profile.yaml` + data lead. Kelola **template** & **kampanye**. **Kirim via SMTP
  nyata** (stdlib `smtplib`) dengan **persetujuan admin wajib** sebelum kirim (ditegakkan juga
  oleh constraint DB `chk_approval_required`). Draft tetap bisa dibuat tanpa SMTP.
- **Anti-mengarang fakta**: AI hanya boleh memakai profil resmi + data DB; daftar `forbidden_claims`
  (sertifikasi, pengalaman, kapasitas, harga, spesifikasi) dilarang diklaim.
- **Frontend**: halaman **Company Leads** (daftar + panel discovery + filter/paginasi),
  **detail lead** (data, kontak, kualifikasi AI, riwayat, email terkait), **Marketing Outreach**
  (tab Pesan/Template/Kampanye), dan **detail pesan** (edit, setujui, kirim, riwayat).
- Migrasi `008_phase3_leads_view.sql` (view `leads_with_analysis`) dan `009_phase3_outreach_columns.sql`
  (kolom audit `outreach_messages.template_id`/`ai_model`).
- Panduan pengguna non-teknis: **`PHASE_3_GUIDE.md`**. Rencana & status verifikasi: **`PHASE3_PLAN.md`**.

## Yang sudah berfungsi (Fase 4 — Automation & Intelligent Scheduling)
- **Scheduler nyata**: **APScheduler** berjalan di dalam proses backend (zona `Asia/Jakarta`), dengan
  konfigurasi & status **disimpan di database** sehingga tetap ada setelah restart. Tidak ada
  eksekusi ganda: satu job aktif per automation dijaga **unique partial index** di DB; idempotency key
  mencegah duplikasi; job yang macet dibersihkan otomatis.
- **4 automation** (sesuai spesifikasi): **Tender Monitoring** (Senin 08:00 WIB), **Company Discovery**
  (Selasa 09:00), **Lead Qualification** (Selasa 10:00), **Outreach Draft Generation** (Rabu 09:00).
  Semua handler memanggil layanan Fase 2/3 yang sudah ada; **tidak ada data palsu** — bila kunci
  eksternal belum diisi, job **gagal dengan pesan jelas**, bukan "sukses" palsu.
  **Outreach hanya membuat draft; email tidak pernah dikirim otomatis.**
- **Halaman Automation Settings** (menggantikan placeholder): tab **Ringkasan** (statistik, jadwal
  berikutnya, job terakhir), **Konfigurasi** (ubah jadwal/hari/jam/zona waktu, retry, timeout, parameter
  JSON, aktif/nonaktif, jalankan sekarang), dan **Riwayat job** (filter + paginasi + modal detail:
  log, percobaan ulang, retry, cancel). Semua aksi tulis **khusus admin**.
- **Notifikasi** in-app: lonceng di topbar dengan hitungan belum dibaca, daftar, tandai dibaca /
  tandai semua. Notifikasi dibuat saat automation selesai/sebagian/gagal; opsional dikirim ke email
  admin (`AUTOMATION_NOTIFY_EMAIL=true` + `SMTP_*`).
- **API**: `GET/POST/PATCH /api/automation/configs`, `GET /api/automation/overview`,
  `GET /api/automation/jobs`, `GET /api/automation/jobs/{id}`, `POST /api/automation/jobs/run`,
  `POST /api/automation/jobs/{id}/retry`, `POST /api/automation/jobs/{id}/cancel`,
  `GET /api/automation/status`, dan `/api/notifications/*` (list, unread-count, read, read-all).
- **Keandalan & keamanan**: retry exponential backoff + batas percobaan, timeout kooperatif,
  idempotency key, lock DB, structured logging, role auth (tulis = admin), rate limiting, rahasia
  hanya lewat env.
- Migrasi `010_phase4_automation.sql` (4 tabel: `automation_configs`, `automation_jobs`,
  `automation_job_logs`, `notifications`; index, trigger `updated_at`, RLS, GRANT, seed 4 automation).
  **Wajib dijalankan** agar halaman Automation & notifikasi berfungsi.
- Panduan pengguna non-teknis: **`PHASE_4_GUIDE.md`**. Rencana & status verifikasi: **`PHASE4_PLAN.md`**.

## Yang sudah berfungsi — Halaman Reports (laporan lintas modul)
- **`GET /api/reports/summary?days=7|30|90`** — agregat tender (total, prioritas, sumber, deadline ≤7 hari,
  tren harian), leads (status CRM, high potential, konversi, tren), outreach (status, tipe email, kampanye),
  dan kinerja automation (job per tipe/status, tingkat sukses, durasi rata-rata, kegagalan terbaru).
- **Ekspor** `GET /api/reports/export.xlsx` (sheet Ringkasan + Tender/Leads/Outreach/Automation) dan
  `GET /api/reports/export.pdf` (reportlab). Tidak butuh migrasi baru — membaca tabel/view yang sudah ada.
- **Halaman Reports** (menggantikan placeholder): pemilih periode 7/30/90 hari, kartu ringkasan per modul
  dengan grafik tren 30 hari, dan tombol ekspor Excel/PDF. Tiap bagian punya status muat/kosong/galat
  sendiri; bila tabel suatu modul belum ada, bagian itu ditandai "tidak tersedia" (bukan dianggap nol).
- Batas jujur: agregasi dihitung dari maksimum **5.000 baris terbaru** per modul (PostgREST tanpa GROUP BY).

## Yang sudah berfungsi — Ganti bahasa (Indonesia ↔ 한국어)
- Pemilih bahasa di **topbar** (sebelah lonceng notifikasi): **Indonesia** atau **한국어 (Korea)**.
- Seluruh UI diterjemahkan: navigasi, login, semua halaman (Dashboard, Tender, Leads, Outreach,
  Automation, Reports), modal & dialog konfirmasi, pesan muat/kosong, label status, serta tanggal &
  durasi (locale `ko-KR` saat Korea, `id-ID` saat Indonesia). Waktu tetap zona **Asia/Jakarta**.
- Pilihan disimpan di **browser (localStorage, kunci `greeneco.lang`)** — tanpa migrasi DB, dan bertahan
  setelah refresh di browser yang sama. Default: **Indonesia**.
- Kamus terjemahan ada di `frontend/src/i18n/ko/` (satu berkas per halaman + `common.js`). Teks sumber
  Bahasa Indonesia menjadi kunci; kunci yang belum ada di kamus otomatis tampil apa adanya (aman).
- Batas jujur: pilihan bahasa bersifat **per-browser**, bukan per-akun (tidak tersinkron antar perangkat).
- Data pengguna (judul tender, nama perusahaan, isi email, dsb.) **tidak** diterjemahkan.

## Belum ada (jangan dianggap berfungsi)
Sisa fitur Fase 5 di luar halaman Reports. **Butuh kredensial agar aktif**: INAPROC API Gateway (`INAPROC_API_KEY`),
analisis AI & penulisan email (`GROQ_API_KEY`/`OPENAI_API_KEY`), pengiriman email (`SMTP_*`),
pencarian perusahaan (`LEAD_SEARCH_API_KEY`).
**Tidak didukung tanpa login**: SIRUP.
Catatan jujur: **timeout & cancel job bersifat kooperatif** — handler memeriksa status di antara
langkah, jadi job yang sedang menunggu proses eksternal berhenti pada titik pemeriksaan berikutnya,
bukan seketika.

## Setup
1. **Supabase**: buat project. Di SQL Editor jalankan berurutan `001_init.sql`, `002_seed_config.sql`,
   lalu `003_phase2_indexes.sql`, `004_phase2_sources.sql`, `005_phase2_grants.sql`,
   `006_phase2_keywords_id.sql`, `007_phase2_tender_view.sql`, `008_phase3_leads_view.sql`,
   `009_phase3_outreach_columns.sql`, dan `010_phase4_automation.sql`.
   - `003` hanya indeks (opsional, non-destruktif). `004` menambah sumber SPSE. `005` memberi **GRANT** ke role
     `authenticated`/`service_role` — **wajib** jika muncul error `permission denied for table` (42501),
     yang terjadi bila project tidak mewarisi default privileges Supabase.
   - `006` menambah keyword Indonesia (agar pencocokan paket SPSE berbahasa Indonesia bekerja). `007` membuat view
     listing + analisis (wajib untuk urut skor relevansi & filter prioritas/kategori).
   - `008` membuat view `leads_with_analysis`. `009` menambah kolom audit `outreach_messages`
     (`template_id`, `ai_model`). **Wajib** agar daftar Company Leads & Pesan tampil (tanpa ini
     keduanya mengembalikan 503). Non-destruktif & idempoten.
   - `010` membuat tabel Fase 4 (`automation_configs`, `automation_jobs`, `automation_job_logs`,
     `notifications`) + seed 4 automation. **Wajib** agar halaman Automation Settings & notifikasi
     berfungsi (tanpa ini keduanya mengembalikan 503 dengan pesan jelas). Non-destruktif & idempoten;
     tabel Fase 1 `automation_schedules` tidak diubah.
2. **Akun**: Authentication > Users > Add user. User pertama otomatis `admin`, berikutnya `staff`.
   Setelah akun tim dibuat, matikan sign-up publik (Authentication > Providers > Email > nonaktifkan "Allow new users to sign up").
3. `cp .env.example .env` lalu isi `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `VITE_*`.
   Service role key hanya untuk backend. Untuk Fase 2 isi juga `GROQ_API_KEY` (atau `OPENAI_API_KEY`);
   `INAPROC_API_KEY` hanya bila punya token API Gateway resmi.
   Untuk Fase 3: isi `SMTP_*` bila ingin mengirim email sungguhan (tanpa itu draft tetap bisa dibuat),
   dan `LEAD_SEARCH_PROVIDER` + `LEAD_SEARCH_API_KEY` (`serper`/`tavily`) bila ingin mencari perusahaan via kata kunci.
   Untuk Fase 4: scheduler menyala otomatis (`SCHEDULER_ENABLED=true`). Set `SCHEDULER_ENABLED=false`
   hanya untuk proses non-web (mis. menjalankan banyak worker). `AUTOMATION_NOTIFY_EMAIL=true`
   mengaktifkan email admin (butuh `SMTP_*`).
4. Isi `config/company_profile.yaml` dari website resmi.
5. Jalankan: `docker compose up -d --build` lalu buka `http://<server>:8080`.

### Development lokal
```
cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Keamanan deployment
Jangan buka port 8080 ke internet publik. Akses lewat Tailscale atau Cloudflare Access.
Backup: aktifkan backup harian Supabase (paket Pro) dan simpan `.env` terpisah dari repo.

## Testing
`cd backend && python -m pytest` (251 test: util teks & web, klien DB, adapter SPSE/INAPROC, koleksi/dedupe,
AI & validasi, analisis tender/lead, discovery lead, layanan outreach & mailer, router tenders/sources/leads/outreach,
**Fase 4**: registry jadwal/cron, runner job (lock/retry/cancel), handler 4 automation, scheduler, dan API automation/notifikasi,
serta **Reports**: agregasi ringkasan lintas modul + ekspor Excel/PDF).
Lihat `TESTING.md` untuk apa yang sudah dan belum teruji (terutama yang butuh kredensial/DB asli).

### Uji cepat end-to-end (smoke test)
Setelah `.env` diisi (Supabase wajib; `GROQ_API_KEY` untuk langkah AI):
```
cd backend
.\.venv\Scripts\python.exe scripts\smoke_test.py            # Windows
python scripts/smoke_test.py                                # Linux/macOS
```
Skrip memverifikasi berurutan: konfigurasi -> koneksi & skema DB -> koleksi SPSE nyata -> simpan ke `tenders` -> analisis AI.
Opsi berguna: `--dry-run` (ambil dari SPSE tanpa menulis DB), `--years 2026 --max-rows 1500`, `--analyze 5`,
`--keywords "sampah,limbah,TPST"`, `--skip-analyze`. Berhenti dengan pesan jelas (bukan error) bila kredensial belum diisi.
`.env` cukup di root repo — backend membacanya baik dijalankan dari root maupun dari `backend/`.
