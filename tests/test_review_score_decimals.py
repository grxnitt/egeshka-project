from decimal import Decimal
from pathlib import Path

from reviews_service import validation

ROOT = Path(__file__).resolve().parents[1]


class School:
    id = 1
    criteria_status = ""


def overall(scores):
    data = {"scores": scores, "positive": "Нормальные занятия, понятно объясняют материал.", "negative": "", "period": "2025/26"}
    return validation.clean_review(data, School, None)["score"]


def test_overall_keeps_one_decimal_instead_of_rounding_to_a_whole_number():
    full = dict(teachers_score=9, practice_score=8, feedback_score=8, curator_score=6, platform_score=9, workload_score=8, organization_score=8)
    assert overall(full) == 8.0 and overall({**full, "curator_score": 5}) == 7.9   # 55/7 = 7.857 -> 7.9
    assert overall({**full, "teachers_score": 10}) == 8.1                          # 57/7 = 8.14 -> 8.1


def test_halves_round_up_not_to_even():
    # 2 criteria would be needed for a clean .x5, so check the helper path with a known case: 8.25 -> 8.3
    assert float(Decimal("8.25").quantize(Decimal("0.1"), rounding=validation.ROUND_HALF_UP)) == 8.3


def test_the_database_no_longer_insists_on_whole_review_scores():
    sql = (ROOT / "supabase" / "migrations" / "023_review_score_decimals.sql").read_text(encoding="utf-8")
    assert "trunc" not in sql.split("add constraint")[1] and "score >= 1 and score <= 10" in sql
