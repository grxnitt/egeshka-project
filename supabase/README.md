# Supabase setup

Configure and apply migrations from the repository root:

```bash
python3 scripts/configure_supabase.py
python3 scripts/apply_supabase_migrations.py
```

The first command hides the pasted URI and writes it to a Git-ignored file with
permissions `600`. Migrations create the catalog, private review data, public
rating snapshots, RLS policies and the daily rating refresh function.

Do not paste database passwords or service-role keys into Git or chat.

For the long-running VPS bot, use the Supabase **Session pooler** connection
string and replace the SQLAlchemy prefix with `postgresql+asyncpg://`.

After the data migration:

1. Run `select public.refresh_all_rating_snapshots();` once.
2. Enable Supabase Cron.
3. Schedule the function using the commented statement in migration 003.
4. Verify that `anon` can select active catalog rows and rating snapshots but
   cannot select `users`, `reviews`, `events` or proof fields.
