# Green Eco Teknologi — Business Automation

Aplikasi **internal** untuk otomatisasi bisnis: memantau tender lingkungan, mencari calon pelanggan, menyiapkan email penawaran dengan AI, menjadwalkan pekerjaan berulang, dan melihat laporan lintas modul.

Dipakai oleh tim **admin** (pengaturan, persetujuan email, konfigurasi automation) dan **staff** (pemantauan & operasional harian).

---

## 1. Apa yang bisa dilakukan?

| Modul | Halaman | Fungsi utama |
| --- | --- | --- |
| **Dashboard** | `/` | Ringkasan angka real dari DB: grafik 7 hari, tender prioritas, status sumber, jadwal terdekat. |
| **Tender Monitoring** | `/tenders`, `/tenders/:id` | Ambil tender dari SPSE/LPSE, analisis relevansi AI (skor 0–100, prioritas, alasan), cari/filter/urutkan, ekspor Excel. |
| **Company Leads** | `/leads`, `/leads/:id` | Kumpulkan calon pelanggan (manual, dari situs web, impor, atau cari kata kunci), kualifikasi AI, lihat kontak & riwayat. |
| **Marketing Outreach** | `/outreach`, `/outreach/:id` | Kelola template & kampanye, buat draft email (id/en/ko) dari profil perusahaan, **minta persetujuan admin**, lalu kirim via SMTP. |
| **Reports** | `/reports` | Laporan tender/lead/outreach/automation untuk periode 7/30/90 hari + ekspor Excel & PDF. |
| **Automation Settings** | `/automation` | Atur jadwal 4 pekerjaan otomatis, jalankan sekarang, lihat riwayat job/log, retry atau cancel. Lonceng notifikasi di kanan atas. |

Bahasa antarmuka bisa diganti **Indonesia ↔ 한국어** lewat pemilih di topbar.

---

## 2. Cara kerja singkat

```text
  Browser (React + Vite + Tailwind)
        │ login & baca data (anon key)
        ▼
  Backend (FastAPI, Python 3.12)
        │ tulis/baca data (service role key)
        ▼
  Supabase PostgreSQL  ← migrasi SQL di folder supabase/migrations/
```

Sumber/kelayanan eksternal (semua opsional kecuali Supabase):

| Kelayanan | Dipakai untuk | Jika tidak diisi |
| --- | --- | --- |
| **SPSE/LPSE** via library `pyproc` | Mengambil daftar tender publik | Tidak ada tender baru; halaman tetap bisa dibuka |
| **INAPROC API Gateway** | Sumber tender resmi `data.inaproc.id` | Adapter ini tidak aktif; SPSE tetap jalan |
| **Groq / OpenAI** | Analisis tender & kualifikasi lead, penulisan email | Tombol analisis memberi pesan "belum dikonfigurasi" |
| **Serper / Tavily** | Pencarian calon pelanggan via kata kunci | Cara tambah manual & dari situs tetap berfungsi |
| **SMTP** | Mengirim email penawaran | Draft tetap dibuat, tapi tidak bisa dikirim |

Prinsip penting: **AI tidak mengubah data mentah** (hasil analisis disimpan terpisah + riwayat), **email tidak pernah dikirim otomatis**, dan AI dilarang mengarang klaim (sertifikat, harga, kapasitas, dll.) di luar `config/company_profile.yaml`.

---

## 3. Instalasi (cara paling mudah: Docker)

### Langkah 1 — Siapkan database Supabase

1. Buat project di Supabase.
2. Buka **SQL Editor**, jalankan file migrasi **berurutan**:

```text
supabase/migrations/001_init.sql
supabase/migrations/002_seed_config.sql
supabase/migrations/003_phase2_indexes.sql
supabase/migrations/004_phase2_sources.sql
supabase/migrations/005_phase2_grants.sql
supabase/migrations/006_phase2_keywords_id.sql
supabase/migrations/007_phase2_tender_view.sql
supabase/migrations/008_phase3_leads_view.sql
supabase/migrations/009_phase3_outreach_columns.sql
supabase/migrations/010_phase4_automation.sql
supabase/migrations/011_pyproc_source.sql
```

