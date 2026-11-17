# Panduan Fase 3 — Company Leads & Marketing Outreach

Panduan ini untuk **pengguna non-teknis** (admin/staf marketing). Tujuan Fase 3: membantu
Anda menemukan calon pelanggan, menilai kecocokannya, dan mengirim email penawaran — dengan
AI sebagai penulis draf, tetapi **keputusan akhir selalu di tangan admin**.

---

## 1. Apa itu "Company Leads"?

Menu **Company Leads** adalah daftar perusahaan calon pelanggan. Untuk setiap perusahaan,
sistem menyimpan:
- **Data perusahaan**: nama, industri, alamat, kota/provinsi, situs web, deskripsi.
- **Kontak bisnis publik**: email/telepon yang dipublikasikan perusahaan (beserta sumbernya).
- **Status CRM**: sejauh mana hubungan berjalan (lihat §5).
- **Penilaian AI**: seberapa cocok perusahaan itu dengan layanan kita (skor 0–100 + alasan).

> Semua data berasal dari **sumber publik** atau **yang Anda masukkan sendiri**. Sistem tidak
> menembus login/CAPTCHA dan menghormati aturan situs (`robots.txt`).

---

## 2. Menambah perusahaan (4 cara)

Buka **Company Leads** → tombol **Tambah / cari perusahaan**. Ada 4 tab:

### a. Tambah manual
Isi nama perusahaan (wajib), lalu data lain bila ada. Cocok untuk perusahaan yang sudah Anda
kenal. Email/telepon dipisah dengan koma.

### b. Dari situs web
Tempel satu atau beberapa alamat situs (satu per baris), mis. `acme.co.id`. Sistem akan:
1. Membuka halaman utama + halaman kontak/tentang yang ditautkan.
2. Mengambil email & telepon bisnis yang **tertera di halaman itu**.
3. Menyimpan perusahaan + kontaknya secara otomatis.

Jika sebuah situs memblokir pengambilan otomatis, sistem melaporkannya sebagai gagal — tidak
ada data yang dipaksakan.

### c. Impor daftar
Tempel banyak perusahaan sekaligus. Satu perusahaan per baris, dipisah tanda **`|`**:

```
Nama | Website | Industri | Kota | email1;email2 | telepon1;telepon2
PT Contoh Jaya | contoh.co.id | Daur ulang | Bandung | info@contoh.co.id | 022-1234567
```

### d. Pencarian (butuh kunci API)
Mencari perusahaan lewat mesin pencari berdasarkan kata kunci. Fitur ini **perlu kunci API
berbayar** (`LEAD_SEARCH_API_KEY`). Bila belum diisi, gunakan cara a–c.

**Duplikat otomatis dicegah:** jika perusahaan dengan nama & situs yang sama sudah ada, sistem
tidak menambah baris baru, melainkan melaporkannya sebagai "duplikat".

---

## 3. Kualifikasi dengan AI

Kualifikasi = menilai kecocokan perusahaan sebagai calon pelanggan.

- **Satu perusahaan**: buka detailnya → tombol **Kualifikasi dengan AI**.
- **Banyak sekaligus**: di daftar → tombol **Kualifikasi massal (AI)** (memproses beberapa
  perusahaan yang belum dianalisis).

Hasilnya berupa **skor 0–100**, **kategori** (HIGH/MEDIUM/LOW), **klasifikasi industri**,
**produk/layanan yang mungkin dibutuhkan**, **alasan skor**, dan **saran pendekatan**.

> AI hanya menilai berdasarkan data yang ada di sistem + profil resmi perusahaan kita
> (`config/company_profile.yaml`). AI **dilarang mengarang** sertifikasi, pengalaman, kapasitas,
> harga, atau spesifikasi. Karena itu jangan heran bila alasan skornya konservatif.

Riwayat penilaian disimpan; Anda bisa melakukan kualifikasi ulang kapan saja (hasil lama tetap
tersimpan sebagai riwayat).

---

## 4. Membuat & mengirim email penawaran

Buka **Marketing Outreach**. Ada tiga tab: **Pesan**, **Template**, **Kampanye**.

### Membuat draft dengan AI
Di tab **Pesan** → panel **Buat email dengan AI**:
1. Pilih **perusahaan tujuan**.
2. Pilih **jenis email** (perkenalan, penawaran layanan, proposal kerja sama, tindak lanjut, dll.).
3. Pilih **bahasa** (Indonesia / English / 한국어).
4. Opsional: pilih **template**, isi **email tujuan**, atau tulis **instruksi tambahan**.
5. Klik **Buat draft**.

