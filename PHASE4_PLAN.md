# PHASE 4 — Automation & Intelligent Scheduling (Rencana Implementasi)

> Status: **selesai diimplementasikan** (lihat `PHASE_4_GUIDE.md` untuk panduan admin).
> Dokumen ini adalah audit + rencana kerja Phase 4 di atas fondasi Phase 1–3.

## 1. Hasil audit singkat

| Area | Kondisi sebelum Phase 4 |
|---|---|
| Scheduler | **Belum ada.** Hanya tabel `automation_schedules` (migrasi 001) berisi 2 baris contoh (`weekly_tender_search`, `weekly_report`) dengan `cron_expression` + `timezone`. CHECK constraint `job_type` masih terbatas 2 nilai. Tidak ada proses yang menjalankannya. |
| Router automation | Placeholder `GET /api/automation/status` (read-only). |
| Job/riwayat | Tidak ada tabel job. Tidak ada monitoring. |
| Notifikasi | Tidak ada tabel `notifications`. |
| Layanan yang bisa dipakai ulang | `services/collection.collect_all` (tender), `services/analysis.analyze_pending` (AI tender), `services/leads.discover` (company discovery), `services/lead_analysis.analyze_pending` (kualifikasi AI), `services/outreach.generate_draft` (draft email, **tanpa kirim**), `services/mailer.send_email`, `services/collection.log_event` (system_logs). |
| Auth/role | `deps.get_current_user`, `deps.require_role("admin")`, `deps.get_db`. |
| Rate limit | slowapi global `RATE_LIMIT` (120/menit). |
| Frontend | `/automation` masih `Placeholder`. Sidebar sudah punya menu "Automation Settings". |

Kesimpulan: seluruh modul bisnis Phase 2/3 sudah punya implementasi nyata dan dapat dipanggil
ulang. Phase 4 **tidak** membuat automation palsu — setiap job memanggil layanan nyata.
Jika sebuah integrasi butuh kunci eksternal (AI/`LEAD_SEARCH_API_KEY`) dan kunci tidak ada,
job **gagal dengan pesan jelas** (bukan "sukses" palsu) dan tercatat di log + notifikasi.

## 2. Keputusan arsitektur

1. **Scheduler**: APScheduler 3.x `BackgroundScheduler` (thread pool), timezone `Asia/Jakarta`.
   - Job berjalan di thread terpisah → tidak menghambat event loop FastAPI.
   - `max_instances=1`, `coalesce=True`, `misfire_grace_time` → tidak ada tumpang tindih.
   - **Persistensi**: sumber kebenaran jadwal = tabel `automation_configs` (DB). Saat startup
     scheduler memuat ulang seluruh konfigurasi → jadwal bertahan setelah restart.
   - **Anti-ganda antar-instance (distributed lock)**: unique partial index
     `automation_jobs(automation_config_id) where status in ('queued','running')`. Instance kedua
     yang mencoba membuat job untuk config yang sama akan gagal 409 → dilewati. Ditambah
     idempotency key per slot jadwal.
2. **Tabel baru (migrasi 010)**: `automation_configs`, `automation_jobs`, `automation_job_logs`,
   `notifications`. Tabel Phase 1 `automation_schedules` **tidak diubah/dihapus** (kompatibilitas);
   dashboard membaca `automation_configs` dengan fallback ke `automation_schedules`.
3. **Modul automation** = 4 job:
   - `tender_monitoring` (Senin 08:00 WIB) → `collection.collect_all` + `analysis.analyze_pending` +
     peringatan deadline.
   - `company_discovery` (Selasa 09:00 WIB) → `leads.discover`.
   - `lead_qualification` (Selasa 10:00 WIB) → `lead_analysis.analyze_pending`.
   - `outreach_draft_generation` (Rabu 09:00 WIB) → `outreach.generate_draft` (**draft saja, tanpa kirim**).
4. **Frekuensi**: `daily | weekly | monthly | custom` disimpan di `schedule_type` + `schedule_config`
   (JSON), lalu diturunkan menjadi `cron_expression` (format crontab standar: `0`=Minggu, `1`=Senin)
   untuk tampilan/kompatibilitas. Konversi ke APScheduler (0=Senin) dilakukan eksplisit agar tidak
   ada pergeseran hari.
5. **Reliability**: retry exponential backoff + `retry_max_attempts`, `timeout_seconds` (kooperatif),
   pembatalan kooperatif (`cancel_requested`), reaper job "menggantung" saat startup,
   structured logging ke `automation_job_logs` + `system_logs`.
6. **Keamanan**: semua endpoint butuh auth; tulis konfigurasi & eksekusi manual = role `admin`.
   Rate limit tambahan pada endpoint eksekusi. RLS: SELECT untuk user aktif (notifikasi hanya milik
   sendiri / broadcast admin); semua tulis lewat backend (service role).

## 3. Migrasi

- **`supabase/migrations/010_phase4_automation.sql`** (baru, idempoten):
  - `automation_configs`, `automation_jobs`, `automation_job_logs`, `notifications`
  - index unik aktif-job + idempotency, index pencarian
  - trigger `updated_at`, RLS, GRANT, seed 4 automation default, `notify pgrst`.

