"""Copy the current SQLite catalog to Supabase and verify row counts."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import asyncpg


ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = ROOT / "egeshka.db"
ENV_FILE = ROOT / ".env.supabase.local"
TABLES = ("schools", "teachers", "courses", "users", "reviews", "events")
DATETIME_COLUMNS = {
    "schools": {"verified_at"},
    "courses": {"verified_at"},
    "users": {"created_at"},
    "reviews": {"created_at", "proof_delete_after"},
    "events": {"created_at"},
}
BOOLEAN_COLUMNS = {
    "schools": {"is_active"},
    "teachers": {"is_active"},
    "courses": {"is_active"},
    "reviews": {"verified", "proof_consent"},
}
LEGACY_CRITERIA = {"price_quality_score": "organization_score"}


def database_url() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("SUPABASE_DATABASE_URL="):
            return line.split("=", 1)[1]
    raise SystemExit("SUPABASE_DATABASE_URL is missing.")


def parse_datetime(value):
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def sqlite_rows():
    source = sqlite3.connect(SQLITE_PATH)
    source.row_factory = sqlite3.Row
    try:
        result = {}
        for table in TABLES:
            rows = []
            for raw in source.execute(f"select * from {table} order by id"):
                row = dict(raw)
                for column in DATETIME_COLUMNS.get(table, set()):
                    row[column] = parse_datetime(row.get(column))
                for column in BOOLEAN_COLUMNS.get(table, set()):
                    row[column] = bool(row.get(column))
                rows.append(row)
            result[table] = rows
        return result
    finally:
        source.close()


async def upsert_rows(connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    assignments = ", ".join(f'"{c}" = excluded."{c}"' for c in columns if c != "id")
    placeholders = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    column_sql = ", ".join(f'"{column}"' for column in columns)
    query = (
        f'insert into public."{table}" ({column_sql}) values ({placeholders}) '
        f"on conflict (id) do update set {assignments}"
    )
    await connection.executemany(query, [tuple(row[column] for column in columns) for row in rows])


async def migrate(apply_changes: bool) -> None:
    rows = sqlite_rows()
    source_counts = {table: len(items) for table, items in rows.items()}
    print("SQLite:", json.dumps(source_counts, ensure_ascii=False, sort_keys=True))
    if not apply_changes:
        print("Dry run only. Re-run with --apply to write to Supabase.")
        return

    connection = await asyncpg.connect(
        database_url(), command_timeout=120, statement_cache_size=0
    )
    try:
        async with connection.transaction():
            for table in TABLES:
                await upsert_rows(connection, table, rows[table])

            for review in rows["reviews"]:
                scores = {}
                if review.get("criteria_json"):
                    try:
                        scores.update(json.loads(review["criteria_json"]))
                    except (TypeError, json.JSONDecodeError):
                        pass
                if review.get("criterion"):
                    scores[review["criterion"]] = review["score"]
                for criterion, score in scores.items():
                    criterion = LEGACY_CRITERIA.get(criterion, criterion)
                    await connection.execute(
                        """
                        insert into public.review_criterion_scores(review_id, criterion, score)
                        values($1, $2, $3)
                        on conflict (review_id, criterion) do update set score = excluded.score
                        """,
                        review["id"], criterion, float(score),
                    )

            for table in TABLES:
                maximum = await connection.fetchval(f'select max(id) from public."{table}"')
                if maximum:
                    await connection.execute(
                        "select setval(pg_get_serial_sequence($1, 'id'), $2, true)",
                        f"public.{table}", maximum,
                    )

            target_counts = {
                table: await connection.fetchval(f'select count(*) from public."{table}"')
                for table in TABLES
            }
            if target_counts != source_counts:
                raise RuntimeError(
                    f"Count mismatch; rolling back. source={source_counts}, target={target_counts}"
                )

        processed = await connection.fetchval("select public.refresh_rating_snapshots()")
        print("Supabase:", json.dumps(target_counts, ensure_ascii=False, sort_keys=True))
        print(f"Verified exact counts. Rating snapshots refreshed for {processed} schools.")
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write to Supabase")
    arguments = parser.parse_args()
    asyncio.run(migrate(arguments.apply))