Catatan:

- `001` membuat tabel, constraint, trigger, dan RLS. `002` mengisi keyword & sumber awal.
- `005` **wajib** bila muncul error `permission denied for table ... (42501)`.
- `008`, `009`, `010` **wajib** agar halaman Leads, Outreach, Automation & notifikasi tidak balas `503`.
- `011` memindahkan sumber SPSE ke adapter `pyproc` (pengganti scraping manual).
- Semua migrasi aman dijalankan ulang (idempoten) dan tidak menghapus data lama.

### Langkah 2 — Buat akun

**Authentication → Users → Add user.** User pertama otomatis ber-role `admin`, berikutnya `staff`.

Setelah semua akun tim dibuat, matikan pendaftaran publik:
**Authentication → Providers → Email → nonaktifkan "Allow new users to sign up"**.

### Langkah 3 — Buat file `.env` di root repo

Belum ada `.env.example` di repo ini. Salin contoh di bawah ke file `.env`, lalu isi nilainya. `.env` sudah masuk `.gitignore` — **jangan pernah commit**.

```dotenv
# WAJIB — Supabase (Settings → API)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...              # boleh dipakai frontend
SUPABASE_SERVICE_ROLE_KEY=eyJ...      # HANYA backend, jangan masuk frontend

# WAJIB — frontend (dipakai saat build Docker)
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...

# AI (opsional, tapi dibutuhkan tombol analisis & penulisan email)
AI_PROVIDER=groq                      # groq | openai
GROQ_API_KEY=
OPENAI_API_KEY=
AI_MODEL=                             # kosong = default provider

# Sumber tender (opsional)
INAPROC_API_KEY=                      # token API Gateway resmi; kosong = tidak aktif
COLLECT_MAX_ROWS=2000
ANALYZE_MAX_BATCH=25

# Lead discovery (opsional)
LEAD_SEARCH_PROVIDER=serper           # serper | tavily | none
LEAD_SEARCH_API_KEY=

# Kirim email (opsional; draft tetap bisa dibuat tanpa ini)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_TLS=true

# Automation (opsional)
SCHEDULER_ENABLED=true                # false hanya untuk worker/test non-web
AUTOMATION_NOTIFY_EMAIL=false         # true = kirim notifikasi juga ke email admin (butuh SMTP)

# Umum
APP_ENV=production                    # development akan mengaktifkan /docs
CORS_ORIGINS=http://localhost:5173,http://<alamat-server>:8080
TIMEZONE=Asia/Jakarta
```

### Langkah 4 — Isi profil perusahaan

Edit `config/company_profile.yaml` dengan data resmi perusahaan (nama, layanan, kontak, dll.). Ini **satu-satunya sumber fakta** yang boleh dipakai AI untuk menulis email.

### Langkah 5 — Jalankan

```bash
docker compose up -d --build
```

Buka `http://<alamat-server>:8080` dan login dengan akun Supabase yang sudah dibuat.

> Port 8080 **jangan dibuka ke internet publik**. Akses lewat Tailscale atau Cloudflare Access. Jika mengubah `VITE_*`, jalankan ulang `docker compose up -d --build` karena nilai itu tertanam saat build frontend.

---

## 4. Alur pemakaian sehari-hari

### Memantau tender

1. Buka **Tender Monitoring** → tombol kumpulkan tender. Sumber yang aktif akan diambil, lalu duplikat otomatis dicegah (`dedupe_hash`).
2. Klik **Analisis** (atau **Analisis yang tertunda**) untuk mendapat skor relevansi, prioritas HIGH/MEDIUM/LOW, alasan, kebutuhan peralatan, dan peluang kerja sama.
3. Gunakan filter/urutan (termasuk urut berdasarkan skor) atau ekspor `.xlsx`.
4. Klik baris tender untuk melihat detail + riwayat analisis.

### Mencari & memilih calon pelanggan

