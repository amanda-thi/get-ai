-- Fase integrasi pyproc: izinkan adapter_type 'pyproc' dan migrasikan sumber SPSE ke pyproc.
-- Idempoten; aman dijalankan ulang. Migrasi dijalankan manual di Supabase SQL Editor.

-- 1) Perluas constraint adapter_type agar menerima 'pyproc'.
do $$
declare
  cname text;
begin
  select con.conname into cname
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  join pg_namespace nsp on nsp.oid = rel.relnamespace
  where nsp.nspname = 'public'
    and rel.relname = 'tender_sources'
    and con.contype = 'c'
    and pg_get_constraintdef(con.oid) like '%adapter_type%'
  limit 1;

  if cname is not null then
    execute format('alter table public.tender_sources drop constraint %I', cname);
  end if;

  -- pastikan tidak ada duplikat constraint bernama sama
  alter table public.tender_sources
    drop constraint if exists tender_sources_adapter_type_check;

  alter table public.tender_sources
    add constraint tender_sources_adapter_type_check
    check (adapter_type in ('sirup','inaproc','spse','generic_html','manual','pyproc'));
end $$;

-- 2) Migrasikan sumber SPSE/LPSE (spse.inaproc.id) ke adapter pyproc.
--    config.host diset dari scope/host jika ada, selain itu 'nasional'.
update public.tender_sources
set adapter_type = 'pyproc',
    config = jsonb_set(
      coalesce(config, '{}'::jsonb),
      '{host}',
      to_jsonb(coalesce(config->>'host', config->>'scope', config->>'instansi', 'nasional')),
      true
    ),
    last_error = null,
    health_status = case when health_status = 'blocked' then 'untested' else health_status end
where adapter_type = 'spse'
   or base_url ilike '%spse.inaproc.id%';

-- Catatan: sumber adapter_type 'inaproc' (API Gateway resmi, data.inaproc.id, butuh token)
-- tidak diubah otomatis. Nonaktifkan secara manual jika tidak ingin memakainya:
--   update public.tender_sources set is_active = false
--   where adapter_type = 'inaproc' or base_url ilike '%inaproc%';
