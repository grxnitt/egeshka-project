alter table public.review_criterion_scores
  drop constraint if exists review_criterion_scores_criterion_check;

alter table public.review_criterion_scores
  add constraint review_criterion_scores_criterion_check check (criterion in (
    'teachers_score', 'practice_score', 'feedback_score', 'curator_score',
    'platform_score', 'workload_score', 'organization_score',
    'explanation', 'practice', 'feedback', 'tempo', 'communication'
  ));
