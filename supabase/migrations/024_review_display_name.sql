-- An author may sign a review with a first name or a nickname (optional; a review without one is shown as anonymous).
-- Checked on the server: 2-30 characters, at most two words, no links, e-mails, phone numbers or impersonation.
alter table public.reviews add column if not exists display_name varchar(40);

create or replace view public.public_reviews as
select
  r.id, r.school_id, r.teacher_id, r.criterion, r.criteria_json, r.score, r.text_positive, r.text_negative,
  r.verified, r.created_at, r.study_period, r.source, r.display_name
from public.reviews r
where r.moderation_status = 'approved';
grant select on public.public_reviews to anon, authenticated;
