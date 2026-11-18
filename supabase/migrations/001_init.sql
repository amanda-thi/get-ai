-- Green Eco Teknologi — skema awal
-- Jalankan di Supabase SQL Editor (urutan: 001 lalu 002).
-- Akses tulis dilakukan backend via service role (bypass RLS). Frontend hanya SELECT.

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$ begin new.updated_at = now(); return new; end $$;

-- 1. users (profil untuk auth.users)
create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text not null default '',
  role text not null default 'staff' check (role in ('admin','staff')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.is_active_user() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.users where id = auth.uid() and is_active)
$$;
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.users where id = auth.uid() and is_active and role = 'admin')
$$;

-- User pertama yang terdaftar = admin, sisanya staff. Matikan sign-up publik di Supabase setelah akun dibuat.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.users (id, email, full_name, role)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name',''),
          case when exists (select 1 from public.users) then 'staff' else 'admin' end);
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- 2. tender_sources
create table public.tender_sources (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  adapter_type text not null check (adapter_type in ('sirup','inaproc','spse','generic_html','manual')),
  base_url text not null unique,
  config jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  health_status text not null default 'untested'
    check (health_status in ('untested','ok','failed','blocked','manual_only')),
  last_checked_at timestamptz,
  last_success_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. tender_keywords
create table public.tender_keywords (
  id uuid primary key default gen_random_uuid(),
  keyword text not null unique,
  category text not null,
  language text not null default 'en' check (language in ('en','id')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 4. tenders (data mentah dari sumber; tidak diubah AI)
create table public.tenders (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.tender_sources(id) on delete restrict,
  external_id text,
  dedupe_hash text not null unique,
  package_name text not null,
  agency text,
  location text,
  procurement_type text,
  description text,
  technical_specs text,
  budget_ceiling numeric(20,2),
  hps numeric(20,2),
  announced_at date,
  registration_start timestamptz,
  registration_end timestamptz,
  bid_deadline timestamptz,
  participant_requirements text,
  status text,
  source_url text not null,
  raw_payload jsonb,
  matched_keywords text[] not null default '{}',
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, external_id)
);

-- 5. tender_analysis (hasil AI, terpisah dari data mentah)
create table public.tender_analysis (
  id uuid primary key default gen_random_uuid(),
  tender_id uuid not null references public.tenders(id) on delete cascade,
  category text,
  relevance_score int not null check (relevance_score between 0 and 100),
  priority text not null check (priority in ('HIGH','MEDIUM','LOW')),
  score_reason text not null,
  equipment_needs text,
  cooperation_opportunity text,
  key_requirements text,
  deadline_flag text,
  model text not null,
  prompt_version text not null,
  raw_ai_output jsonb,
  is_current boolean not null default true,
  verified_by uuid references public.users(id),
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index uq_tender_analysis_current on public.tender_analysis(tender_id) where is_current;

-- 6. companies
create table public.companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  normalized_name text not null,
  industry text,
  description text,
  address text,
  city text,
  province text,
  website text,
  source_name text not null,
  source_url text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index uq_companies_name_site on public.companies(normalized_name, coalesce(website,''));

-- 7. company_contacts (hanya kontak bisnis publik, wajib ada sumber)
create table public.company_contacts (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id) on delete cascade,
  contact_type text not null check (contact_type in ('email','phone')),
  value text not null,
  source_url text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, contact_type, value)
);

-- 8. company_leads
create table public.company_leads (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null unique references public.companies(id) on delete cascade,
  status text not null default 'new' check (status in
    ('new','qualified','contacted','responded','negotiation','won','lost','do_not_contact')),
  notes text,
  assigned_to uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 9. lead_analysis
create table public.lead_analysis (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.company_leads(id) on delete cascade,
  lead_score int not null check (lead_score between 0 and 100),
  category text not null check (category in ('HIGH','MEDIUM','LOW')),
  industry_classification text,
  potential_products text[] not null default '{}',
  reason text not null,
  suggested_approach text,
  model text not null,
  prompt_version text not null,
  raw_ai_output jsonb,
  is_current boolean not null default true,
  verified_by uuid references public.users(id),
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index uq_lead_analysis_current on public.lead_analysis(lead_id) where is_current;

-- 10. email_templates
create table public.email_templates (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email_type text not null check (email_type in
    ('company_intro','product_intro','partnership_proposal','service_offering','follow_up')),
  language text not null check (language in ('id','en','ko')),
  subject text not null,
  body text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (email_type, language, name)
);

-- 11. outreach_campaigns
create table public.outreach_campaigns (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  status text not null default 'active' check (status in ('active','paused','completed')),
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 12. outreach_messages — DB menjamin email approved/sent selalu punya approver
create table public.outreach_messages (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references public.outreach_campaigns(id) on delete set null,
  lead_id uuid references public.company_leads(id) on delete set null,
  contact_id uuid references public.company_contacts(id) on delete set null,
  email_type text not null check (email_type in
    ('company_intro','product_intro','partnership_proposal','service_offering','follow_up')),
  language text not null check (language in ('id','en','ko')),
  recipient_email text,
  subject text not null,
  body text not null,
  status text not null default 'draft' check (status in
    ('draft','saved_for_later','approved','sent','failed')),
  approved_by uuid references public.users(id),
  approved_at timestamptz,
  sent_at timestamptz,
  provider_message_id text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_approval_required check
    (status not in ('approved','sent') or (approved_by is not null and approved_at is not null))
);

-- 13. outreach_logs
create table public.outreach_logs (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.outreach_messages(id) on delete cascade,
  event_type text not null check (event_type in
    ('created','edited','approved','sent','failed','delivered','replied','follow_up_scheduled','note')),
  details jsonb not null default '{}'::jsonb,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 14. automation_schedules
create table public.automation_schedules (
  id uuid primary key default gen_random_uuid(),
  job_type text not null unique check (job_type in ('weekly_tender_search','weekly_report')),
  cron_expression text not null,
  timezone text not null default 'Asia/Jakarta',
  is_active boolean not null default true,
  last_run_at timestamptz,
  last_status text check (last_status in ('success','partial','failed','running')),
  next_run_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 15. system_logs
create table public.system_logs (
  id uuid primary key default gen_random_uuid(),
  level text not null check (level in ('debug','info','warning','error')),
  component text not null,
  message text not null,
  details jsonb,
  user_id uuid references public.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 16. application_settings (NON-rahasia saja; API key hanya di env backend)
create table public.application_settings (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  value jsonb not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Indexes
create index idx_tenders_deadline on public.tenders(bid_deadline);
create index idx_tenders_status on public.tenders(status);
create index idx_tenders_agency on public.tenders(agency);
create index idx_tenders_location on public.tenders(location);
create index idx_tenders_source on public.tenders(source_id);
create index idx_tenders_name_trgm on public.tenders using gin (package_name gin_trgm_ops);
create index idx_tender_analysis_priority on public.tender_analysis(priority, relevance_score desc) where is_current;
create index idx_companies_city on public.companies(province, city);
create index idx_lead_analysis_cat on public.lead_analysis(category, lead_score desc) where is_current;
create index idx_leads_status on public.company_leads(status);
create index idx_msgs_status on public.outreach_messages(status);
create index idx_msgs_lead on public.outreach_messages(lead_id);
create index idx_outreach_logs_msg on public.outreach_logs(message_id);
create index idx_syslogs_created on public.system_logs(created_at desc);
create index idx_syslogs_level on public.system_logs(level);

-- updated_at trigger + RLS untuk semua tabel
do $$
declare t text;
begin
  foreach t in array array['users','tender_sources','tender_keywords','tenders','tender_analysis',
    'companies','company_contacts','company_leads','lead_analysis','email_templates',
    'outreach_campaigns','outreach_messages','outreach_logs','automation_schedules',
    'system_logs','application_settings'] loop
    execute format('create trigger trg_%s_updated before update on public.%I
                    for each row execute function public.set_updated_at()', t, t);
    execute format('alter table public.%I enable row level security', t);
  end loop;

  -- baca: semua user aktif
  foreach t in array array['tender_sources','tender_keywords','tenders','tender_analysis','companies',
    'company_contacts','company_leads','lead_analysis','email_templates','outreach_campaigns',
    'outreach_messages','outreach_logs','automation_schedules'] loop
    execute format('create policy "%s_select" on public.%I for select to authenticated
                    using (public.is_active_user())', t, t);
  end loop;
end $$;

create policy users_select on public.users for select to authenticated
  using (id = auth.uid() or public.is_admin());
create policy system_logs_select on public.system_logs for select to authenticated using (public.is_admin());
create policy app_settings_select on public.application_settings for select to authenticated using (public.is_admin());
-- Tidak ada policy INSERT/UPDATE/DELETE: semua tulis lewat backend (service role).

-- Default schedule: Senin 08.00 WIB
insert into public.automation_schedules (job_type, cron_expression, timezone)
values ('weekly_tender_search', '0 8 * * 1', 'Asia/Jakarta'),
       ('weekly_report', '30 8 * * 1', 'Asia/Jakarta');
