-- A review's overall score is the mean of its criteria with one decimal (8.1), not a rounded whole number.
-- The column is already double precision; only the "whole numbers only" check goes. Criterion scores stay whole (1-10).
alter table public.reviews drop constraint if exists reviews_score_check;
alter table public.reviews add constraint reviews_score_check check (score >= 1 and score <= 10);
