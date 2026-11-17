# Status pengujian

Diperbarui untuk Fase 4 + halaman Reports. Prinsip: **yang tidak diuji dengan kredensial/DB asli tidak diklaim berfungsi.**

## Teruji otomatis (`cd backend && python -m pytest` — 251 test)
| Area | Status | Cara |
|---|---|---|
| Util teks: strip HTML, normalisasi, keyword, parse Rupiah, parse tanggal Indonesia + ISO, dedupe hash | LULUS | `tests/test_text_utils.py` |
| Util web: normalisasi URL, domain, robots.txt, ekstrak email/telepon/judul/deskripsi, tautan kontak | LULUS | `tests/test_web_utils.py` |
| Klien DB: count, get_user, insert/upsert, update, delete | LULUS | `tests/test_db_client.py` (MockTransport) |
| Adapter SPSE Nasional: bootstrap token, parse baris DataTables, detail, jadwal, keyword filter, health check | LULUS | `tests/test_sources_spse.py` (MockTransport + fixture bentuk asli) |
| Adapter INAPROC API: guard tanpa key, mapping, paginasi cursor, 401 | LULUS | `tests/test_sources_inaproc.py` (mock sesuai skema terdokumentasi) |
| Koleksi & dedupe: upsert `on_conflict=dedupe_hash`, `first_seen_at` tidak tertimpa, kesehatan sumber, `system_logs`, sumber tak didukung → `manual_only` | LULUS | `tests/test_collection.py` |
| AI tender: klien Groq/OpenAI (mock), validasi output, layanan analisis | LULUS | `tests/test_ai.py` |
| Analisis tender: nonaktifkan `is_current` lama lalu simpan baru, pending, henti saat key kosong | LULUS | `tests/test_analysis.py` |
| Router tender: filter/param (murni), listing, detail, export xlsx, collect, analyze tanpa key → 503 | LULUS | `tests/test_tenders_api.py` |
| Router sumber/keyword: daftar, health check, kontrol akses admin, validasi bahasa | LULUS | `tests/test_sources_api.py` |
| **Discovery lead**: website (ekstrak kontak + `guess_name`), pencarian (Serper, guard tanpa kunci, 401/429) | LULUS | `tests/test_lead_discovery.py` |
| **AI lead**: prompt/validasi kualifikasi, guard key kosong, error validasi | LULUS | `tests/test_lead_ai.py` |
| **Layanan lead**: normalisasi nama, deteksi duplikat, simpan perusahaan+kontak, `_ensure_lead`, `domain_matches` | LULUS | `tests/test_leads_service.py` |
| **Layanan outreach**: `create_message`, `update_message`, `set_status`, `approve_message`, `send_message` (sukses/gagal), `generate_draft`, log | LULUS | `tests/test_outreach_service.py` |
| **Mailer**: guard SMTP belum dikonfigurasi, kirim via SMTP tiruan (login + STARTTLS) | LULUS | `tests/test_outreach_service.py` |
| **Router leads**: filter (murni), listing, detail, discovery (bad input → error rapi), kualifikasi, kontak | LULUS | `tests/test_leads_api.py` |
| **Router outreach**: filter (murni), config, template admin-only, approve admin-only, kirim tanpa SMTP → 502, kirim belum disetujui → 400 | LULUS | `tests/test_outreach_api.py` |
| Auth/role/overview (Fase 1) | LULUS | `tests/test_api.py` |
| **Fase 4 — registry jadwal**: konversi cron (mingguan 0=Senin → crontab 0=Minggu), trigger APScheduler, `next_run_at`, `describe_schedule`, validasi jadwal | LULUS | `tests/test_phase4_registry.py` |
| **Fase 4 — runner job**: `create_job`/`run_job`, lock job aktif (konflik → `None`), idempotency, retry + exponential backoff, `max_attempts`, cancel kooperatif, timeout kooperatif, `reap_stale_jobs`, `list_enabled_configs` (hanya `is_enabled=true`) | LULUS | `tests/test_phase4_runner.py` (DB tiruan `AutomationDB`) |
| **Fase 4 — handler 4 automation**: memanggil layanan Fase 2/3; tanpa kunci AI/pencarian → `JobError` (gagal jujur, bukan sukses palsu); outreach **hanya draft, tidak kirim email** | LULUS | `tests/test_phase4_handlers.py` |
| **Fase 4 — scheduler**: mulai/berhenti, registrasi job terjadwal, `submit_job`, `misfire_grace`, muat ulang config dari DB | LULUS | `tests/test_phase4_scheduler.py` |
| **Fase 4 — API automation/notifikasi**: configs/jobs/overview/detail/run/retry/cancel (tulis admin-only), filter & paginasi, visibilitas notifikasi (admin = miliknya + broadcast; staf = miliknya), tandai dibaca/read-all, pesan ramah saat tabel belum ada | LULUS | `tests/test_phase4_api.py` |
| **Reports — API**: agregasi ringkasan lintas modul (tender/leads/outreach/automation), tren harian, durasi job dari timestamp, bagian ditandai `available:false` bila tabelnya belum ada (bukan dianggap nol), ekspor `.xlsx` (sheet Ringkasan + Tender/Leads/Outreach/Automation) & `.pdf` valid, butuh autentikasi | LULUS | `tests/test_reports_api.py` (DB tiruan `ReportDB`) |
| Frontend production build | LULUS | `npm run build` |
| Smoke test Fase 2 (orkestrasi SPSE→DB→AI) | LULUS (jalur pesan) | `backend/scripts/smoke_test.py` — berhenti rapi bila kredensial belum diisi |

