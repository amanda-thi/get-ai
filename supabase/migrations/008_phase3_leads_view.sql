-- Fase 3 — view baca listing lead + analisis terkini (satu baris per perusahaan)
--          dan kolom audit untuk email outreach.
--
-- Kenapa view: `company_leads` -> `lead_analysis` adalah relasi SATU-KE-BANYAK, sehingga
-- PostgREST tidak bisa mengurutkan/memfilter lead berdasarkan kolom analisis (PGRST118).
-- View ini meratakan lead (`lead_*`) dan analisis `is_current` (`analysis_*`) menjadi kolom
-- biasa, sama polanya dengan `tenders_with_analysis` (migrasi 007).
--
-- Non-destruktif & idempoten. Jalankan di Supabase SQL Editor setelah 001–007.

-- 1) Kolom audit pada email outreach (untuk menautkan template & mencatat model AI).
alter table public.outreach_messages
  add column if not exists template_id uuid references public.email_templates(id) on delete set null;
alter table public.outreach_messages
  add column if not exists ai_model text;

-- 2) View listing lead + analisis terkini.
create or replace view public.leads_with_analysis
with (security_invoker = true) as
select
  c.*,
  l.id          as lead_id,
  l.status      as lead_status,
  l.notes       as lead_notes,
  l.assigned_to as lead_assigned_to,
  a.id                   as analysis_id,
  a.lead_score           as analysis_lead_score,
  a.category             as analysis_category,
  a.industry_classification as analysis_industry_classification,
  a.potential_products   as analysis_potential_products,
  a.reason               as analysis_reason,
  a.suggested_approach   as analysis_suggested_approach,
  a.created_at           as analysis_created_at
from public.companies c
left join public.company_leads l
  on l.company_id = c.id
left join public.lead_analysis a
  on a.lead_id = l.id
 and a.is_current;

grant select on public.leads_with_analysis to authenticated, service_role;

-- Segarkan cache skema PostgREST agar view & kolom baru langsung dikenali.
notify pgrst, 'reload schema';
