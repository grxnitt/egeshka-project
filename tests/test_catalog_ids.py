import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_ids_are_the_live_database_ids():
    """The site and the ratings address schools and teachers by id; adding a teacher in the middle of the list must not
    renumber the rest (that once shifted 50 teachers). Ids come from content/db_ids.json, refreshed from the database."""
    catalog = json.loads((ROOT / "web" / "catalog.json").read_text(encoding="utf-8"))
    saved = json.loads((ROOT / "content" / "db_ids.json").read_text(encoding="utf-8"))
    teachers = {(school, name, subject): ident for school, name, subject, ident in saved["teachers"]}
    assert [t["id"] for t in catalog["teachers"]] == [teachers[(t["school"], t["name"], t["subject"])] for t in catalog["teachers"]]
    assert all(saved["schools"][s["name"]] == s["id"] for s in catalog["schools"])
    assert len({t["id"] for t in catalog["teachers"]}) == len(catalog["teachers"])
