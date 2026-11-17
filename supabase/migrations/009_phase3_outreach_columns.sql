-- Fase 3 — perbaikan: pastikan kolom audit email outreach ada.
--
-- Migrasi 008 versi awal hanya membuat view `leads_with_analysis`. Kolom
-- `outreach_messages.template_id` dan `outreach_messages.ai_model` ditambahkan
-- belakangan, sehingga database yang sudah menjalankan 008 versi lama akan
-- kehilangan kedua kolom itu (listing pesan outreach → HTTP 503 / PostgREST 42703).
--
-- Migrasi ini mengisi kolom yang hilang secara idempoten agar DB sinkron dengan
-- kode backend. Non-destruktif. Jalankan di Supabase SQL Editor setelah 001–008.

alter table public.outreach_messages
  add column if not exists template_id uuid references public.email_templates(id) on delete set null;
alter table public.outreach_messages
  add column if not exists ai_model text;

-- Segarkan cache skema PostgREST agar kolom baru langsung dikenali.
notify pgrst, 'reload schema';
