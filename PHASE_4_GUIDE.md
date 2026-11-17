# Panduan Fase 4 — Automation & Intelligent Scheduling

Panduan ini untuk **pengguna non-teknis** (admin/staf). Fase 4 menambahkan **penjadwalan otomatis**:
sistem menjalankan sendiri tugas-tugas rutin (memantau tender, mencari calon pelanggan, menilai lead,
dan membuat draft email) sesuai jadwal — tanpa Anda perlu menekan tombol.

> **Prinsip penting:** Automation hanya **menyiapkan** pekerjaan. **Email tidak pernah dikirim
> otomatis.** Draft outreach yang dibuat otomatis tetap harus **disetujui admin** sebelum dikirim,
> sama seperti Fase 3.

---

## 1. Apa yang diotomatiskan?

Ada 4 tugas (automation) bawaan, masing-masing dengan jadwal awal (zona **Asia/Jakarta / WIB**):

| Automation | Jadwal awal | Yang dilakukan |
|---|---|---|
| **Tender Monitoring** | Senin 08:00 | Mencari tender baru dari sumber publik, menganalisis relevansinya dengan AI, dan menandai yang deadlinenya mendekat. |
| **Company Discovery** | Selasa 09:00 | Mencari calon pelanggan baru dari sumber publik memakai daftar kata kunci & lokasi. |
| **Lead Qualification** | Selasa 10:00 | Menilai lead yang belum dinilai: skor 0–100, prioritas, dan rekomendasi layanan. |
| **Outreach Draft Generation** | Rabu 09:00 | Membuat **draft** email penawaran untuk lead berprioritas. **Tidak mengirim email.** |

Semua jadwal bisa Anda ubah. Anda juga bisa menjalankan tugas **kapan saja** lewat tombol
**Jalankan sekarang**.

---

## 2. Membuka halaman Automation

Klik menu **Automation Settings** di sidebar kiri. Halaman ini punya 3 tab:

- **Ringkasan** — gambaran cepat: berapa job sudah berjalan, berapa yang selesai/gagal, jadwal
  berikutnya, dan job terakhir.
- **Konfigurasi** — daftar 4 automation. Di sini Anda mengubah jadwal, mengaktifkan/menonaktifkan,
  atau menjalankannya sekarang.
- **Riwayat job** — daftar semua eksekusi (job) dengan filter dan detail lengkap.

---

## 3. Tab "Ringkasan"

Menampilkan:

- **Kartu angka**: total job, sedang berjalan, selesai, selesai sebagian, gagal, dibatalkan, menunggu,
  dan rata-rata durasi.
- **Jadwal berikutnya**: kapan tiap automation akan berjalan lagi.
- **Job terakhir**: daftar eksekusi terbaru. **Klik satu baris** untuk membuka detail job.

Angka di sini **nyata dari database**. Jika belum ada job, tampil ajakan (bukan data contoh).

---

## 4. Tab "Konfigurasi"

Setiap automation ditampilkan sebagai satu kartu berisi:

- **Nama & jenis** automation.
- **Jadwal** dalam bahasa manusia, mis. "Setiap Senin pukul 08:00 (Asia/Jakarta)".
- **Jalannya berikutnya** dan **jalan terakhir**, serta **status terakhir** (Selesai, Gagal, dst.).
- **Retry / timeout**: berapa kali dicoba ulang, jeda, dan batas waktu per job.
- Label **aktif / nonaktif**.

Di bagian atas ada **Kesiapan integrasi**: penanda apakah kunci yang dibutuhkan sudah diisi
(AI, pencarian lead, INAPROC, SMTP). Bila sebuah kunci belum diisi, kartu automation yang
memerlukannya menampilkan peringatan dan job akan **gagal dengan pesan jelas** — bukan dianggap
sukses.

### Tombol pada tiap kartu (khusus admin)

| Tombol | Fungsi |
|---|---|
| **Jalankan sekarang** | Menjalankan job saat itu juga (di latar belakang). Muncul dialog konfirmasi. |
| **Ubah jadwal** | Membuka editor jadwal (lihat §5). |
| **Aktifkan / Nonaktifkan** | Menyalakan/mematikan jadwal. Menonaktifkan meminta konfirmasi. |

> **Tidak ada job ganda.** Jika sebuah automation sedang berjalan, permintaan "Jalankan sekarang"
> akan ditolak sampai job sebelumnya selesai.

---

## 5. Mengubah jadwal

Klik **Ubah jadwal** pada kartu automation. Anda bisa mengatur:

- **Nama** automation.
- **Jenis jadwal**:
  - **Setiap hari** — pilih jam & menit.
  - **Mingguan** — pilih hari (Senin–Minggu), jam & menit.
  - **Bulanan** — pilih tanggal (1–28), jam & menit.
  - **Kustom (cron)** — tulis ekspresi cron standar 5 bagian, mis. `0 8 * * 1`.
- **Zona waktu** (bawaan `Asia/Jakarta`).
- **Maks. percobaan ulang**, **jeda awal retry (detik)**, dan **batas waktu job (detik)**.
- **Parameter** — pengaturan lanjutan per jenis automation, dalam format JSON. Contoh kunci:
  - Tender Monitoring: `analyze_limit`, `deadline_days`
  - Company Discovery: `queries`, `locations`, `industries`, `limit`
  - Lead Qualification: `limit`
  - Outreach Draft Generation: `limit`, `email_type`, `language`, `priorities`, `min_score`