1. Buka **Company Leads** → tambah manual, tempel URL situs perusahaan, impor daftar, atau cari kata kunci (butuh `LEAD_SEARCH_API_KEY`).
2. Klik **Kualifikasi AI** untuk skor 0–100, kategori, industri, produk yang mungkin dibutuhkan, dan saran pendekatan.
3. Detail lead menampilkan kontak, riwayat analisis, dan email terkait.

### Menyiapkan & mengirim email

1. Buka **Marketing Outreach** → buat/duplikat template jika perlu, lalu buat kampanye.
2. Generate draft (AI hanya memakai profil resmi + data lead).
3. Periksa dan edit draft → **Setujui** (khusus admin).
4. **Kirim** — pengiriman hanya berjalan bila SMTP terisi dan draft sudah disetujui. Database juga menolak email berstatus `approved`/`sent` tanpa `approved_by` + `approved_at`.

### Automation & notifikasi

Jadwal bawaan (zona `Asia/Jakarta`, bisa diubah di halaman Automation Settings):

| Pekerjaan | Jadwal default | Kebutuhan |
| --- | --- | --- |
| Tender Monitoring | Senin 08:00 WIB | SPSE/LPSE + AI untuk analisis |
| Company Discovery | Selasa 09:00 WIB | `LEAD_SEARCH_API_KEY` |
| Lead Qualification | Selasa 10:00 WIB | AI |
| Outreach Draft Generation | Rabu 09:00 WIB | AI (hanya membuat draft) |

Riwayat job bisa difilter, dibuka detail log-nya, di-retry, atau di-cancel. Lonceng di topbar menampilkan notifikasi hasil job; dengan `AUTOMATION_NOTIFY_EMAIL=true`, ringkasan juga dikirim ke email admin.

### Laporan & bahasa

- **Reports**: pilih 7/30/90 hari, lihat kartu & grafik tren per modul, lalu ekspor Excel atau PDF.
- **Pemilih bahasa** di topbar: `Indonesia` / `한국어`. Pilihan disimpan di browser (`localStorage`, kunci `greeneco.lang`), bukan per akun. Data seperti judul tender atau isi email **tidak** diterjemahkan.

---

## 5. Ringkasan API

Semua endpoint diawali `/api`. Login memakai token Supabase (Bearer). Penulisan umumnya khusus admin.

| Grup | Endpoint contoh |
| --- | --- |
| Auth & health | `GET /api/auth/me`, `GET /api/health`, `GET /api/health/db` |
| Dashboard | `GET /api/dashboard/overview` |
| Sumber & keyword | `GET/POST /api/sources`, `PATCH /api/sources/{id}`, `POST /api/sources/{id}/check`, `GET/POST /api/keywords` |
| Tender | `GET /api/tenders`, `GET /api/tenders/export`, `POST /api/tenders/collect`, `POST /api/tenders/analyze-pending`, `POST /api/tenders/{id}/analyze` |
| Lead | `GET/POST /api/leads`, `POST /api/leads/discover`, `POST /api/leads/{id}/qualify`, `POST /api/leads/analyze-pending` |
| Outreach | `GET/POST /api/outreach/templates`, `/campaigns`, `/messages`, `POST /api/outreach/generate`, `POST /api/outreach/messages/{id}/approve`, `.../send` |
| Automation | `GET/POST/PATCH /api/automation/configs`, `GET /api/automation/overview`, `GET /api/automation/jobs`, `POST /api/automation/jobs/run`, `.../retry`, `.../cancel`, `GET /api/automation/status` |
| Notifikasi | `GET /api/notifications`, `GET /api/notifications/unread-count`, `PATCH /api/notifications/{id}/read`, `POST /api/notifications/read-all` |
| Reports | `GET /api/reports/summary?days=7`, `GET /api/reports/export.xlsx`, `GET /api/reports/export.pdf` |

Dokumentasi interaktif tersedia di `/docs` saat `APP_ENV=development`.

---

## 6. Development lokal & pengujian

```bash
# Backend (port 8000)
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Frontend (port 5173)
cd frontend
npm install
npm run dev
```

Backend membaca `.env` dari root repo **atau** dari folder `backend/`, jadi satu file di root cukup.

