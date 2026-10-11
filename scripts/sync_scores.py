"""Pull the editorial scores edited in the console into the repository files (catalog.json and the bot's SEED),
so the static pages, the bot and the tests agree with what visitors see.

  .venv/bin/python scripts/sync_scores.py            # show what would change
  .venv/bin/python scripts/sync_scores.py --write    # apply, then rebuild: scripts/build_school_pages.py

Run it after a monthly review, before the rebuild. Statuses (yes / tier / none) are only reported: change
CRITERIA_STATUS in egeshka_bot/db.py by hand if the console changed one.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://data.egematch.ru/rest/v1"
KEYS = ("teachers_score", "practice_score", "feedback_score", "curator_score", "platform_score", "workload_score", "organization_score")
WEIGHTS = {"teachers_score": .20, "practice_score": .16, "feedback_score": .14, "curator_score": .14, "platform_score": .14,
           "workload_score": .08, "organization_score": .14}


def fetch(path):
    with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", headers={"apikey": "public"}), timeout=20) as response:
        return json.load(response)


def editorial(scores, status):
    total = weight = 0.0
    for key in KEYS:
        if status.get(key, "yes") != "none":
            total += scores[key] * WEIGHTS[key]
            weight += WEIGHTS[key]
    return round(total / weight, 1)


def main(write: bool):
    live = {row["school_id"]: row for row in fetch("school_scores_public?select=*")}
    catalog_path = ROOT / "web" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    db_path = ROOT / "egeshka_bot" / "db.py"
    db_text = db_path.read_text(encoding="utf-8")
    changed = []
    for school in catalog["schools"]:
        row = live.get(school["id"])
        if not row:
            continue
        new = {key: round(float(row[key]), 1) for key in KEYS}
        status = json.loads(row.get("criteria_status") or "{}")
        if status != (school.get("criteriaStatus") or {}):
            print(f"! {school['name']}: статусы критериев в консоли отличаются от каталога ({status}); поправь CRITERIA_STATUS в db.py вручную")
        diffs = {key: (school["criteria"][key], new[key]) for key in KEYS if school["criteria"].get(key) != new[key] and new[key] is not None}
        if not diffs:
            continue
        changed.append(school["name"])
        print(f"{school['name']}: " + ", ".join(f"{key} {old} -> {value}" for key, (old, value) in diffs.items()))
        school["criteria"].update(new)
        school["score"] = editorial({**school["criteria"]}, status)
        block = re.search(r'("name": "%s",.*?)(?=\n    \{\n        "name":|\Z)' % re.escape(school["name"]), db_text, re.S)
        if not block:
            print(f"! {school['name']}: блок не найден в db.py")
            continue
        text = block.group(1)
        for key, value in new.items():
            text = re.sub(r'("%s": )[0-9.]+' % key, r"\g<1>%s" % value, text, count=1)
        db_text = db_text.replace(block.group(1), text, 1)
    if not changed:
        print("Изменений нет: каталог совпадает с консолью.")
        return
    if write:
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        db_path.write_text(db_text, encoding="utf-8")
        print(f"\nЗаписано: {len(changed)} школ. Теперь: scripts/build_school_pages.py, тесты, коммит.")
    else:
        print(f"\nБыло бы изменено школ: {len(changed)}. Запусти с --write, чтобы применить.")


if __name__ == "__main__":
    main("--write" in sys.argv)
