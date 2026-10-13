-- Reviews without a screenshot now count towards the ratings with a small weight (0.2 of a confirmed review).
-- A pile of them cannot outvote confirmed students: their total weight is capped at (confirmed reviews + 1),
-- the same rule the bot uses. The rating starts from an effective weight of 3 (3 confirmed, or fewer plus unconfirmed)
-- and stays preliminary below 10. Everything else (editorial weights, the blend n / (n + 5)) is unchanged.

alter table public.rating_snapshots
  add column if not exists unverified_review_count integer not null default 0 check (unverified_review_count >= 0);
alter table public.teacher_rating_snapshots
  add column if not exists unverified_review_count integer not null default 0 check (unverified_review_count >= 0);

create or replace function public.refresh_rating_snapshots()
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  processed integer := 0;
  run_id bigint;
begin
  insert into public.rating_runs default values returning id into run_id;

  with offered as (
    select s.*, coalesce(nullif(s.criteria_status, ''), '{}')::jsonb as st
    from public.schools s
    where s.is_active
  ), weighted as (
    -- weight 0 for a criterion the school does not offer; the rest are renormalised below
    select o.id as school_id, v.value, v.weight
    from offered o
    cross join lateral (values
      (o.teachers_score,      case when o.st ->> 'teachers_score'     = 'none' then 0 else 0.20 end),
      (o.practice_score,      case when o.st ->> 'practice_score'     = 'none' then 0 else 0.16 end),
      (o.feedback_score,      case when o.st ->> 'feedback_score'     = 'none' then 0 else 0.14 end),
      (o.curator_score,       case when o.st ->> 'curator_score'      = 'none' then 0 else 0.14 end),
      (o.price_quality_score, case when o.st ->> 'organization_score' = 'none' then 0 else 0.14 end),
      (o.platform_score,      case when o.st ->> 'platform_score'     = 'none' then 0 else 0.14 end),
      (o.workload_score,      case when o.st ->> 'workload_score'     = 'none' then 0 else 0.08 end)
    ) as v(value, weight)
  ), editorial as (
    select school_id,
      (sum(value * weight) / nullif(sum(weight), 0))::numeric as editorial_score
    from weighted
    group by school_id
  ), per_school as (
    select r.school_id,
      count(*) filter (where r.verified)::integer as v_count,
      count(*) filter (where not r.verified)::integer as u_count,
      avg(r.score) filter (where r.verified)::numeric as v_avg,
      avg(r.score) filter (where not r.verified)::numeric as u_avg
    from public.reviews r
    where r.teacher_id is null and r.moderation_status = 'approved'
    group by r.school_id
  ), students as (
    select p.*, least(0.2 * p.u_count, p.v_count + 1.0) as u_weight
    from per_school p
  ), student_part as (
    select s.school_id, s.v_count, s.u_count,
      (s.v_count + s.u_weight) as n_eff,
      ((coalesce(s.v_avg, 0) * s.v_count + coalesce(s.u_avg, 0) * s.u_weight)
        / nullif(s.v_count + s.u_weight, 0))::numeric as user_score
    from students s
  ), calculated as (
    select e.school_id,
      round(e.editorial_score, 1) as editorial_score,
      round(v.user_score, 1) as verified_user_score,
      coalesce(v.v_count, 0) as verified_review_count,
      coalesce(v.u_count, 0) as unverified_review_count,
      case
        when coalesce(v.n_eff, 0) < 3 then round(e.editorial_score, 1)
        else round(
          e.editorial_score * (1 - v.n_eff / (v.n_eff + 5)) +
          v.user_score * (v.n_eff / (v.n_eff + 5)),
          1
        )
      end as final_score,
      coalesce(v.n_eff, 0) < 10 as is_preliminary
    from editorial e
    left join student_part v using (school_id)
  )
  insert into public.rating_snapshots (
    school_id, editorial_score, verified_user_score, verified_review_count, unverified_review_count,
    final_score, is_preliminary, calculated_at
  )
  select school_id, editorial_score, verified_user_score, verified_review_count, unverified_review_count,
         final_score, is_preliminary, now()
  from calculated
  on conflict (school_id) do update set
    editorial_score = excluded.editorial_score,
    verified_user_score = excluded.verified_user_score,
    verified_review_count = excluded.verified_review_count,
    unverified_review_count = excluded.unverified_review_count,
    final_score = excluded.final_score,
    is_preliminary = excluded.is_preliminary,
    calculated_at = excluded.calculated_at;

  get diagnostics processed = row_count;
  update public.rating_runs
    set finished_at = now(), status = 'succeeded', schools_processed = processed
    where id = run_id;
  return processed;