```bash
# Semua test otomatis
cd backend && python -m pytest

# Uji alur nyata: konfigurasi → DB → ambil tender SPSE → simpan → analisis AI
python scripts/smoke_test.py --dry-run                 # tanpa menulis DB
python scripts/smoke_test.py --years 2026 --max-rows 1500 --analyze 5
python scripts/smoke_test.py --keywords "sampah,limbah,TPST" --skip-analyze
```

Test yang membutuhkan kredensial asli (Supabase, AI, API eksternal) akan dilewati dengan pesan jelas bila kuncinya kosong.

---

## 7. Deploy & keamanan

- **Docker Compose** (direkomendasikan untuk server internal): `docker compose up -d --build`. Backend tidak membuka port sendiri; hanya frontend yang diekspos di `8080`.
- **Vercel**: repo juga bisa di-deploy sebagai satu project lewat `vercel.json` (`/api/*` → backend FastAPI, lainnya → frontend Vite + fallback SPA). Isi environment variable yang sama seperti `.env`. **Catatan:** scheduler APScheduler tidak otomatis berjalan di serverless, dan file `config/company_profile.yaml` tidak ikut ter-bundle — keduanya perlu penanganan terpisah jika memakai Vercel.
- Akses dibatasi lewat Tailscale / Cloudflare Access; jangan ekspos port ke publik.
- Aktifkan backup harian Supabase dan simpan `.env` terpisah dari repository.

---

## 8. Batasan yang perlu diketahui

- Sisa fitur **Fase 5 di luar halaman Reports** belum dibangun.
- **SIRUP tidak didukung otomatis** karena butuh login; sumbernya ditandai `manual_only`.
- Fitur AI, pencarian lead, INAPROC API, dan pengiriman email baru aktif setelah kunci masing-masing diisi. Tanpa kunci, job automation **gagal dengan pesan jelas**, bukan "sukses palsu".
- Timeout dan cancel job bersifat **kooperatif**: handler memeriksa status di antara langkah, jadi proses yang sedang menunggu layanan eksternal berhenti di titik pemeriksaan berikutnya, bukan seketika.
- Agregasi Reports dihitung dari maksimal **5.000 baris terbaru per modul**.
- Pilihan bahasa bersifat per-browser, tidak tersinkron antar perangkat.

### Kalau ada masalah

| Gejala | Penyebab & solusi |
| --- | --- |
| `permission denied for table ... (42501)` | Jalankan `005_phase2_grants.sql` di SQL Editor. |
| Halaman Leads/Outreach/Automation balas `503` | Migrasi `008`, `009`, `010` belum dijalankan. |
| Tombol analisis bilang belum ada kunci | Isi `GROQ_API_KEY` atau `OPENAI_API_KEY`, lalu restart backend. |
| Draft email tidak bisa dikirim | Cek `SMTP_*` dan pastikan admin sudah menyetujui draft. |
| Tidak ada tender baru | Cek sumber aktif di halaman Sumber, koneksi SPSE/LPSE, dan keyword. Jalankan smoke test `--dry-run`. |

---

## 9. Struktur folder

```text
backend/
  app/
    routers/      # endpoint API (auth, tender, lead, outreach, automation, reports, ...)
    services/     # logika koleksi, analisis, leads, outreach, mailer
    ai/           # prompt + validasi output AI
    sources/      # adapter SPSE/LPSE (pyproc), INAPROC API, registry sumber
    discovery/    # pencarian & pengumpulan data company leads
    automation/   # scheduler, runner job, handler, notifikasi
    utils/        # parser tanggal/teks/HTML
  scripts/        # smoke_test.py
  tests/          # test otomatis
config/
  company_profile.yaml   # fakta resmi perusahaan untuk AI
frontend/
  src/pages/      # halaman sesuai menu
  src/components/ # layout, tabel, notifikasi, dll.
  src/lib/        # auth, Supabase client, i18n, format
  src/i18n/ko/    # kamus terjemahan Korea
supabase/migrations/     # 001–011, dijalankan manual di SQL Editor
docker-compose.yml       # api + frontend (akses :8080)
vercel.json              # deploy alternatif (dua service dalam satu project)
```
