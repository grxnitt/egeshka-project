import json
import re
from pathlib import Path

WEB = Path("web")


def catalog():
    return json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))


def school(name):
    return next(s for s in catalog()["schools"] if s["name"] == name)


def test_noo_lists_the_ege_chemistry_teachers_not_the_oge_one():
    names = [t["name"] for t in catalog()["teachers"] if t["school"] == "НОО"]
    assert names == ["Татьяна Бумстади", "Зумруд Омарова", "Дмитрий Петров"]
    assert not (WEB / "teachers" / "noo-tatyana-krinitsyna.html").exists()
    assert all("chemogegod" not in t["url"] for t in catalog()["teachers"])


def test_noo_course_length_and_prices_match_the_course_page():
    noo = school("НОО")
    assert noo["monthlyPriceFrom"] == 5690 and "5 690" in noo["price"] and "6 390" in noo["price"]
    assert "десять месяцев" not in noo["format"] and "8 месяцев" in noo["format"]
    assert "почти каждый десятый" not in json.dumps(noo, ensure_ascii=False)


def test_egehub_prices_tariffs_and_basic_math():
    hub = school("ЕГЭХАБ")
    assert "математика базовая" in hub["subjects"]
    for figure in ("3 450", "4 450", "5 450", "3 105"):
        assert figure in hub["price"]
    comparison = (WEB / "comparison.js").read_text(encoding="utf-8")
    assert "31 050" in comparison and "«Ванта»" in comparison


def test_new_school_copy_does_not_expose_internal_provenance():
    text = (WEB / "comparison.js").read_text(encoding="utf-8") + (WEB / "school-content.js").read_text(encoding="utf-8")
    blob = json.dumps([s for s in catalog()["schools"] if s["name"] in {"ЕГЭХАБ", "Школа Пифагора", "НОО"}], ensure_ascii=False)
    assert "пользовател" not in blob.lower()
    for name in ("'Школа Пифагора'",):
        line = next(l for l in text.splitlines() if name in l)
        assert "пользовател" not in line.lower()


def test_new_schools_have_bot_course_cards():
    import sys
    sys.path.insert(0, ".")
    from egeshka_bot import db

    for name in ("ЕГЭХАБ", "Школа Пифагора", "НОО"):
        assert name in db.COURSE_CONFIG, name
