from pathlib import Path

import pytest

from reviews_service import validation
from reviews_service.validation import ReviewError, clean_display_name

ROOT = Path(__file__).resolve().parents[1]


def test_no_name_means_anonymous():
    assert clean_display_name(None) is None and clean_display_name("") is None and clean_display_name("   ") is None


@pytest.mark.parametrize("name", ["Маша", "ege_ivan", "Иван К.", "Anna-Maria", "  Саша   "])
def test_first_names_and_nicknames_are_accepted(name):
    assert clean_display_name(name) == " ".join(name.split())


@pytest.mark.parametrize("name", [
    "А", "x" * 31,                         # too short, too long
    "Иванов Иван Иванович",                # a full name
    "ivan.petrov@mail.ru", "vk.com/ivan", "https://t.me/x",   # contact details and links
    "+7 999 123 45 67", "89991234567",     # phone numbers
    "ЕГЭ Мэтч", "Администрация", "модератор", "Поддержка",    # impersonation
    "<b>Маша</b>", "Маша!!!",              # markup and noise
])
def test_names_that_identify_or_impersonate_are_refused(name):
    with pytest.raises(ReviewError):
        clean_display_name(name)


def test_a_review_carries_the_signature_into_the_payload():
    class School:
        id, criteria_status = 1, ""
    data = {"scores": dict(teachers_score=8, practice_score=8, feedback_score=8, curator_score=8, platform_score=8,
                           workload_score=8, organization_score=8),
            "positive": "Нормальные занятия, понятно объясняют материал и быстро проверяют домашние задания.", "negative": "", "period": "2025/26", "display_name": "Маша"}
    assert validation.clean_review(data, School, None)["display_name"] == "Маша"
    assert validation.clean_review({**data, "display_name": None}, School, None)["display_name"] is None


def test_the_view_and_the_site_know_the_new_column():
    sql = (ROOT / "supabase" / "migrations" / "024_review_display_name.sql").read_text(encoding="utf-8")
    assert "add column if not exists display_name" in sql and "r.display_name" in sql
    assert "display_name" in (ROOT / "web" / "supabase-client.js").read_text(encoding="utf-8")
    form = (ROOT / "web" / "review.html").read_text(encoding="utf-8")
    assert 'data-author="anon"' in form and 'data-author="named"' in form and 'id="rf-name"' in form
