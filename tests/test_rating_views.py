from types import SimpleNamespace

from egeshka_bot.bot import (
    CRITERIA,
    TEACHER_CRITERIA,
    comparison_section_text,
    comparison_text,
    school_total_score,
    teacher_criteria_text,
)


def school(name="Школа"):
    values = {
        "name": name,
        "price_text": "от 4 000 руб.",
        "format_text": "эфиры и записи",
        "support_text": "куратор",
        "homework_text": "домашки",
        "strengths": "практика",
        "weaknesses": "темп подходит не всем",
    }
    values.update({field: 8.0 for field, _, _ in CRITERIA})
    return SimpleNamespace(**values)


def test_school_total_is_preliminary_without_student_reviews():
    total, preliminary = school_total_score(school())
    assert total == 8.0
    assert preliminary is True


def test_comparison_summary_is_short_and_sections_keep_all_criteria():
    left, right = school("Левая"), school("Правая")
    summary = comparison_text(left, right)
    details = comparison_section_text(left, right, "criteria")
    assert "Итоговый рейтинг" in summary
    assert "Цена и тарифы" not in summary
    assert all(label in details for _, label, _ in CRITERIA)


def test_teacher_criteria_only_lists_submitted_aspects():
    stats = {field: (None, 0) for field, _ in TEACHER_CRITERIA}
    stats["explanation"] = (4.5, 2)
    result = teacher_criteria_text(stats)
    assert "Объяснение материала" in result
    assert "Практика и разбор ошибок" not in result
