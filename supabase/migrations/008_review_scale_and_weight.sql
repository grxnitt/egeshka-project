-- Move student review scores from a 1-5 scale to 1-10, matching the
-- editorial criteria (already 0-10). This lets teachers be rated the same
-- way schools are rated, and removes the awkward /2 + /2 blending the old
-- 1-5 scale required.
--
-- Also lowers how many confirmed reviews it takes for the student part to
-- meaningfully influence a school's score: the weight curve moves from
-- review_count / (review_count + 10) to review_count / (review_count + 5),
-- so a handful of reviews already matter, not only several dozen. Small
-- schools were the ones this hurt most, since they simply have fewer
-- students who could ever leave a review.
--
-- Assumes no production review data exists yet (confirmed before writing
-- this migration) - if that ever changes, existing 1-5 scores would need
-- to be doubled before these constraints are tightened.

alter table public.reviews
  drop constraint if exists reviews_score_check;
alter table public.reviews
  add constraint reviews_score_check check (score between 1 and 10 and score = trunc(score));

alter table public.review_criterion_scores
  drop constraint if exists review_criterion_scores_score_check;
alter table public.review_criterion_scores
  add constraint review_criterion_scores_score_check check (score between 1 and 10 and score = trunc(score));

-- numeric(2,1) only fits up to 9.9 - widen every score column that can now
-- reach 10.0 before tightening its check constraint.
alter table public.rating_snapshots
  alter column verified_user_score type numeric(3,1);
alter table public.rating_snapshots
  drop constraint if exists rating_snapshots_verified_user_score_check;
alter table public.rating_snapshots
  add constraint rating_snapshots_verified_user_score_check check (verified_user_score between 1 and 10);

alter table public.teacher_rating_snapshots
  alter column student_score type numeric(3,1),
  alter column explanation_score type numeric(3,1),
  alter column practice_score type numeric(3,1),
  alter column atmosphere_score type numeric(3,1),
  alter column structure_score type numeric(3,1),
  alter column exam_value_score type numeric(3,1);

alter table public.teacher_rating_snapshots
  drop constraint if exists teacher_rating_snapshots_student_score_check;
alter table public.teacher_rating_snapshots
  add constraint teacher_rating_snapshots_student_score_check check (student_score between 1 and 10);
alter table public.teacher_rating_snapshots
  drop constraint if exists teacher_rating_snapshots_explanation_score_check;
alter table public.teacher_rating_snapshots
  add constraint teacher_rating_snapshots_explanation_score_check check (explanation_score between 1 and 10);
alter table public.teacher_rating_snapshots
  drop constraint if exists teacher_rating_snapshots_practice_score_check;
alter table public.teacher_rating_snapshots
  add constraint teacher_rating_snapshots_practice_score_check check (practice_score between 1 and 10);
alter table public.teacher_rating_snapshots
  drop constraint if exists teacher_rating_snapshots_atmosphere_score_check;
alter table public.teacher_rating_snapshots
  add constraint teacher_rating_snapshots_atmosphere_score_check check (atmosphere_score between 1 and 10);
alter table public.teacher_rating_snapshots
  drop constraint if exists teacher_rating_snapshots_structure_score_check;
alter table public.teacher_rating_snapshots
  add constraint teacher_rating_snapshots_structure_score_check check (structure_score between 1 and 10);
alter table public.teacher_rating_snapshots
  drop constraint if exists teacher_rating_snapshots_exam_value_score_check;
alter table public.teacher_rating_snapshots
  add constraint teacher_rating_snapshots_exam_value_score_check check (exam_value_score between 1 and 10);

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
