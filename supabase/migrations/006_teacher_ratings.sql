alter table public.review_criterion_scores
  drop constraint if exists review_criterion_scores_criterion_check;

alter table public.review_criterion_scores
  add constraint review_criterion_scores_criterion_check check (criterion in (
    'teachers_score', 'practice_score', 'feedback_score', 'curator_score',
    'platform_score', 'workload_score', 'organization_score',
    'explanation', 'practice', 'atmosphere', 'structure', 'exam_value',
    'feedback', 'tempo', 'communication'
  ));

create table if not exists public.teacher_rating_snapshots (
  teacher_id integer primary key references public.teachers(id) on delete cascade,
  verified_review_count integer not null default 0 check (verified_review_count >= 0),
  student_score numeric(2,1) check (student_score between 1 and 5),
  explanation_score numeric(2,1) check (explanation_score between 1 and 5),
  practice_score numeric(2,1) check (practice_score between 1 and 5),
  atmosphere_score numeric(2,1) check (atmosphere_score between 1 and 5),
  structure_score numeric(2,1) check (structure_score between 1 and 5),
  exam_value_score numeric(2,1) check (exam_value_score between 1 and 5),
  is_preliminary boolean not null default true,
  calculated_at timestamp with time zone not null default now()
);

alter table public.teacher_rating_snapshots enable row level security;
grant select on public.teacher_rating_snapshots to anon, authenticated, egeshka_bot_app;

drop policy if exists teacher_rating_snapshots_public_read on public.teacher_rating_snapshots;
create policy teacher_rating_snapshots_public_read on public.teacher_rating_snapshots
  for select to anon, authenticated using (true);
drop policy if exists teacher_rating_snapshots_bot_read on public.teacher_rating_snapshots;
create policy teacher_rating_snapshots_bot_read on public.teacher_rating_snapshots
  for select to egeshka_bot_app using (true);

create or replace function public.refresh_teacher_rating_snapshots()
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  processed integer := 0;
begin
  with complete_reviews as (
    select r.id, r.teacher_id
    from public.reviews r
    join public.review_criterion_scores rcs on rcs.review_id = r.id
    where r.teacher_id is not null
      and r.moderation_status = 'approved'
      and r.verified
      and rcs.criterion in ('explanation', 'practice', 'atmosphere', 'structure', 'exam_value')
    group by r.id, r.teacher_id
    having count(distinct rcs.criterion) = 5
  ), aggregates as (
    select cr.teacher_id,
      count(distinct cr.id)::integer as review_count,
      avg(rcs.score)::numeric as student_score,
      avg(rcs.score) filter (where rcs.criterion = 'explanation')::numeric as explanation_score,
      avg(rcs.score) filter (where rcs.criterion = 'practice')::numeric as practice_score,
      avg(rcs.score) filter (where rcs.criterion = 'atmosphere')::numeric as atmosphere_score,
      avg(rcs.score) filter (where rcs.criterion = 'structure')::numeric as structure_score,
      avg(rcs.score) filter (where rcs.criterion = 'exam_value')::numeric as exam_value_score
    from complete_reviews cr
    join public.review_criterion_scores rcs on rcs.review_id = cr.id
    where rcs.criterion in ('explanation', 'practice', 'atmosphere', 'structure', 'exam_value')
    group by cr.teacher_id
  )
  insert into public.teacher_rating_snapshots (
    teacher_id, verified_review_count, student_score, explanation_score,
    practice_score, atmosphere_score, structure_score, exam_value_score,
    is_preliminary, calculated_at
  )
  select t.id,
    coalesce(a.review_count, 0),
    case when coalesce(a.review_count, 0) >= 3 then round(a.student_score, 1) end,
    case when coalesce(a.review_count, 0) >= 3 then round(a.explanation_score, 1) end,
    case when coalesce(a.review_count, 0) >= 3 then round(a.practice_score, 1) end,
    case when coalesce(a.review_count, 0) >= 3 then round(a.atmosphere_score, 1) end,
    case when coalesce(a.review_count, 0) >= 3 then round(a.structure_score, 1) end,
    case when coalesce(a.review_count, 0) >= 3 then round(a.exam_value_score, 1) end,
    coalesce(a.review_count, 0) < 10,
    now()
  from public.teachers t
  left join aggregates a on a.teacher_id = t.id
  where t.is_active
  on conflict (teacher_id) do update set
    verified_review_count = excluded.verified_review_count,
    student_score = excluded.student_score,
    explanation_score = excluded.explanation_score,
    practice_score = excluded.practice_score,
    atmosphere_score = excluded.atmosphere_score,
    structure_score = excluded.structure_score,
    exam_value_score = excluded.exam_value_score,
    is_preliminary = excluded.is_preliminary,
    calculated_at = excluded.calculated_at;

  get diagnostics processed = row_count;
  return processed;
end;
$$;

revoke all on function public.refresh_teacher_rating_snapshots() from public, anon, authenticated;

create or replace function public.refresh_all_rating_snapshots()
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  perform public.refresh_rating_snapshots();
  perform public.refresh_teacher_rating_snapshots();
end;
$$;

revoke all on function public.refresh_all_rating_snapshots() from public, anon, authenticated;

do $$
declare existing_job bigint;
begin
  select jobid into existing_job from cron.job where jobname = 'refresh-egeshka-ratings';
  if existing_job is not null then perform cron.unschedule(existing_job); end if;
  perform cron.schedule('refresh-egeshka-ratings', '15 0 * * *', 'select public.refresh_all_rating_snapshots();');
end $$;

select public.refresh_teacher_rating_snapshots();