## Uji end-to-end Fase 3 terhadap layanan asli (dijalankan 17 Nov 2026)
Diverifikasi dengan login admin nyata + backend berjalan + Supabase asli:

| Langkah | Hasil |
|---|---|
| Login admin (Supabase Auth) | LULUS — 200 |
| `GET /api/outreach/config` | LULUS — 200 `{smtp_configured:false, ai_configured:true, email_types:[…], languages:[id,en,ko]}` |
| `GET /api/outreach/templates`, `/campaigns` | LULUS — 200 (kosong) |
| `POST /api/leads/discover` (input salah) | LULUS — 200, error tercatat, **tidak ada data ditulis** |
| `POST /api/leads/discover` **dari situs nyata** (`https://greenecoteknologi.com`) | LULUS — 1 perusahaan dibuat, **3 kontak publik** diekstrak (1 email + 2 telepon) |
| `GET /api/leads/{id}` (detail) | LULUS — data perusahaan + kontak + status lead `new` |
| `POST /api/leads/{id}/qualify` (AI Groq) | LULUS — skor 15 / LOW, alasan relevan; status lead otomatis → `qualified` |
| `DELETE /api/leads/{id}` (bersih-bersih) | LULUS — 200 `{ok:true}` (data uji dihapus, tidak ada sisa) |
| `GET /api/leads`, `GET /api/outreach/messages` | **LULUS** (200) | Setelah migrasi `009` dijalankan, daftar Pesan tampil (tidak lagi 503) |

## Uji end-to-end Fase 4 terhadap layanan asli (dijalankan 17 Nov 2026)
Diverifikasi dengan login admin nyata + backend berjalan + Supabase asli, **setelah migrasi `010` diterapkan**:

| Langkah | Hasil |
|---|---|
| `GET /api/health` | LULUS — 200 `{"status":"ok"}` |
| `GET /api/automation/configs` | LULUS — 200, 4 konfigurasi (Tender Monitoring, Company Discovery, Lead Qualification, Outreach Draft) |
| `GET /api/automation/status` / `overview` | LULUS — 200, scheduler memuat 4 job, `next_run_at` terisi (mis. `2026-11-24T03:00:00Z` = Sel 10:00 WIB) |
| `POST /api/automation/jobs/run` (Lead Qualification, manual) | LULUS — job `running → partially_completed` (8 lead ter-kualifikasi, 1 gagal), 33 detik, log tersimpan |
| `GET /api/automation/jobs/{id}` | LULUS — status, `total_processed`/`success_count`/`failed_count`, log per langkah |
| `POST /api/automation/jobs/run` (duplikat saat job aktif) | LULUS — **409** "Job untuk automation ini sedang berjalan" (lock aktif ganda) |
| `POST /api/automation/jobs/{id}/cancel` | LULUS — 200 `{immediate:false}` → status berakhir `cancelled` (cancel kooperatif) |
| `automation_configs.last_status`/`last_run_at` ter-update | LULUS |
| Notifikasi otomatis (`automation_partial`, `lead_high_priority`) | LULUS — 2 notifikasi belum dibaca, tautan ke `/automation?job=…` & `/leads` |

## Uji end-to-end halaman Reports terhadap data asli (dijalankan 17 Nov 2026)
| Langkah | Hasil |
|---|---|
| `GET /api/reports/summary?days=30` | LULUS — 200; tender total 59 / teranalisis 24 / belum 35, prioritas MEDIUM 2 & LOW 22, sumber SPSE Nasional 59; leads 9 (high potential 6, qualified 8); outreach 0; automation 2 job, durasi rata-rata 20,5 dtk; tren tender menunjukkan 59 pada 2026-11-16 |
| `GET /api/reports/export.xlsx?days=30` | LULUS — 200 `application/vnd…sheet`, magic `PK`; sheet Ringkasan (79 baris), Tender (60), Leads (10), Automation (3) |
| `GET /api/reports/export.pdf?days=30` | LULUS — 200 `application/pdf`, magic `%PDF`, berkas valid (reportlab) |
| Tanpa token | 401 (sudah diuji otomatis) |

