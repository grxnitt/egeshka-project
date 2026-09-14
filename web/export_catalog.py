"""Export public editorial catalog only; never reads users, reviews or secrets."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from egeshka_bot.db import SEED, TEACHERS
from egeshka_bot.scoring import BASE_WEIGHTS

schools = []
for row in SEED:
    schools.append({
        'name': row['name'], 'description': row['description'],
        'subjects': row['subjects'].split(','), 'price': row['price_text'],
        'strengths': row['strengths'], 'weaknesses': row['weaknesses'],
        'format': row['format_text'], 'url': row['official_url'],
        'criteria': {key: row[key] for key in BASE_WEIGHTS},
        'score': round(sum(row[key] * weight for key, weight in BASE_WEIGHTS.items()), 1),
    })
catalog = {'schools': schools, 'teachers': [
    {'school': t[0], 'name': t[1], 'subject': t[2], 'description': t[3], 'score': t[4], 'url': t[6]}
    for t in TEACHERS
]}
Path(__file__).with_name('catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
