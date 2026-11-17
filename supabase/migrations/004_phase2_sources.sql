-- Fase 2 — perbaikan/penambahan KONFIGURASI sumber (idempoten, non-destruktif).
-- 002_seed_config.sql menyemai SIRUP & INAPROC dengan status 'untested'.
-- Di sini kita: (1) menambah sumber SPSE Nasional yang sudah terverifikasi publik,
-- (2) mengoreksi base_url SIRUP yang sudah mati (migrasi ke sirup.inaproc.id)
--     dan menandainya 'manual_only' karena butuh login.

-- 1. Sumber pertama yang benar-benar terintegrasi (spse.inaproc.id, publik, teruji).
insert into public.tender_sources (name, adapter_type, base_url, config)
values ('SPSE Nasional', 'spse', 'https://spse.inaproc.id', '{"scope":"nasional"}'::jsonb)
on conflict (base_url) do nothing;

-- 2. SIRUP: domain lama tidak resolve. Perbaiki URL & tandai butuh login.
update public.tender_sources
set base_url = 'https://sirup.inaproc.id',
    health_status = 'manual_only',
    last_error = 'SIRUP butuh login (sirup.inaproc.id); tidak ada endpoint RUP publik.'
where adapter_type = 'sirup' and base_url = 'https://sirup.lkpp.go.id';

-- Catatan: INAPROC API Gateway (adapter_type 'inaproc') tetap 'untested' sampai
-- INAPROC_API_KEY diisi. Aktif otomatis tanpa perubahan skema.