## BELUM diuji (butuh kredensial / layanan asli)
| Area | Status | Catatan |
|---|---|---|
| SQL migration di Supabase asli (001–010) | **LULUS** | 001–010 sudah diterapkan. Semua non-destruktif; 005 (GRANT) wajib bila muncul `permission denied` (42501) |
| **Scheduler & job automation live** | **LULUS** | Diverifikasi live: 4 job terjadwal, eksekusi manual, lock duplikat (409), retry/cancel, notifikasi |
| Listing lead & pesan setelah migrasi 008/009 | **LULUS** | `GET /api/leads` → 200; `GET /api/outreach/messages` → 200 |
| **Kirim email via SMTP nyata** | **BELUM DIUJI** | Butuh `SMTP_*`. Tanpa itu `send` → 502 (sudah diuji). Draft & persetujuan sudah diuji |
| **Pencarian perusahaan via kata kunci** | **LULUS (live, Tavily)** | Adapter `serper` & `tavily`; diuji live via `POST /api/leads/discover` (3 hasil, 0 gagal) |
| Analisis AI live (tender & lead) | LULUS untuk lead | Butuh `GROQ_API_KEY`/`OPENAI_API_KEY` (di lingkungan ini terisi) |
| INAPROC API Gateway live | **BELUM DIUJI** | Butuh `INAPROC_API_KEY` (token Data Integrator) |
| Docker Compose | BELUM DIUJI | Docker tidak tersedia di lingkungan pengembangan |

## Sumber discovery: didukung vs tidak
- **Tambah manual / impor daftar**: didukung, tanpa kredensial.
- **Pengumpulan dari URL situs web**: didukung; menghormati `robots.txt`, tanpa login/CAPTCHA.
- **Pencarian kata kunci**: adapter `serper` & `tavily` siap, aktif setelah `LEAD_SEARCH_PROVIDER` + `LEAD_SEARCH_API_KEY` diisi.
  Tidak ada sumber daftar-perusahaan publik & legal yang bisa di-scrape bebas → tidak dibuat.
- **Tidak didukung**: sumber yang butuh login/CAPTCHA/paywall, atau `robots.txt` melarang.

## Sumber tender (Fase 2): didukung vs tidak
- **SPSE Nasional** (`spse.inaproc.id`): didukung, publik (`robots.txt: Allow: /`), tanpa login/CAPTCHA.
- **INAPROC API Gateway** (`data.inaproc.id`): adapter siap, aktif setelah `INAPROC_API_KEY` diisi.
- **SIRUP** (`sirup.inaproc.id`): **tidak didukung** — semua `/sirup/*` mengarah ke login.
- Domain LPSE per-instansi / CKAN LKPP: ditolak (DNS/TLS gagal; `robots.txt` melarang `/api/`). Lihat `PHASE2_PLAN.md` §2.4.

## Catatan tampilan
Build frontend lulus. Uji live Fase 3 memakai API nyata; tampilan visual sebaiknya dicek di browser
(mode terang, mode gelap, lebar HP) pada halaman Company Leads, detail lead, Marketing Outreach, dan
detail pesan. Semua halaman memakai angka real dari DB (kosong = tampil ajakan, bukan data contoh).

Fase 4: halaman **Automation Settings** (tab Ringkasan/Konfigurasi/Riwayat job, modal detail job &
editor jadwal) dan **lonceng notifikasi** di topbar sebaiknya dicek di browser pada lebar desktop &
tablet.

Halaman **Reports** sebaiknya dicek di browser (desktop & tablet): pemilih periode 7/30/90 hari,
kartu ringkasan per modul, grafik tren 30 hari, serta tombol **Ekspor Excel** dan **Ekspor PDF**.
Setiap bagian punya status muat/kosong/galat sendiri; bila tabel suatu modul belum ada, bagian itu
ditandai "tidak tersedia" — bukan ditampilkan sebagai nol.

**Ganti bahasa (Indonesia ↔ 한국어)** sebaiknya dicek di browser: ubah bahasa dari pemilih di topbar,
lalu pastikan seluruh halaman (nav, Dashboard, Tender, Leads, Outreach, Automation, Reports), modal,
label status, dan tanggal/durasi ikut berubah, dan pilihan tetap tersimpan setelah refresh
(localStorage `greeneco.lang`). Data pengguna (judul tender, nama perusahaan, isi email) tidak boleh ikut
diterjemahkan.
