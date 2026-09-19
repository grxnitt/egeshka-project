"""Save Supabase connection settings locally without printing secrets."""

from getpass import getpass
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env.supabase.local"


def main() -> None:
    print("Paste the Supabase Session pooler URI. Input is hidden.")
    uri = getpass("Session pooler URI: ").strip()
    # Terminal paste can occasionally repeat the clipboard contents. Keep one
    # complete URI instead of persisting a syntactically valid but unusable path.
    marker = "postgresql://"
    if uri.count(marker) > 1:
        uri = marker + uri.rsplit(marker, 1)[1]
    if not uri.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Expected a postgresql:// URI from Supabase Connect.")

    if "[YOUR-PASSWORD]" in uri or "YOUR-PASSWORD" in uri:
        password = getpass("Database password: ")
        if not password:
            raise SystemExit("Database password cannot be empty.")
        uri = uri.replace("[YOUR-PASSWORD]", quote(password, safe=""))
        uri = uri.replace("YOUR-PASSWORD", quote(password, safe=""))

    parsed = urlsplit(uri)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    hostname = parsed.hostname or ""
    port = parsed.port
    # The local network closes Supabase's session-pooler port before TLS. The
    # transaction-pooler port is IPv4-compatible and works for migrations.
    if hostname.endswith(".pooler.supabase.com") and port == 5432:
        credentials = parsed.netloc.rsplit("@", 1)[0]
        netloc = f"{credentials}@{hostname}:6543"
    else:
        netloc = parsed.netloc
    uri = urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), parsed.fragment))

    async_query = {key: value for key, value in query.items() if key != "sslmode"}
    async_query["prepared_statement_cache_size"] = "0"
    async_uri = urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(async_query), parsed.fragment))
    async_uri = async_uri.replace("postgres://", "postgresql+asyncpg://", 1)
    async_uri = async_uri.replace("postgresql://", "postgresql+asyncpg://", 1)
    TARGET.write_text(
        f"SUPABASE_DATABASE_URL={uri}\nDATABASE_URL={async_uri}\n",
        encoding="utf-8",
    )
    TARGET.chmod(0o600)
    print(f"Saved securely to {TARGET}")


if __name__ == "__main__":
    main()
