-- Fase 2 — hak akses eksplisit untuk schema public (idempoten, non-destruktif).
--
-- Kenapa perlu: sebagian project Supabase TIDAK mewarisi default privileges,
-- sehingga role anon/authenticated/service_role tidak punya GRANT pada tabel
-- buatan migrasi 001. Akibatnya PostgREST menjawab 42501 "permission denied
-- for table ...". Migrasi ini memastikan hak akses sesuai desain aplikasi:
--   * authenticated : SELECT saja (RLS tetap membatasi baris yang terlihat)
--   * service_role  : ALL (backend menulis, bypass RLS)
--   * anon          : tanpa akses tabel (dipakai hanya untuk login/GoTrue)
--
-- Aman dijalankan berulang. Jalankan di Supabase SQL Editor.

grant usage on schema public to authenticated, service_role;

-- Hak untuk tabel yang SUDAH ada.
grant select on all tables in schema public to authenticated;
grant all    on all tables in schema public to service_role;
grant all    on all sequences in schema public to service_role;
grant all    on all functions in schema public to service_role;

-- Supaya tabel/sequence/fungsi BARU di masa depan otomatis mengikuti.
-- (Dijalankan sebagai role pembuat; di SQL Editor biasanya 'postgres'.)
alter default privileges in schema public grant select on tables to authenticated;
alter default privileges in schema public grant all    on tables to service_role;
alter default privileges in schema public grant all    on sequences to service_role;
alter default privileges in schema public grant all    on functions to service_role;
