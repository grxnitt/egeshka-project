"""Rewrites content/db_ids.json from the live database over SSH (read only).
Run after adding a teacher or school to the database:  python3 scripts/refresh_db_ids.py
"""
import json
import subprocess
from pathlib import Path

KEY = Path.home() / ".ssh" / "egematch_vps"
QUERY = ("select 'T', t.id, s.name, t.name, t.subject from teachers t join schools s on s.id=t.school_id "
         "union all select 'S', id, name, '', '' from schools order by 1,2")
out = subprocess.run(["ssh", "-i", str(KEY), "root@95.163.231.156",
                      f"sudo -u postgres psql -d postgres -AtF'|' -c \"{QUERY}\""],
                     check=True, capture_output=True, text=True).stdout
schools, teachers = {}, []
for line in out.splitlines():
    if line.count("|") != 4:
        continue
    kind, ident, a, b, c = line.split("|")
    if kind == "S":
        schools[a] = int(ident)
    else:
        teachers.append([a, b, c, int(ident)])
target = Path(__file__).resolve().parents[1] / "content" / "db_ids.json"
note = json.loads(target.read_text(encoding="utf-8"))["_note"]
target.write_text(json.dumps({"_note": note, "schools": schools, "teachers": teachers}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(schools)} schools, {len(teachers)} teachers")
