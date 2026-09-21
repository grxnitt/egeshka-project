-- The bot exposes a user-initiated deletion flow. Keep DELETE unavailable to
-- public API roles and grant it only to the dedicated bot role.
grant delete on public.users, public.reviews, public.review_criterion_scores, public.events
  to egeshka_bot_app;

-- Refresh public rating snapshots immediately after a user's verified reviews
-- are removed. The function is SECURITY DEFINER and exposes no row data.
grant execute on function public.refresh_all_rating_snapshots() to egeshka_bot_app;
