from types import SimpleNamespace

from egeshka_bot.bot import (
    CRITERIA,
    TEACHER_CRITERIA,
    comparison_section_text,
    comparison_text,
    school_total_score,
    teacher_criteria_text,
    teacher_rating_from_criteria,
    teacher_rating_text,
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


def test_school_total_waits_for_three_verified_reviews_and_uses_confidence_weight():
    assert school_total_score(school(), 2.0, 2) == (8.0, True)
    total, preliminary = school_total_score(school(), 2.0, 10)
    assert total == 7.0
    assert preliminary is False


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


def test_teacher_rating_is_student_only_average_of_five_criteria():
    stats = {field: (score, 4) for (field, _), score in zip(TEACHER_CRITERIA, (5, 4, 4.5, 3.5, 4))}

    assert teacher_rating_from_criteria(stats) == (4.2, 4)
    assert "4,2/5*" in teacher_rating_text(stats)
    assert "/10" not in teacher_rating_text(stats)


def test_teacher_rating_waits_for_three_complete_verified_reviews():
    stats = {field: (5.0, 2) for field, _ in TEACHER_CRITERIA}

    assert "пока не сформирована" in teacher_rating_text(stats)


def test_teacher_criteria_are_the_universal_five():
    assert [label for _field, label in TEACHER_CRITERIA] == [
        "Объяснение материала",
        "Практика и разбор ошибок",
        "Атмосфера и вовлечённость",
        "Структура и темп занятий",
        "Польза для экзамена",
    ]
