-- The console shows the computed scores next to the editorial ones and checks that the nightly recalculation ran.
grant select on public.rating_snapshots, public.teacher_rating_snapshots to reviews_admin;
drop policy if exists rating_snapshots_admin_read on public.rating_snapshots;
create policy rating_snapshots_admin_read on public.rating_snapshots for select to reviews_admin using (true);
drop policy if exists teacher_rating_snapshots_admin_read on public.teacher_rating_snapshots;
create policy teacher_rating_snapshots_admin_read on public.teacher_rating_snapshots for select to reviews_admin using (true);