exception when others then
  update public.rating_runs
    set finished_at = now(), status = 'failed', error_message = sqlerrm
    where id = run_id;
  raise;
end;
$$;

revoke all on function public.refresh_rating_snapshots() from public, anon, authenticated;

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
    select r.id, r.teacher_id, r.verified
    from public.reviews r
    join public.review_criterion_scores rcs on rcs.review_id = r.id
    where r.teacher_id is not null
      and r.moderation_status = 'approved'
      and rcs.criterion in ('explanation', 'practice', 'atmosphere', 'structure', 'exam_value')
    group by r.id, r.teacher_id, r.verified
    having count(distinct rcs.criterion) = 5
  ), counts as (
    select teacher_id,
      count(*) filter (where verified)::integer as v_count,
      count(*) filter (where not verified)::integer as u_count
    from complete_reviews
    group by teacher_id
  ), weights as (
    -- a confirmed review weighs 1; the unconfirmed ones share 0.2 each, at most (confirmed + 1) in total
    select cr.id, cr.teacher_id,
      case when cr.verified then 1.0
           else least(0.2 * c.u_count, c.v_count + 1.0) / c.u_count end as w,
      c.v_count, c.u_count
    from complete_reviews cr
    join counts c on c.teacher_id = cr.teacher_id
  ), aggregates as (
    select w.teacher_id,
      max(w.v_count) as v_count,
      max(w.u_count) as u_count,
      (select sum(x.w) from weights x where x.teacher_id = w.teacher_id) as n_eff,
      sum(rcs.score::numeric * w.w) / nullif(sum(w.w), 0) as student_score,
      sum(rcs.score::numeric * w.w) filter (where rcs.criterion = 'explanation') / nullif(sum(w.w) filter (where rcs.criterion = 'explanation'), 0) as explanation_score,
      sum(rcs.score::numeric * w.w) filter (where rcs.criterion = 'practice') / nullif(sum(w.w) filter (where rcs.criterion = 'practice'), 0) as practice_score,
      sum(rcs.score::numeric * w.w) filter (where rcs.criterion = 'atmosphere') / nullif(sum(w.w) filter (where rcs.criterion = 'atmosphere'), 0) as atmosphere_score,
      sum(rcs.score::numeric * w.w) filter (where rcs.criterion = 'structure') / nullif(sum(w.w) filter (where rcs.criterion = 'structure'), 0) as structure_score,
      sum(rcs.score::numeric * w.w) filter (where rcs.criterion = 'exam_value') / nullif(sum(w.w) filter (where rcs.criterion = 'exam_value'), 0) as exam_value_score
    from weights w
    join public.review_criterion_scores rcs on rcs.review_id = w.id
    where rcs.criterion in ('explanation', 'practice', 'atmosphere', 'structure', 'exam_value')
    group by w.teacher_id
  )
  insert into public.teacher_rating_snapshots (
    teacher_id, verified_review_count, unverified_review_count, student_score, explanation_score,
    practice_score, atmosphere_score, structure_score, exam_value_score,
    is_preliminary, calculated_at
  )
  select t.id,
    coalesce(a.v_count, 0),
    coalesce(a.u_count, 0),
    case when coalesce(a.n_eff, 0) >= 3 then round(a.student_score, 1) end,
    case when coalesce(a.n_eff, 0) >= 3 then round(a.explanation_score, 1) end,
    case when coalesce(a.n_eff, 0) >= 3 then round(a.practice_score, 1) end,
    case when coalesce(a.n_eff, 0) >= 3 then round(a.atmosphere_score, 1) end,
    case when coalesce(a.n_eff, 0) >= 3 then round(a.structure_score, 1) end,
    case when coalesce(a.n_eff, 0) >= 3 then round(a.exam_value_score, 1) end,
    coalesce(a.n_eff, 0) < 10,
    now()
  from public.teachers t
  left join aggregates a on a.teacher_id = t.id
  where t.is_active
  on conflict (teacher_id) do update set
    verified_review_count = excluded.verified_review_count,
    unverified_review_count = excluded.unverified_review_count,
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

select public.refresh_rating_snapshots();
select public.refresh_teacher_rating_snapshots();
