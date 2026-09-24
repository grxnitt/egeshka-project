-- Remember the admin chat copies of a proof file so the bot can delete them after moderation.
alter table public.reviews add column if not exists proof_admin_messages text;
