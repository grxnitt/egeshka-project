alter table public.schools enable row level security;
alter table public.teachers enable row level security;
alter table public.courses enable row level security;
alter table public.users enable row level security;
alter table public.reviews enable row level security;
alter table public.review_criterion_scores enable row level security;
alter table public.events enable row level security;
alter table public.rating_snapshots enable row level security;
alter table public.rating_runs enable row level security;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

grant usage on schema public to anon, authenticated;
grant select on public.schools, public.teachers, public.courses, public.rating_snapshots to anon, authenticated;

drop policy if exists schools_public_read on public.schools;
create policy schools_public_read on public.schools for select to anon, authenticated using (is_active);

drop policy if exists teachers_public_read on public.teachers;
create policy teachers_public_read on public.teachers for select to anon, authenticated using (is_active);

drop policy if exists courses_public_read on public.courses;
create policy courses_public_read on public.courses for select to anon, authenticated using (is_active);

drop policy if exists rating_snapshots_public_read on public.rating_snapshots;
create policy rating_snapshots_public_read on public.rating_snapshots for select to anon, authenticated using (true);

-- Direct bot connections inherit this no-login role. A separate login role and
-- password are created manually, so no secret is ever committed to Git.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'egeshka_bot_app') then
    create role egeshka_bot_app nologin;
  end if;
end $$;

grant usage on schema public to egeshka_bot_app;
grant select, insert, update on public.users, public.reviews, public.review_criterion_scores, public.events to egeshka_bot_app;
grant select on public.schools, public.teachers, public.courses, public.rating_snapshots to egeshka_bot_app;
grant usage, select on all sequences in schema public to egeshka_bot_app;

drop policy if exists schools_bot_read on public.schools;
create policy schools_bot_read on public.schools for select to egeshka_bot_app using (true);
drop policy if exists teachers_bot_read on public.teachers;
create policy teachers_bot_read on public.teachers for select to egeshka_bot_app using (true);
drop policy if exists courses_bot_read on public.courses;
create policy courses_bot_read on public.courses for select to egeshka_bot_app using (true);
drop policy if exists rating_snapshots_bot_read on public.rating_snapshots;
create policy rating_snapshots_bot_read on public.rating_snapshots for select to egeshka_bot_app using (true);

drop policy if exists users_bot_write on public.users;
create policy users_bot_write on public.users for all to egeshka_bot_app using (true) with check (true);
drop policy if exists reviews_bot_write on public.reviews;
create policy reviews_bot_write on public.reviews for all to egeshka_bot_app using (true) with check (true);
drop policy if exists review_scores_bot_write on public.review_criterion_scores;
create policy review_scores_bot_write on public.review_criterion_scores for all to egeshka_bot_app using (true) with check (true);
drop policy if exists events_bot_write on public.events;
create policy events_bot_write on public.events for all to egeshka_bot_app using (true) with check (true);

alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
