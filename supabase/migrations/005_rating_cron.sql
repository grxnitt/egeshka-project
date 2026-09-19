create extension if not exists pg_cron;

do $$
declare
  existing_job bigint;
begin
  select jobid into existing_job
  from cron.job
  where jobname = 'refresh-egeshka-ratings';

  if existing_job is not null then
    perform cron.unschedule(existing_job);
  end if;

  perform cron.schedule(
    'refresh-egeshka-ratings',
    '15 0 * * *',
    'select public.refresh_rating_snapshots();'
  );
end $$;
