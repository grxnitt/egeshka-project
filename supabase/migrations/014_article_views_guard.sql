-- increment_article_view used to accept any slug from anyone, so the public
-- key could create unlimited junk rows. Only well-formed slugs are counted,
-- and new slugs stop being accepted once the table holds 500 articles.
create or replace function public.increment_article_view(p_slug text)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  new_count integer;
begin
  if p_slug is null or p_slug !~ '^[a-z0-9]+(-[a-z0-9]+)*$' or length(p_slug) > 80 then
    return null;
  end if;

  update public.article_views
     set views = views + 1, updated_at = now()
   where slug = p_slug
  returning views into new_count;

  if new_count is null then
    if (select count(*) from public.article_views) >= 500 then
      return null;
    end if;
    insert into public.article_views (slug, views, updated_at)
    values (p_slug, 1, now())
    on conflict (slug) do update
      set views = article_views.views + 1, updated_at = now()
    returning views into new_count;
  end if;

  return new_count;
end;
$$;

revoke all on function public.increment_article_view(text) from public;
grant execute on function public.increment_article_view(text) to anon, authenticated;

-- Drop junk rows that don't look like article slugs.
delete from public.article_views where slug !~ '^[a-z0-9]+(-[a-z0-9]+)*$' or length(slug) > 80;
