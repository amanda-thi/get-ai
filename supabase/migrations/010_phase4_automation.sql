-- Fase 4 — Automation & Intelligent Scheduling (idempoten, non-destruktif).
--
-- Menambah tabel konfigurasi automation, job, log job, dan notifikasi.
-- Tabel Fase 1 `automation_schedules` DIBIARKAN (tidak diubah/dihapus) untuk
-- kompatibilitas; sumber kebenaran jadwal Fase 4 adalah `automation_configs`.
-- Tidak ada data Phase 1/2/3 yang diubah secara destruktif.
--
-- Aman dijalankan berulang. Jalankan di Supabase SQL Editor.

create extension if not exists pgcrypto;

-- 1. automation_configs — satu baris per jenis automation
create table if not exists public.automation_configs (
  id uuid primary key default gen_random_uuid(),
  automation_name text not null,
  automation_type text not null unique,
  description text,
  is_enabled boolean not null default true,
  schedule_type text not null default 'weekly' check (schedule_type in ('daily','weekly','monthly','custom')),
  schedule_config jsonb not null default '{}'::jsonb,
  cron_expression text not null,
  timezone text not null default 'Asia/Jakarta',
  params jsonb not null default '{}'::jsonb,
  retry_max_attempts int not null default 2 check (retry_max_attempts between 0 and 10),
  retry_backoff_seconds int not null default 60 check (retry_backoff_seconds between 5 and 86400),
  timeout_seconds int not null default 900 check (timeout_seconds between 30 and 86400),
  last_run_at timestamptz,
  last_status text check (last_status in ('completed','partially_completed','failed','cancelled','running')),
  last_job_id uuid,
  next_run_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. automation_jobs — riwayat eksekusi (scheduled / manual / retry)
create table if not exists public.automation_jobs (
  id uuid primary key default gen_random_uuid(),
  automation_config_id uuid references public.automation_configs(id) on delete set null,
  job_name text not null,
  job_type text not null,
  trigger_type text not null default 'scheduled' check (trigger_type in ('scheduled','manual','retry')),
  status text not null default 'pending' check (status in
    ('pending','queued','running','completed','partially_completed','failed','cancelled')),
  progress int not null default 0 check (progress between 0 and 100),
  total_processed int not null default 0,
  success_count int not null default 0,
  failed_count int not null default 0,
  error_message text,
  attempt int not null default 1,
  max_attempts int not null default 1,
  idempotency_key text,
  cancel_requested boolean not null default false,
  parent_job_id uuid references public.automation_jobs(id) on delete set null,
  triggered_by uuid references public.users(id) on delete set null,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Lock terdistribusi level DB: hanya SATU job aktif (queued/running) per config.
-- Inilah pencegah job ganda saat ada beberapa instance backend.
create unique index if not exists uq_automation_jobs_active
  on public.automation_jobs(automation_config_id)
  where status in ('queued','running');

-- Idempotensi: kunci unik per slot (mis. per menit terjadwal) / eksekusi manual.
create unique index if not exists uq_automation_jobs_idem
  on public.automation_jobs(idempotency_key)
  where idempotency_key is not null;

create index if not exists idx_automation_jobs_created on public.automation_jobs(created_at desc);
create index if not exists idx_automation_jobs_status on public.automation_jobs(status);
create index if not exists idx_automation_jobs_type on public.automation_jobs(job_type);

-- 3. automation_job_logs — log terstruktur per job
create table if not exists public.automation_job_logs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.automation_jobs(id) on delete cascade,
  log_level text not null default 'info' check (log_level in ('debug','info','warning','error')),
  message text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_automation_job_logs_job on public.automation_job_logs(job_id, created_at);
create index if not exists idx_automation_job_logs_created on public.automation_job_logs(created_at desc);

-- 4. notifications — notifikasi internal (user_id NULL = broadcast ke admin)
create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  notification_type text not null,
  title text not null,
  message text not null,
  related_job_id uuid references public.automation_jobs(id) on delete set null,
  link text,
  dedupe_key text,
  is_read boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- Cegah notifikasi berulang untuk event yang sama.
create unique index if not exists uq_notifications_dedupe
  on public.notifications(dedupe_key)
  where dedupe_key is not null;
create index if not exists idx_notifications_user on public.notifications(user_id, created_at desc);
create index if not exists idx_notifications_unread on public.notifications(is_read) where not is_read;

-- FK last_job_id (dibuat setelah automation_jobs ada)
alter table public.automation_configs drop constraint if exists fk_automation_configs_last_job;
alter table public.automation_configs
  add constraint fk_automation_configs_last_job
  foreign key (last_job_id) references public.automation_jobs(id) on delete set null;

-- updated_at trigger + RLS (pola sama dengan migrasi 001)
do $$
declare t text;
begin
  foreach t in array array['automation_configs','automation_jobs','automation_job_logs','notifications'] loop
    execute format('drop trigger if exists trg_%s_updated on public.%I', t, t);
    execute format('create trigger trg_%s_updated before update on public.%I
                    for each row execute function public.set_updated_at()', t, t);
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- Baca: user aktif (backend tetap memegang kendali tulis lewat service role).
drop policy if exists automation_configs_select on public.automation_configs;
create policy automation_configs_select on public.automation_configs
  for select to authenticated using (public.is_active_user());
drop policy if exists automation_jobs_select on public.automation_jobs;
create policy automation_jobs_select on public.automation_jobs
  for select to authenticated using (public.is_active_user());
drop policy if exists automation_job_logs_select on public.automation_job_logs;
create policy automation_job_logs_select on public.automation_job_logs
  for select to authenticated using (public.is_active_user());

-- Notifikasi: milik sendiri, atau broadcast (user_id NULL) hanya untuk admin.
drop policy if exists notifications_select on public.notifications;
create policy notifications_select on public.notifications
  for select to authenticated
  using (user_id = auth.uid() or (user_id is null and public.is_admin()));

-- Hak akses eksplisit (idempoten).
grant select on public.automation_configs, public.automation_jobs, public.automation_job_logs, public.notifications to authenticated;
grant all    on public.automation_configs, public.automation_jobs, public.automation_job_logs, public.notifications to service_role;

-- Seed 4 automation default (jadwal sesuai spesifikasi Fase 4, WIB).
insert into public.automation_configs
  (automation_name, automation_type, description, schedule_type, schedule_config, cron_expression, timezone, params)
values
  ('Tender Monitoring', 'tender_monitoring',
   'Mencari tender baru dari sumber publik, menganalisis relevansi dengan AI, dan menandai deadline mendekat.',
   'weekly', '{"day_of_week":0,"hour":8,"minute":0}', '0 8 * * 1', 'Asia/Jakarta',
   '{"analyze_limit":25,"deadline_days":7}'),
  ('Company Discovery', 'company_discovery',
   'Mencari calon pelanggan baru dari sumber publik memakai daftar kata kunci dan lokasi.',
   'weekly', '{"day_of_week":1,"hour":9,"minute":0}', '0 9 * * 2', 'Asia/Jakarta',
   '{"queries":[],"locations":[],"industries":[],"limit":10}'),
  ('Lead Qualification', 'lead_qualification',
   'Menganalisis lead yang belum dikualifikasi: skor 0-100, prioritas, dan rekomendasi layanan.',
   'weekly', '{"day_of_week":1,"hour":10,"minute":0}', '0 10 * * 2', 'Asia/Jakarta',
   '{"limit":20}'),
  ('Outreach Draft Generation', 'outreach_draft_generation',
   'Membuat draft email penawaran untuk lead qualified berprioritas. TIDAK mengirim email.',
   'weekly', '{"day_of_week":2,"hour":9,"minute":0}', '0 9 * * 3', 'Asia/Jakarta',
   '{"limit":20,"email_type":"company_intro","language":"id","priorities":["HIGH","MEDIUM"]}')
on conflict (automation_type) do nothing;

notify pgrst, 'reload schema';