Draft tersimpan dengan status **Draft** dan **belum terkirim**. Anda bisa membuka dan mengeditnya.

### Menyetujui & mengirim (hanya admin)
Buka sebuah email (klik barisnya) → halaman detail:
1. Periksa & edit subjek/isi bila perlu → **Simpan perubahan**.
2. **Setujui** → status menjadi *Disetujui*.
3. **Kirim email** → status menjadi *Terkirim*.

> **Aturan penting:** email **tidak akan terkirim** sebelum disetujui admin. Aturan ini juga
> ditegakkan oleh database, bukan sekadar tampilan. Staf biasa bisa membuat & mengedit draft,
> tetapi hanya admin yang bisa menyetujui & mengirim.

### Template
Kerangka email yang bisa dipakai ulang saat membuat draft. Hanya admin yang bisa membuat,
mengaktifkan/menonaktifkan, dan menghapus template.

### Kampanye
Wadah untuk mengelompokkan email (mis. "Promo Q1"). Admin bisa membuat, menjeda, melanjutkan,
atau menyelesaikan kampanye.

---

## 5. Arti status pada daftar perusahaan

| Label di layar | Arti |
|---|---|
| **New** | Baru ditambahkan, belum dihubungi. |
| **Qualified** | Sudah dinilai AI dan layak didekati. |
| **Contacted** | Sudah dikirim email. |
| **Responded** | Perusahaan sudah membalas. |
| **Interested** | Sedang dalam pembicaraan/negosiasi. |
| **Converted** | Berhasil menjadi pelanggan. |
| **Not Interested** | Menolak / tidak cocok. |
| **Do Not Contact** | Jangan dihubungi lagi. |

Ubah status di halaman detail perusahaan (bagian **Status & catatan**), lalu **Simpan**.

---

## 6. Bila ada fitur yang belum aktif

Sistem akan menampilkan keterangan bila sebuah fitur belum siap — bukan tombol yang diam-diam
tidak bekerja. Penyebab umum:

| Pesan / kondisi | Arti & tindakan |
|---|---|
| "SMTP belum dikonfigurasi" | Email bisa dibuat & disimpan sebagai draft, tetapi **belum bisa dikirim**. Minta admin teknis mengisi `SMTP_*`. |
| "Kunci AI belum diisi" | Kualifikasi & pembuatan email otomatis belum aktif. Minta admin teknis mengisi `GROQ_API_KEY`/`OPENAI_API_KEY`. |
| Tab "Pencarian" butuh kunci | Pencarian perusahaan berbasis kata kunci butuh `LEAD_SEARCH_PROVIDER` + `LEAD_SEARCH_API_KEY`. Gunakan cara manual/impor/URL. |
| Daftar perusahaan / pesan gagal dimuat | Pastikan migrasi `008_phase3_leads_view.sql` **dan** `009_phase3_outreach_columns.sql` sudah dijalankan (lihat §7). |

---

## 7. Langkah satu kali (untuk admin teknis)

Sebelum halaman **Company Leads** dan **Pesan** bisa menampilkan daftar, jalankan migrasi
terakhir **satu kali** di **Supabase → SQL Editor**:

1. Buka file `supabase/migrations/008_phase3_leads_view.sql`.
2. Salin seluruh isinya, tempel ke SQL Editor, klik **Run**.
3. Ulangi langkah yang sama untuk `supabase/migrations/009_phase3_outreach_columns.sql`.

Migrasi ini aman (tidak menghapus data) dan bisa dijalankan berulang kali.

Setelah itu, untuk mengaktifkan **pengiriman email**, isi variabel berikut di file `.env`
(rahasia — jangan dibagikan): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
`SMTP_FROM`. Muat ulang backend setelahnya.

---

## 8. Hal yang sengaja TIDAK dilakukan sistem

- Tidak mengirim email tanpa persetujuan admin.
- Tidak mengarang fakta perusahaan (sertifikasi, pengalaman, kapasitas, harga, spesifikasi).
- Tidak menembus login, CAPTCHA, paywall, atau larangan `robots.txt`.
- Tidak membuat data contoh/dummy di lingkungan produksi.
