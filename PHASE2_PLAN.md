# Fase 2 — AI Environmental Tender Monitoring

Rencana teknis + status verifikasi sumber. Ditulis setelah meninjau seluruh kode Fase 1
dan menguji akses data sumber secara langsung (bukan asumsi).

> Prinsip: **tidak ada data dummy di produksi**, **tidak mengklaim integrasi yang belum diuji**,
> **tidak melewati CAPTCHA / akses terbatas**, desain & branding dashboard Fase 1 dipertahankan.

---

## 1. Ringkasan hasil inspeksi kode Fase 1

| Bagian | Kondisi |
|---|---|
| DB | `supabase/migrations/001_init.sql` — 16 tabel, `tenders`, `tender_analysis`, `tender_sources`, `tender_keywords`, `system_logs`, RLS SELECT-only untuk authenticated, tulis hanya via service role. `002_seed_config.sql` — 31 keyword + 2 sumber (SIRUP, INAPROC) status `untested`. |
| Backend | FastAPI. `app/db.py` = klien tipis Supabase (hanya `select` + `count`). `app/deps.py` = auth JWT + role. Router: `health`, `auth`, `dashboard`, `automation`. |
| Frontend | React 19 + Vite + Tailwind v4. `Overview.jsx` sudah memakai angka DB nyata. Halaman lain = `Placeholder.jsx`. CSS desain ada di `index.css` (variabel warna logo, dark mode otomatis, kelas `.card/.chip/.btn/.field` dst). |
| Test | 14 test lulus (`FakeDB` + `httpx.MockTransport`). |

**Celah yang harus ditutup Fase 2**
- `db.py` belum bisa tulis (insert/update/upsert) → dibutuhkan untuk menyimpan tender & analisis.
- Belum ada adapter sumber, AI, koleksi, dedupe.
- `/tenders` masih placeholder.

**Bug/kualitas yang ditemukan di Fase 1**
- `frontend/package.json` tidak punya pustaka Excel; export akan dibuat di backend.
- `db.count()` memakai `Range: 0-0` + `Prefer: count=exact` — benar, dipertahankan.
- Tidak ada indeks untuk urutan `announced_at`/`first_seen_at` (ditambah di migrasi opsional).

---

## 2. Riset & verifikasi sumber (diuji 16 Nov 2026)

### 2.1 INAPROC API Gateway — **official, perlu kredensial**
- Dokumentasi: `https://data.inaproc.id/docs`. Base URL `https://data.inaproc.id/api`.
- Auth: `Authorization: Bearer <JWT>` atau `X-API-Key`. Endpoint RUP: `GET /api/v1/rup/rencana/penyedia?limit&cursor&start_date&end_date`.
- Pendaftaran: role **Data Integrator**, butuh surat permohonan instansi → **tidak bisa langsung dipakai**.
- **Keputusan:** bangun adapter resmi (`inaproc_api`) yang aktif otomatis begitu `INAPROC_API_KEY` diisi.
  Tanpa key → `SourceError("belum dikonfigurasi")`, sumber tetap `untested`. Diuji dengan mock sesuai skema terdokumentasi.

### 2.2 SIRUP LKPP — **perlu login**
- `sirup.lkpp.go.id` sudah tidak resolve (migrasi). SIRUP sekarang di `https://sirup.inaproc.id`.
- Semua path `/sirup/*` redirect ke `RUP - Form Login`. Tidak ada endpoint RUP publik tanpa login.
- **Keputusan:** **TIDAK didukung** untuk Fase 2. Didokumentasikan sebagai `manual_only`/login-required.

### 2.3 SPSE Nasional (`spse.inaproc.id`) — **publik, terverifikasi, JADI SUMBER PERTAMA**
- Halaman publik "CARI PAKET": `https://spse.inaproc.id/nasional/lelang`. `robots.txt`: `User-agent: * Allow: /`.
- Daftar: `POST /nasional/dt/lelang?tahun=YYYY` (DataTables server-side). Perlu cookie sesi (`SPSE_SESSION`)
  + `authenticityToken` yang memang dirender di halaman publik (bukan CAPTCHA, bukan login).
  Body: `authenticityToken=…&draw=1&start=N&length=M&search[value]=`.
- Terbukti: `tahun=2026` → 1.324 baris nyata (1.049 selesai, 105 gagal, 15+ sedang berjalan, dst). `length=1000` diterima.
- Detail: `GET /nasional/lelang/<id>/pengumumanlelang` (butuh cookie+Referer) → Nama Tender, Kode RUP, Instansi,
  Satuan Kerja, Jenis/Metode Pengadaan, Tahun Anggaran, **Nilai Pagu**, **Nilai HPS**, Lokasi, Syarat Kualifikasi, deskripsi.
- Jadwal: `GET /nasional/lelang/<id>/jadwal` → tabel tahap + tanggal (untuk `registration_*` & `bid_deadline`).
- Uji kata kunci: `sampah|limbah|TPST|…` → 9 paket relevan pada 2026+2027.
- **Keputusan:** sumber pertama yang diintegrasikan & diuji langsung.

