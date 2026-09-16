from egeshka_bot.db import SEED, TEACHERS
from egeshka_bot.scoring import BASE_WEIGHTS


def test_new_schools_have_complete_catalog_entries():
    schools = {row["name"]: row for row in SEED}
    for name in ("PARTA", "Skysmart", "Школково"):
        assert name in schools
        assert all(key in schools[name] for key in BASE_WEIGHTS)
        assert schools[name]["official_url"].startswith("https://")


def test_price_quality_was_replaced_everywhere_in_seed():
    assert "organization_score" in BASE_WEIGHTS
    assert "price_quality_score" not in BASE_WEIGHTS
    assert all("organization_score" in row and "price_quality_score" not in row for row in SEED)


def test_new_school_teacher_cards_are_available():
    counts = {name: sum(teacher[0] == name for teacher in TEACHERS) for name in ("PARTA", "Skysmart", "Школково")}
    assert counts == {"PARTA": 8, "Skysmart": 3, "Школково": 3}


def test_teacher_subjects_are_listed_by_their_school():
    school_subjects = {row["name"]: set(row["subjects"].split(",")) for row in SEED}
    missing = {
        (school, subject)
        for school, _name, subject, *_rest in TEACHERS
        if subject.lower().replace(" язык", "") not in school_subjects[school]
    }
    assert missing == set()


def test_researched_teacher_cards_use_factual_descriptions():
    researched = [row for row in TEACHERS if row[0] in {"ЕГЭLand", "PARTA", "Школково"}]
    banned = ("официальной линейке", "официальном каталоге", "официальной команде", "профиль подтверждён")

    assert all(len(description) >= 90 for _school, _name, _subject, description, *_rest in researched)
    assert all(not any(fragment in description.lower() for fragment in banned) for _school, _name, _subject, description, *_rest in researched)


def test_ege_land_physics_card_tracks_current_teacher():
    physics_names = {name for school, name, subject, *_rest in TEACHERS if school == "ЕГЭLand" and subject == "Физика"}

    assert physics_names == {"Даня Физик"}
