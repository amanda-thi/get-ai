-- Fase 2 — view baca untuk listing tender + analisis terkini (satu baris per tender).
--
-- Kenapa perlu: `tenders` -> `tender_analysis` adalah relasi SATU-KE-BANYAK, sehingga
-- PostgREST tidak bisa mengurutkan baris tender berdasarkan kolom analisis
-- (error PGRST118: "A related order on 'tender_analysis' is not possible"). View ini
-- meratakan analisis `is_current` (dijamin satu per tender oleh indeks
-- uq_tender_analysis_current) menjadi kolom biasa `analysis_*`, sehingga filter
-- prioritas/kategori dan urut skor relevansi bisa langsung di query.
--
-- `security_invoker = true` (Postgres 15+, dipakai Supabase) agar RLS pada tabel dasar
-- tetap berlaku untuk role `authenticated` (frontend). Non-destruktif & idempoten.

create or replace view public.tenders_with_analysis
with (security_invoker = true) as
select
  t.*,
  a.id              as analysis_id,
  a.category        as analysis_category,
  a.relevance_score as analysis_relevance_score,
  a.priority        as analysis_priority,
  a.score_reason    as analysis_score_reason,
  a.deadline_flag   as analysis_deadline_flag,
  a.created_at      as analysis_created_at
from public.tenders t
left join public.tender_analysis a
  on a.tender_id = t.id
 and a.is_current;

grant select on public.tenders_with_analysis to authenticated, service_role;

-- Segarkan cache skema PostgREST agar view langsung dikenali.
notify pgrst, 'reload schema';