### 2.4 Sumber lain yang diperiksa & ditolak
| Sumber | Hasil | Alasan |
|---|---|---|
| `lpse.pu.go.id`, `lpse.jakarta.go.id` | DNS tidak resolve | domain tidak tersedia |
| `lpse.kemenkeu.go.id`, `lpse.komdigi.go.id` | error sertifikat TLS | tidak aman/tidak stabil |
| `ckan.lkpp.go.id` | API hidup, tapi `robots.txt` `Disallow: /api/`; isi = data statistik agregat | bukan per-tender + dilarang robots |
| `data.lkpp.go.id` | portal Next.js, bukan CKAN | tidak ada API publik terdokumentasi |

> LPSE per-instansi bisa ditambahkan admin lewat dashboard sebagai `spse` (adapter sama) bila domainnya valid.

---

## 3. Arsitektur yang ditambahkan (tanpa membongkar Fase 1)

```
backend/app/
  config.py            (+) AI, SPSE, INAPROC, batas koleksi
  db.py                (+) insert / update / upsert / rpc
  utils/text.py        (+) strip_html, normalisasi, match keyword, parse rupiah/tanggal, dedupe hash
  ai/
    client.py          (+) Groq & OpenAI (OpenAI-compatible) via httpx
    prompts.py         (+) prompt + prompt_version
    validate.py        (+) validasi output AI sebelum disimpan
    service.py         (+) analyze_tender()
  sources/
    base.py            (+) RawTender, SourceAdapter, SourceError
    spse_nasional.py   (+) adapter teruji
    inaproc_api.py     (+) adapter resmi (butuh key)
    registry.py        (+) adapter_type -> adapter
  services/
    collection.py      (+) discovery, dedupe, simpan, kesehatan sumber, log
    analysis.py        (+) analisis tender + simpan (is_current)
  routers/
    tenders.py         (+) list/detail/koleksi manual/analisis/export Excel
    sources.py         (+) daftar sumber, health check, kelola keyword
frontend/src/
  pages/Tenders.jsx       (+) listing fungsional
  pages/TenderDetail.jsx  (+) detail + analisis AI
  components/Pagination.jsx, lib/format.js  (+)
  App.jsx, index.css      (ubah minimal, gaya Fase 1 dipertahankan)
```

**Alur koleksi:** adapter → `RawTender` → cocokkan keyword → `dedupe_hash` → upsert `tenders`
(`first_seen_at` tetap, `last_seen_at` diperbarui) → update kesehatan sumber + `system_logs`.
**Alur AI:** tender terpilih → prompt → Groq/OpenAI → validasi → `tender_analysis` (`is_current=true`,
versi lama di-`is_current=false`). Data mentah di `tenders` **tidak pernah** diubah AI.

**Dedupe:** `dedupe_hash = sha256(source_id : external_id)` (fallback: nama+instansi ternormalisasi),
unik di DB → upsert idempoten. Duplikat lintas-sumber dideteksi dengan kunci nama+instansi ternormalisasi.

---

## 4. Kontrak API baru

| Method | Path | Guna |
|---|---|---|
| GET | `/api/tenders` | listing: `q, priority, category, source_id, status, agency, date_from, date_to, sort, order, page, per_page` |
| GET | `/api/tenders/{id}` | detail + analisis AI terkini |
| GET | `/api/tenders/export` | Excel (.xlsx) sesuai filter |
| POST | `/api/tenders/collect` | pencarian manual (staff/admin): `{source_ids?, years?, keywords?, max_rows?}` |
| POST | `/api/tenders/{id}/analyze` | analisis 1 tender |
| POST | `/api/tenders/analyze-pending` | analisis sekumpulan tender (cap) |
| GET | `/api/sources` | daftar sumber + kesehatan |
| POST | `/api/sources/{id}/check` | health check sumber |
| GET/POST/PATCH/DELETE | `/api/keywords` | kelola keyword (admin) |

---

## 5. Rencana implementasi bertahap (tiap langkah diuji sebelum lanjut)

1. **Fondasi backend** — perluas `config.py`, `db.py` (tulis), `utils/text.py`. Test unit.
2. **Adapter SPSE** — bootstrap sesi, fetch per tahun, parse baris, detail & jadwal. Test dgn `MockTransport` + uji live terkontrol.
3. **Adapter INAPROC** — sesuai skema terdokumentasi, guard key. Test mock.
4. **Koleksi & dedupe** — `services/collection.py`. Test dedupe/upsert + kesehatan sumber.
5. **AI** — client, prompt, validasi, service. Test mock + validasi.
6. **Router tenders & sources** — list/detail/collect/analyze/export. Test API.
7. **Frontend** — listing, filter, sort, paginasi, detail, kontrol pencarian manual, export.
8. **Dokumentasi** — README/TESTING diperbarui (apa yang teruji, apa yang butuh kredensial).

**Migrasi:** `003_phase2_indexes.sql` — hanya `create index if not exists` (aman, non-destruktif),
dijalankan **opsional**; aplikasi tetap berjalan tanpanya.

**Yang TIDAK akan diklaim berfungsi tanpa kredensial:** INAPROC API Gateway (butuh token),
AI (butuh `GROQ_API_KEY`/`OPENAI_API_KEY`), SIRUP (butuh login).
