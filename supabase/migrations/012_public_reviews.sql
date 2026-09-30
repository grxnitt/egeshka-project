-- Public read-only view of individual approved reviews, for a "browse every review"
-- page on the site and an "all reviews" link from the bot's school/teacher cards.
--
-- No personal data: there is no public registration yet (only Telegram), so this view
-- deliberately excludes user_id and the proof_* columns (screenshot file ids, consent
-- flag) — it exposes exactly what a reader should see: the score, the per-criterion
-- breakdown, the free text, whether the review is verified, and when it was left.
-- Runs as the view owner, so it reads through reviews' RLS (which otherwise only lets
-- egeshka_bot_app touch that table) without granting anon anything on the base table.

create or replace view public.public_reviews as
select
  r.id,
  r.school_id,
  r.teacher_id,
  r.criterion,
  r.criteria_json,
  r.score,
  r.text_positive,
  r.text_negative,
  r.verified,
  r.created_at
from public.reviews r
where r.moderation_status = 'approved';

grant select on public.public_reviews to anon, authenticated;
