"""Apply checked-in SQL migrations to the configured Supabase database."""

import asyncio
from pathlib import Path

import asyncpg


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.supabase.local"
MIGRATIONS = ROOT / "supabase" / "migrations"


def load_connection_url() -> str:
    if not ENV_FILE.exists():
        raise SystemExit("Run scripts/configure_supabase.py first.")
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        key, separator, value = raw_line.partition("=")
        if separator and key == "SUPABASE_DATABASE_URL":
            return value.strip()
    raise SystemExit("SUPABASE_DATABASE_URL is missing from .env.supabase.local.")


async def apply() -> None:
    connection = await asyncpg.connect(
        load_connection_url(), command_timeout=120, statement_cache_size=0
    )
    try:
        await connection.execute(
            """
            create table if not exists public.schema_migrations (
              version text primary key,
              applied_at timestamp with time zone not null default now()
            );
            alter table public.schema_migrations enable row level security;
            revoke all on public.schema_migrations from anon, authenticated;
            """
        )
        applied = {
            row["version"]
            for row in await connection.fetch("select version from public.schema_migrations")
        }
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                print(f"skip  {path.name}")
                continue
            async with connection.transaction():
                await connection.execute(path.read_text(encoding="utf-8"))
                await connection.execute(
                    "insert into public.schema_migrations(version) values($1)", path.name
                )
            print(f"apply {path.name}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(apply())
