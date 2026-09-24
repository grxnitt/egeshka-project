-- Record when and to which text version a user agreed to personal data processing in the bot.
alter table public.users add column if not exists consent_at timestamp with time zone;
alter table public.users add column if not exists consent_version varchar(30);
