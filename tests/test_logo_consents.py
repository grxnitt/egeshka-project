import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSENTS = json.loads((ROOT / "content" / "logo_consents.json").read_text(encoding="utf-8"))
JS = (ROOT / "web" / "school-content.js").read_text(encoding="utf-8")


def test_a_logo_is_shown_only_for_schools_with_a_written_consent():
    shown = set(re.findall(r"'([^']+)'", re.search(r"LOGO_CONSENTS = new Set\(\[(.*?)\]\)", JS, re.S).group(1)))
    consented = {item["school"] for key, item in CONSENTS.items() if not key.startswith("_")}
    assert shown == consented
    for key, item in CONSENTS.items():
        if not key.startswith("_"):
            assert (ROOT / item["file"]).exists() and item["granted"]


def test_logos_stay_switched_off_for_everyone_else():
    assert "const LOGOS_ALLOWED = false;" in JS