Klik **Simpan**. Perubahan langsung dipakai scheduler dan tetap tersimpan setelah server restart.

---

## 6. Tab "Riwayat job"

Menampilkan semua eksekusi beserta statusnya. Filter tersedia: **jenis** automation, **status**,
**pemicu** (Terjadwal / Manual / Percobaan ulang), dan **rentang tanggal**.

Arti status:

| Status | Arti |
|---|---|
| **Menunggu** (pending) | Sudah dibuat, belum masuk antrean. |
| **Dalam antrean** (queued) | Menunggu giliran dijalankan. |
| **Berjalan** (running) | Sedang dieksekusi. |
| **Selesai** (completed) | Semua langkah berhasil. |
| **Selesai sebagian** (partially completed) | Sebagian berhasil, sebagian gagal. |
| **Gagal** (failed) | Job gagal (mis. kunci API belum diisi). |
| **Dibatalkan** (cancelled) | Dihentikan atas permintaan admin. |

**Klik satu baris** untuk membuka **detail job**: waktu mulai/selesai, durasi, jumlah diproses/
sukses/gagal, **progres**, **pesan galat** (bila ada), **riwayat percobaan ulang**, dan **log**
kronologis.

### Aksi pada detail job (khusus admin)

- **Jalankan ulang** — membuat job baru untuk automation yang sama (mis. setelah kunci API
  dilengkapi). Muncul konfirmasi.
- **Batalkan** — untuk job yang masih menunggu/berjalan. Pembatalan job yang **sedang berjalan
  bersifat kooperatif**: job berhenti pada titik pemeriksaan berikutnya, bukan seketika.

---

## 7. Notifikasi

Di kanan atas (topbar) ada ikon **lonceng**. Angka merah menunjukkan jumlah notifikasi yang
**belum dibaca**. Klik untuk membuka daftar.

- Notifikasi muncul otomatis saat sebuah automation **selesai**, **selesai sebagian**, atau **gagal**.
- Klik satu notifikasi untuk **menandai dibaca** dan menuju halaman terkait.
- Tombol **Tandai semua dibaca** menandai seluruh daftar.
- Admin juga melihat notifikasi **siaran** (broadcast) untuk seluruh tim. Staf hanya melihat
  notifikasi miliknya sendiri.

Bila diisi, notifikasi juga bisa dikirim ke email admin (opsional, butuh `SMTP_*` dan
`AUTOMATION_NOTIFY_EMAIL=true`).

---

## 8. Keandalan: apa yang membuat automation aman?

- **Tidak ada job ganda** — satu automation hanya boleh punya satu job aktif (dijaga di database).
- **Idempoten** — permintaan yang sama tidak membuat data ganda.
- **Percobaan ulang otomatis** dengan jeda yang makin panjang (exponential backoff) sampai batas
  percobaan.
- **Batas waktu** per job (kooperatif) dan **pembersihan job yang macet**.
- **Tetap ada setelah restart** — jadwal & status disimpan di database, bukan di memori.
- **Hanya admin** yang boleh mengubah jadwal dan menjalankan/membatalkan job. Semua endpoint butuh
  login; aksi tulis dibatasi rate limit.
- **Kunci rahasia** hanya disimpan di `.env` backend, tidak pernah dikirim ke browser.

---

## 9. Syarat: migrasi database

Fase 4 memakai 4 tabel baru (`automation_configs`, `automation_jobs`, `automation_job_logs`,
`notifications`). Tabel ini dibuat oleh migrasi:

```
supabase/migrations/010_phase4_automation.sql
```

**Jalankan file ini di Supabase SQL Editor** (satu kali). Sebelum dijalankan, halaman Automation
menampilkan pesan: *"Tabel Fase 4 belum ada. Jalankan migrasi …"*. Setelah dijalankan, halaman
langsung berfungsi (muat ulang browser).

Migrasi ini **non-destruktif & idempoten**: tidak menghapus data Fase 1–3, dan aman dijalankan
ulang. Tabel `automation_schedules` dari Fase 1 tidak diubah.

---

## 10. Kapan sebuah automation butuh kunci?

| Automation | Butuh |
|---|---|
| Tender Monitoring | Koleksi SPSE berjalan tanpa kunci; analisis AI butuh `GROQ_API_KEY`/`OPENAI_API_KEY`; `INAPROC_API_KEY` hanya bila ingin memakai API Gateway resmi. |
| Company Discovery | `LEAD_SEARCH_PROVIDER` + `LEAD_SEARCH_API_KEY` untuk pencarian kata kunci. |
| Lead Qualification | `GROQ_API_KEY`/`OPENAI_API_KEY`. |
| Outreach Draft Generation | `GROQ_API_KEY`/`OPENAI_API_KEY` (SMTP **tidak** diperlukan untuk membuat draft). |

Bila kunci belum ada, job ditandai **gagal** dengan pesan yang menjelaskan kunci mana yang kurang.
Isi kunci di `.env` backend lalu restart backend.
