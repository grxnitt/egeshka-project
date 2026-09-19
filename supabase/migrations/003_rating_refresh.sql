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

  with editorial as (
    select s.id as school_id,
      (
        s.teachers_score * 0.24 + s.practice_score * 0.16 +
        s.feedback_score * 0.14 + s.curator_score * 0.14 +
        s.price_quality_score * 0.14 + s.platform_score * 0.10 +
        s.workload_score * 0.08
      )::numeric as editorial_score
    from public.schools s
    where s.is_active
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
          e.editorial_score / 2 +
          ((e.editorial_score / 2) * (1 - v.review_count::numeric / (v.review_count + 10)) +
           v.user_score * (v.review_count::numeric / (v.review_count + 10))),
          1
        )
      end as final_score,
      coalesce(v.review_count, 0) < 3 as is_preliminary
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

-- Schedule after enabling the Supabase Cron integration:
-- select cron.schedule(
--   'refresh-egeshka-ratings',
--   '15 0 * * *', -- 03:15 Europe/Moscow while Moscow is UTC+3
--   $$select public.refresh_rating_snapshots();$$
-- );
