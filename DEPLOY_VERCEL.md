# Deploy ke Vercel — satu project, dua service

Repo ini di-deploy sebagai **satu project Vercel** berisi dua *service*:

- **backend** — FastAPI (`backend/`, entrypoint `app.main:app`)
- **frontend** — React + Vite SPA (`frontend/`)

Konfigurasinya ada di [`vercel.json`](vercel.json) di root repo. Ini memakai fitur
[Vercel Services](https://vercel.com/docs/services) (Beta di semua paket) — dua framework
berbeda dalam satu deployment, satu domain.

---

## Cara kerja routing

| Request        | Service    | Yang diterima service                       |
| -------------- | ---------- | ------------------------------------------- |
| `/api/...`     | `backend`  | path asli (prefix `/api/` **dipertahankan**) |
| selain itu     | `frontend` | path asli, lalu fallback SPA ke `/index.html` |

- Backend mendefinisikan route-nya dengan prefix `/api/...` (mis. `GET /api/health`), jadi
  **tidak ada perubahan path** yang diperlukan.
- Frontend memanggil API lewat path **relatif** (`/api/...`), sehingga di produksi
  request-nya **same-origin** — CORS praktis tidak terpakai.
- Rewrite internal `/(.*)` → `/index.html` di service frontend membuat **deep link SPA**
  (mis. `/tenders/<id>`, `/reports`) tidak 404 saat halaman di-refresh.

> Catatan: `vercel.json` ini mengabaikan `backend/Dockerfile`, `frontend/Dockerfile`, dan
> `frontend/nginx.conf`. Keduanya tetap dipakai oleh `docker-compose.yml` untuk deploy
> self-hosted (VPS/Tailscale), bukan oleh Vercel.

---

## Langkah deploy

### Lewat dashboard (import dari Git)

1. Vercel → **Add New… → Project** → import repo `amanda-thi/get-ai`.
2. **Root Directory**: biarkan **kosong** (root repo). Jangan diarahkan ke `frontend/` atau
   `backend/` — `vercel.json` yang mengatur kedua service.
3. Buka **Environment Variables** dan isi variabel di tabel bawah (minimal bagian **Wajib**),
   untuk **Production** dan **Preview**.
4. **Deploy**.

### Lewat Vercel CLI

```bash
npm i -g vercel
vercel link                 # hubungkan folder ini ke project Vercel
vercel env add SUPABASE_URL # ulangi untuk variabel lain (atau lewat dashboard)
vercel --prod
```

### Development lokal (opsional)

```bash
npm i -g vercel
vercel dev        # menjalankan kedua service sekaligus, seperti di produksi
vercel dev -L     # tanpa login ke Vercel Cloud
```

Untuk pengembangan sehari-hari, cara lama tetap jalan: `uvicorn` di `backend/` + `vite` di
`frontend/` (Vite mem-proxy `/api` ke `localhost:8000`, lihat `frontend/vite.config.js`).

---

## Environment Variables

### Backend (runtime)

| Variabel                     | Wajib   | Keterangan                                                                 |
| ---------------------------- | ------- | -------------------------------------------------------------------------- |
| `SUPABASE_URL`               | **Ya**  | URL project Supabase.                                                      |
| `SUPABASE_SERVICE_ROLE_KEY`  | **Ya**  | Kunci rahasia backend. **Jangan pernah** ditaruh di frontend.              |
| `APP_ENV`                    | saran   | Set `production` (mematikan `/docs` & `/openapi.json`).                    |
| `TIMEZONE`                   | saran   | `Asia/Jakarta`.                                                            |
| `SUPABASE_ANON_KEY`          | saran   | Untuk validasi JWT user. Kosong → otomatis memakai service role key.       |
| `CORS_ORIGINS`               | saran   | Domain Vercel produksi. Tidak wajib karena same-origin.                    |
| `GROQ_API_KEY`               | fitur   | Analisis AI tender/lead & generate draft (provider default `groq`).        |
| `AI_PROVIDER`                | fitur   | `groq` (default) atau `openai`.                                            |
| `OPENAI_API_KEY`             | fitur   | Hanya bila `AI_PROVIDER=openai`.                                           |
| `AI_MODEL`                   | fitur   | Override model AI (kosong = default per provider).                         |
| `INAPROC_API_KEY`            | fitur   | Sumber tender INAPROC API Gateway (opsional; SPSE jalan tanpa kunci).      |
| `LEAD_SEARCH_PROVIDER`       | fitur   | `tavily` / `serper` / `none` untuk pencarian lead berbasis kata kunci.      |
| `LEAD_SEARCH_API_KEY`        | fitur   | Kunci provider pencarian lead.                                             |
| `SMTP_HOST` … `SMTP_FROM`    | fitur   | Pengiriman email outreach (tetap **wajib approval admin**).                |
| `SMTP_USE_TLS`, `SMTP_PORT`  | fitur   | Default `true` / `587`.                                                    |
| `AUTOMATION_NOTIFY_EMAIL`    | fitur   | `true` = notifikasi hasil automation juga dikirim ke email admin.          |
| `SCHEDULER_ENABLED`          | saran   | Set **`false`** di Vercel (lihat batasan di bawah).                        |
| `COMPANY_PROFILE_PATH`       | saran   | Lihat batasan "Profil perusahaan" di bawah.                                |

Variabel lain (`COLLECT_MAX_ROWS`, `ANALYZE_MAX_BATCH`, `HTTP_TIMEOUT`, `RATE_LIMIT`,
`AUTOMATION_*`, dll.) punya default aman — lihat `backend/app/config.py`.

### Frontend (build-time)

Vite hanya mengekspos variabel ber-prefix `VITE_`. Keduanya dibutuhkan **saat build**:

| Variabel                 | Wajib  | Keterangan                                        |
| ------------------------ | ------ | ------------------------------------------------- |
| `VITE_SUPABASE_URL`      | **Ya** | Sama dengan `SUPABASE_URL` backend.               |
| `VITE_SUPABASE_ANON_KEY` | **Ya** | Kunci **anon/publishable** (bukan service role!). |

> Setelah mengubah variabel `VITE_*`, lakukan **redeploy** — nilainya dibekukan ke bundle JS
> saat build, bukan dibaca saat runtime. Bila kosong saat build, build tetap **sukses** tetapi
> aplikasi menampilkan pesan konfigurasi dan login tidak bisa dipakai (`frontend/src/lib/supabase.js`).

---

## Batasan & catatan penting (jujur)

1. **Scheduler automation tidak berjalan otomatis di serverless.**
   `backend` menyalakan **APScheduler** di dalam proses (lifespan). Di Vercel, instance
   dibuat/dimatikan sesuai trafik dan bisa lebih dari satu, sehingga job terjadwal tidak
   dapat diandalkan (bisa tidak jalan, atau jalan di instance acak).
   **Rekomendasi:** set `SCHEDULER_ENABLED=false` di Vercel. Tombol **"Jalankan sekarang"**
   di halaman Automation **tetap berfungsi** — saat scheduler dimatikan, job dijalankan
   lewat thread latar (`scheduler.submit_job`). Anti-ganda tetap dijaga unique index di DB.
   Untuk automation **terjadwal** yang andal, jalankan backend di host long-running
   (`docker-compose.yml`) **atau** tambahkan Vercel Cron yang memanggil endpoint khusus
   (belum ada di kode ini; butuh endpoint + verifikasi `CRON_SECRET`).

2. **Profil perusahaan (`config/company_profile.yaml`) tidak ikut ke bundle backend.**
   Service root backend adalah `backend/`, sehingga file di root repo (`config/`) tidak
   disertakan. Akibatnya `load_profile()` mengembalikan `{}` dan AI outreach/lead berjalan
   **tanpa fakta perusahaan** (kualitas menurun; AI tetap dilarang mengarang).
   **Solusi:** salin file itu ke dalam service backend dan arahkan env ke sana:
   ```bash
   mkdir -p backend/config
   cp config/company_profile.yaml backend/config/company_profile.yaml
   ```
   lalu set `COMPANY_PROFILE_PATH=config/company_profile.yaml` (path relatif terhadap root
   service = `backend/`). Jaga agar salinan tetap sinkron bila profil diperbarui.

3. **Durasi maksimum function 300 detik** (`maxDuration: 300` di `vercel.json`; 300s adalah
   batas paket Hobby, dan default semua paket). Koleksi tender / analisis AI / discovery
   yang besar bisa melewatinya → `504 FUNCTION_INVOCATION_TIMEOUT`. Jalankan per-batch
   (tombol analyze-pending, limit kecil) atau naikkan batas di paket Pro (hingga 800s).

4. **State scheduler & rate limit bersifat per-instance.** APScheduler (in-memory) dan
   `slowapi` tidak dibagi antar instance function. Ini konsisten dengan batasan (1).

5. **Batas body request/response 4.5 MB** (respons non-stream). Ekspor Excel/PDF yang sangat
   besar bisa kena limit; agregasi Reports sudah dibatasi ≤ 5000 baris per modul.

6. **Migrasi database dijalankan manual.** File `supabase/migrations/*.sql` harus dijalankan
   di Supabase SQL Editor (mis. `010_phase4_automation.sql`). Vercel tidak menjalankannya.

7. **Filesystem ephemeral & read-only.** Jangan menulis state ke disk; semua state ada di
   Supabase.

---

## Verifikasi pasca-deploy

1. `GET https://<domain>/api/health` → `200` (backend hidup).
2. Buka `https://<domain>/` → halaman login tampil, ganti bahasa ID/한국어 berfungsi.
3. Login admin → Overview menampilkan angka dari DB.
4. Buka `/reports` → ringkasan + ekspor Excel/PDF berjalan.
5. Buka `/automation` → tab konfigurasi & riwayat job tampil; coba **Jalankan sekarang**
   (butuh `GROQ_API_KEY` untuk hasil AI).
6. Deep link: refresh `https://<domain>/reports` langsung → tidak 404 (fallback SPA jalan).

Jika service backend gagal terdeteksi, pastikan `entrypoint` tetap `app.main:app` (relatif
terhadap `backend/`) — struktur ini sama dengan contoh resmi Vercel
["How to deploy a Python backend with Vercel Services"](https://vercel.com/kb/guide/python-backend-on-vercel).