## 4. Backend

File baru:
- `backend/app/automation/__init__.py`
- `backend/app/automation/registry.py` — metadata tipe, konversi jadwal→cron→trigger, deskripsi ID.
- `backend/app/automation/notifications.py` — pembuatan notifikasi + dedupe + opsi email admin.
- `backend/app/automation/runner.py` — siklus hidup job (buat, jalankan, progress, retry, cancel).
- `backend/app/automation/handlers.py` — 4 handler yang memanggil layanan Phase 2/3.
- `backend/app/automation/scheduler.py` — manajer APScheduler (singleton).
- `backend/app/routers/notifications.py` — endpoint notifikasi.

File dimodifikasi:
- `backend/app/routers/automation.py` — endpoint configs/jobs/overview/logs/run/retry/cancel (+ `/status` lama).
- `backend/app/routers/dashboard.py` — baca `automation_configs` (fallback ke `automation_schedules`).
- `backend/app/main.py` — lifespan start/stop scheduler + registrasi router notifikasi.
- `backend/app/config.py` — setting Phase 4.
- `backend/requirements.txt` — `apscheduler>=3.10,<4`.

## 5. Frontend

- `frontend/src/pages/Automation.jsx` (menggantikan Placeholder) — tab Ringkasan / Konfigurasi /
  Riwayat Job + panel detail job + dialog edit jadwal + aksi Run Now / Enable / Disable / Retry / Cancel.
- `frontend/src/components/Notifications.jsx` — lonceng notifikasi di topbar (unread count, tandai dibaca).
- `frontend/src/App.jsx`, `components/Layout.jsx`, `lib/format.js`, `pages/Overview.jsx`, `index.css`.

## 6. Testing

- `backend/tests/test_phase4_registry.py` — konversi jadwal/cron, timezone.
- `backend/tests/test_phase4_runner.py` — siklus hidup job, duplikat, retry, cancel, timeout.
- `backend/tests/test_phase4_api.py` — endpoint, auth/role, notifikasi.
- `backend/tests/test_phase4_scheduler.py` — init/load/sync scheduler dengan DB palsu.
- Mock Tavily/Groq/SMTP; tidak ada email sungguhan.
- `npm run build` frontend.

## 7. Yang butuh konfigurasi eksternal (jujur)

- `company_discovery` butuh `LEAD_SEARCH_API_KEY` (Tavily/Serper).
- `lead_qualification` & `outreach_draft_generation` butuh kunci AI (`GROQ_API_KEY`/`OPENAI_API_KEY`).
- `tender_monitoring` memakai sumber publik (SPSE) tanpa kunci; sumber `inaproc` butuh `INAPROC_API_KEY`.
- Notifikasi email admin butuh SMTP (`SMTP_HOST`, `SMTP_FROM`) dan `AUTOMATION_NOTIFY_EMAIL=true`.
- **Outreach tidak pernah dikirim otomatis** — hanya draft, menunggu approval admin.

## 8. Status implementasi (selesai 17 Nov 2026)

**Backend**: selesai & teruji. `automation/` (registry, errors, notifications, runner, handlers,
scheduler), `routers/automation.py` (configs/jobs/overview/logs/run/retry/cancel + `/status`),
`routers/notifications.py`, `ratelimit.py`, `db.py` (`is_conflict_error`, `is_missing_table_error`),
`main.py` (lifespan scheduler), `dashboard.py` (overview baca configs + fallback), `config.py`.

**Migrasi**: `supabase/migrations/010_phase4_automation.sql` (4 tabel + index + trigger + RLS +
GRANT + seed 4 automation). **Belum dijalankan di Supabase asli** — wajib dijalankan agar halaman
Automation & notifikasi berfungsi. Sampai itu dijalankan, endpoint mengembalikan **503 dengan pesan
ramah** ("Tabel Fase 4 belum ada. Jalankan migrasi 010…").

**Frontend**: selesai & `npm run build` lulus. `pages/Automation.jsx` (tab Ringkasan/Konfigurasi/
Riwayat job, modal detail job + editor jadwal, aksi admin dengan dialog konfirmasi),
`components/Notifications.jsx` (lonceng + badge belum dibaca), `components/Modal.jsx`
(`Modal` + `ConfirmDialog`), `components/Icon.jsx`, `lib/format.js`, `App.jsx`, `Layout.jsx`,
`pages/Overview.jsx` (status Fase 4 + `next_run_at`), `index.css`.

**Test**: `242 passed` (`tests/test_phase4_registry.py`, `test_phase4_runner.py`,
`test_phase4_handlers.py`, `test_phase4_scheduler.py`, `test_phase4_api.py`, plus `test_db_client.py`).
DB palsu `AutomationDB` (filter PostgREST termasuk `or`/`and`, konflik unik). Tidak ada panggilan
Tavily/Groq/SMTP nyata.

**Dokumentasi**: `PHASE_4_GUIDE.md` (panduan pengguna), `README.md`, `TESTING.md`, `.env.example`
(variabel Fase 4).

**Belum diuji live (jujur)**: scheduler & job nyata (menunggu migrasi 010), INAPROC
(`INAPROC_API_KEY`), kirim email SMTP, tampilan browser.
