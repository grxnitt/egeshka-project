-- Per-article view counter, shown directly on the article page next to the
-- read-time meta. One row per slug, incremented via a security-definer
-- function so anon can bump the count without write access to the table
-- itself — same pattern as refresh_rating_snapshots() in 003.

create table if not exists public.article_views (
  slug text primary key,
  views integer not null default 0,
  updated_at timestamptz not null default now()
);

alter table public.article_views enable row level security;

revoke all on public.article_views from anon, authenticated;
grant select on public.article_views to anon, authenticated;

drop policy if exists article_views_public_read on public.article_views;
create policy article_views_public_read on public.article_views for select to anon, authenticated using (true);

create or replace function public.increment_article_view(p_slug text)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  new_count integer;
begin
  insert into public.article_views (slug, views, updated_at)
  values (p_slug, 1, now())
  on conflict (slug) do update
    set views = article_views.views + 1, updated_at = now()
  returning views into new_count;
  return new_count;
end;
$$;

revoke all on function public.increment_article_view(text) from public;
grant execute on function public.increment_article_view(text) to anon, authenticated;
