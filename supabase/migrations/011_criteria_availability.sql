-- Criteria a school does not offer (no curators, no manual checking, no platform ...).
-- schools.criteria_status is JSON text {criterion: "tier"|"none"}; a missing key means "offered".
-- A "none" criterion is left out of the editorial score and its weight is redistributed
-- over the criteria the school does offer, so its absence neither helps nor hurts.
-- Keys use the application names (organization_score is stored in price_quality_score).

alter table public.schools add column if not exists criteria_status text not null default '{}';

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
      (o.teachers_score,      case when o.st ->> 'teachers_score'     = 'none' then 0 else 0.24 end),
      (o.practice_score,      case when o.st ->> 'practice_score'     = 'none' then 0 else 0.16 end),
      (o.feedback_score,      case when o.st ->> 'feedback_score'     = 'none' then 0 else 0.14 end),
      (o.curator_score,       case when o.st ->> 'curator_score'      = 'none' then 0 else 0.14 end),
      (o.price_quality_score, case when o.st ->> 'organization_score' = 'none' then 0 else 0.14 end),
      (o.platform_score,      case when o.st ->> 'platform_score'     = 'none' then 0 else 0.10 end),
      (o.workload_score,      case when o.st ->> 'workload_score'     = 'none' then 0 else 0.08 end)
    ) as v(value, weight)
  ), editorial as (
    select school_id,
      (sum(value * weight) / nullif(sum(weight), 0))::numeric as editorial_score
    from weighted
    group by school_id
  ), verified_reviews as (
    select r.school_id, avg(r.score)::numeric as user_score, count(*)::integer as review_count
    from public.reviews r
    where r.teacher_id is null and r.moderation_status = 'approved' and r.verified
    group by r.school_id
  ), calculated as (
    select e.school_id,
      round(e.editorial_score, 1) as editorial_score,
      round(v.user_score, 1) as verified_user_score,
      coalesce(v.review_count, 0) as verified_review_count,
      case
        when coalesce(v.review_count, 0) < 3 then round(e.editorial_score, 1)
        else round(
          e.editorial_score * (1 - v.review_count::numeric / (v.review_count + 5)) +
          v.user_score * (v.review_count::numeric / (v.review_count + 5)),
          1
        )
      end as final_score,
      coalesce(v.review_count, 0) < 10 as is_preliminary
    from editorial e
    left join verified_reviews v using (school_id)
  )
  insert into public.rating_snapshots (
    school_id, editorial_score, verified_user_score, verified_review_count,
    final_score, is_preliminary, calculated_at
  )
  select school_id, editorial_score, verified_user_score, verified_review_count,
         final_score, is_preliminary, now()
  from calculated
  on conflict (school_id) do update set
    editorial_score = excluded.editorial_score,
    verified_user_score = excluded.verified_user_score,
    verified_review_count = excluded.verified_review_count,
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

select public.refresh_rating_snapshots();
select public.refresh_teacher_rating_snapshots();
