import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL = json.loads((ROOT / "content" / "school_legal.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / "web" / "catalog.json").read_text(encoding="utf-8"))


def test_every_school_has_a_legal_entry_and_valid_inn():
    for school in CATALOG["schools"]:
        info = LEGAL[school["reviewSlug"]]
        if info:
            assert info["entity"] and re.fullmatch(r"\d{10}|\d{12}", info["inn"])


def test_school_pages_carry_the_legal_note():
    for school in CATALOG["schools"]:
        page = (ROOT / "web" / "schools" / f"{school['reviewSlug']}.html").read_text(encoding="utf-8")
        assert 'class="sp-legal"' in page
        inn = LEGAL[school["reviewSlug"]].get("inn")
        if inn:
            assert f"ИНН {inn}" in page
