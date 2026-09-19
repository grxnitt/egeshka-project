"""Configure the public Supabase client used by the static website."""

from getpass import getpass
import json
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV = ROOT / ".env.supabase.public.local"
WEB_CONFIG = ROOT / "web" / "supabase-config.js"


def main() -> None:
    project_url = input("Project URL: ").strip().rstrip("/")
    if project_url.endswith("/rest/v1"):
        project_url = project_url.removesuffix("/rest/v1")
    publishable_key = getpass("Publishable key (input hidden): ").strip()
    marker = "sb_publishable_"
    if publishable_key.count(marker) > 1:
        publishable_key = marker + publishable_key.rsplit(marker, 1)[1]

    parsed = urlsplit(project_url)
    if parsed.scheme != "https" or parsed.path not in ("", "/") or not parsed.hostname or not parsed.hostname.endswith(".supabase.co"):
        raise SystemExit("Expected an https://<project-ref>.supabase.co URL.")
    if not publishable_key.startswith("sb_publishable_"):
        raise SystemExit("Expected a key starting with sb_publishable_.")

    LOCAL_ENV.write_text(
        f"SUPABASE_URL={project_url}\nSUPABASE_PUBLISHABLE_KEY={publishable_key}\n",
        encoding="utf-8",
    )
    LOCAL_ENV.chmod(0o600)
    WEB_CONFIG.write_text(
        "// Public browser credentials. Access is restricted by Supabase RLS.\n"
        f"window.EGESHKA_SUPABASE = {json.dumps({'url': project_url, 'publishableKey': publishable_key}, ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    print(f"Saved public web config to {WEB_CONFIG}")


if __name__ == "__main__":
    main()
