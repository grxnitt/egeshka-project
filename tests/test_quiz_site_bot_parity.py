"""The site quiz (web/app.js) and the bot quiz (egeshka_bot/scoring.py) must recommend the same schools.
They are two implementations of one formula, so their tables are compared here number for number."""
import re
from pathlib import Path

from egeshka_bot import scoring

WEB = Path("web")
APP = (WEB / "app.js").read_text(encoding="utf-8")


def _js_object(name, text):
    start = text.index(f"const {name}=") + len(f"const {name}=")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            return text[start:i + 1]


def test_lesson_formats_are_the_same_on_site_and_bot():
    js = (WEB / "school-content.js").read_text(encoding="utf-8")
    site = {}
    for name, lessons, unsure in re.findall(r"'([^']+)':\{priceFrom:[^,]+,lessons:\[([^\]]*)\](?:,unsure:\[([^\]]*)\])?\}", js):
        site[name] = (tuple(re.findall(r"'(\w+)'", lessons)), tuple(re.findall(r"'(\w+)'", unsure)))
    assert site == scoring.LESSON_FORMATS


def test_penalties_are_the_same():
    js = _js_object("PENALTY", APP)
    names = {"formatMissing": "format_missing", "recordedMissing": "recorded_missing", "formatUnsure": "format_unsure",
             "needNone": "need_none", "needTier": "need_tier", "overBudgetMax": "over_budget_max", "priceUnknown": "price_unknown"}
    site = {names[k]: float(v) for k, v in re.findall(r"(\w+):([\d.]+)", js)}
    assert site == {k: float(v) for k, v in scoring.PENALTY.items()}


def test_importance_multipliers_are_the_same():
    js = _js_object("IMPORTANCE", APP)
    for answer, table in scoring.IMPORTANCE.items():
        block = re.search(answer + r":\{(.*?)\}\}", js).group(1) + "}"
        for value, multipliers in table.items():
            entry = re.search(r"(?:^|,)'?" + re.escape(str(value)) + r"'?:\{([^}]*)\}", block).group(1)
            assert dict((k, float(v)) for k, v in re.findall(r"(\w+):([\d.]+)", entry)) == {k: float(v) for k, v in multipliers.items()}, (answer, value)
    assert f"const PRIORITY_MULTIPLIER={scoring.PRIORITY_MULTIPLIER};" in APP
    assert f"Math.min({scoring.MAX_IMPORTANCE},m[key])" in APP


def test_bot_asks_the_same_eight_questions_as_the_site():
    from egeshka_bot.bot import QUIZ_STEPS
    site_keys = re.findall(r"\{key:'(\w+)',questionNumber:\d", APP)
    bot_keys = [key if key != "priority" else "priority1" for key, _, _ in QUIZ_STEPS]
    bot_keys[bot_keys.index("level"):bot_keys.index("target") + 1] = ["goal"]  # one screen on the site, two steps in the bot
    assert bot_keys == site_keys


def test_bot_reads_new_and_old_site_links():
    from egeshka_bot.bot import profile_from_payload
    new = profile_from_payload("q_0_8000_middle_70_3_2_practice_none_3_individual_3")
    assert new.lesson_format == "individual" and new.teacher_need == 3 and new.curator_need == 3
    old = profile_from_payload("q_0_8000_middle_70_3_2_practice_none_3")
    assert old.lesson_format == "any" and old.teacher_need == 2


def test_subject_teacher_points_and_factor_labels_are_the_same():
    js = _js_object("SUBJECT_TEACHER", APP)
    assert f"perPoint:{scoring.SUBJECT_TEACHER['per_point']},min:{scoring.SUBJECT_TEACHER['min']},max:{scoring.SUBJECT_TEACHER['max']}" in js
    assert "need:{'1':.5,'2':1,'3':1.5}" in js and scoring.SUBJECT_TEACHER["need"] == {1: 0.5, 2: 1, 3: 1.5}
    labels = dict(re.findall(r"(\w+):'([^']+)'", _js_object("FACTOR_LABELS", APP)))
    assert labels == scoring.FACTOR_LABELS


def test_months_to_exam_counts_payments_until_may():
    from datetime import date
    assert scoring.months_to_exam(date(2026, 10, 5)) == 8
    assert scoring.months_to_exam(date(2027, 1, 10)) == 5
    assert scoring.months_to_exam(date(2027, 5, 20)) == 1
    assert scoring.months_to_exam(date(2027, 6, 10)) == 1
    assert scoring.months_to_exam(date(2027, 7, 1)) == 11
    assert "examYear=m>=7?today.getFullYear()+1:today.getFullYear()" in APP


def test_price_bonus_is_the_same():
    assert f"const PRICE_BONUS_MAX={scoring.PRICE_BONUS_MAX};" in APP


def test_more_matches_threshold_is_the_same():
    from egeshka_bot.bot import MORE_MIN_SCORE
    assert f"const MORE_MIN_SCORE={MORE_MIN_SCORE};" in APP


def test_big_gap_is_the_same():
    from egeshka_bot.scoring import QuizProfile, big_gap
    p = lambda subject, level, target: QuizProfile(subject, None, level, target, 2, 2, 2, (), "any", 2)
    assert big_gap(p("русский", "low", 90)) and big_gap(p("русский", "low", 80)) and big_gap(p("русский", "middle", 90))
    assert not big_gap(p("русский", "low", 70)) and not big_gap(p("русский", "high", 90))
    assert big_gap(p("математика базовая", "low", 5)) and not big_gap(p("математика базовая", "middle", 5))
    assert "(a.level==='low'&&Number(a.target)>=80)||(a.level==='middle'&&a.target==='90')" in APP
