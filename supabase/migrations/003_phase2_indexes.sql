-- Fase 2 — indeks tambahan (OPSIONAL, non-destruktif).
-- Semua memakai "if not exists": aman dijalankan berulang dan aplikasi tetap
-- berjalan tanpanya. Tidak mengubah tabel/kolom yang sudah ada.

-- Urutan listing & export berdasarkan tanggal.
create index if not exists idx_tenders_announced on public.tenders(announced_at desc);
create index if not exists idx_tenders_first_seen on public.tenders(first_seen_at desc);

-- Pencarian keyword yang tersimpan (array) & filter prioritas analisis terkini sudah ada
-- (uq_tender_analysis_current, idx_tender_analysis_priority).
create index if not exists idx_tenders_matched_keywords on public.tenders using gin (matched_keywords);

-- Mempercepat join analisis terkini per tender pada listing.
create index if not exists idx_tender_analysis_tender_current on public.tender_analysis(tender_id) where is_current;
