-- School partnerships managed from the moderation console (reviews_service admin) and leads taken by the leads
-- service on the Russian server. Personal data (leads) never leaves this database.
--
-- Roles (login roles are created on the server, never in Git):
--   reviews_leads  - the public leads API: reads enabled schools, creates/updates/deletes leads;
--   reviews_admin  - the console: edits lead_schools, reads leads, retries / marks them, flips the global switch.

alter table public.lead_schools add column if not exists agreement_date date;
alter table public.lead_schools add column if not exists notes text not null default '';

-- Global switches. leads_enabled is the master switch for the whole site; it starts OFF and only the console flips it.
create table if not exists public.site_flags (
  key varchar(40) primary key,
  value boolean not null default false,
  note varchar(300) not null default '',
  updated_at timestamp not null default (now() at time zone 'utc')
);
insert into public.site_flags (key, value, note) values ('leads_enabled', false, 'master switch for site leads') on conflict do nothing;
alter table public.site_flags enable row level security;
revoke all on public.site_flags from anon, authenticated;

-- Every catalog school gets a (disabled) settings row, so the console can fill it in and switch it on later.
insert into public.lead_schools (school_id) select id from public.schools on conflict do nothing;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'reviews_leads') then create role reviews_leads nologin; end if;
end $$;
grant usage on schema public to reviews_leads;
grant usage, select on all sequences in schema public to reviews_leads, reviews_admin;

-- schools: readable by the leads role too
grant select on public.schools to reviews_leads;
drop policy if exists schools_reviews_read on public.schools;
create policy schools_reviews_read on public.schools for select to reviews_public, reviews_admin, reviews_leads using (true);

-- lead_schools
grant select on public.lead_schools to reviews_leads;
grant select, insert, update on public.lead_schools to reviews_admin;
drop policy if exists lead_schools_leads_read on public.lead_schools;
create policy lead_schools_leads_read on public.lead_schools for select to reviews_leads using (true);
drop policy if exists lead_schools_admin on public.lead_schools;
create policy lead_schools_admin on public.lead_schools for all to reviews_admin using (true) with check (true);

-- leads
grant select, insert, update, delete on public.leads to reviews_leads;
grant select, insert, update on public.leads to reviews_admin;
drop policy if exists leads_leads_all on public.leads;
create policy leads_leads_all on public.leads for all to reviews_leads using (true) with check (true);
drop policy if exists leads_admin_all on public.leads;
create policy leads_admin_all on public.leads for all to reviews_admin using (true) with check (true);

-- site_flags: the leads service only reads, the console changes
grant select on public.site_flags to reviews_leads;
grant select, update on public.site_flags to reviews_admin;
drop policy if exists site_flags_read on public.site_flags;
create policy site_flags_read on public.site_flags for select to reviews_leads, reviews_admin using (true);
drop policy if exists site_flags_admin_update on public.site_flags;
create policy site_flags_admin_update on public.site_flags for update to reviews_admin using (true) with check (true);
