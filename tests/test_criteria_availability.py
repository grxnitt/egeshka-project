import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from egeshka_bot import db
from egeshka_bot.bot import (
    CRITERIA,
    criterion_buttons,
    criterion_score_keyboard,
    school_criteria,
    school_criteria_simple_text,
    school_criteria_text,
    school_total_score,
)
from egeshka_bot.models import School
from egeshka_bot.scoring import (
    BASE_WEIGHTS,
    QuizProfile,
    _need_penalty,
    applicable_criteria,
    editorial_score,
    effective_weights,
    is_rated,
    school_score,
)

WEB = Path("web")


def school(values=8.0, status=None, **extra):
    row = {key: values for key in BASE_WEIGHTS}
    row.update(extra)
    row.update(name="Школа", subjects="русский", monthly_price_from=5000, criteria_status=json.dumps(status or {}))
    return SimpleNamespace(**row)


def profile(**kw):
    base = dict(subject="русский", budget=5000, current_level="middle", target=80, curator_need=1, workload=2, control_need=1, priorities=())
    base.update(kw)
    return QuizProfile(**base)


def test_missing_criterion_neither_helps_nor_hurts_the_total():
    full = school(teachers_score=9, practice_score=8, feedback_score=8, curator_score=8, platform_score=7, workload_score=8, organization_score=9)
    # without the curator the weights are renormalised over the six criteria that remain
    without = school(teachers_score=9, practice_score=8, feedback_score=8, curator_score=0, platform_score=7, workload_score=8, organization_score=9,
                     status={"curator_score": "none"})
    others = {k: v for k, v in effective_weights(without).items()}
    expected = sum(getattr(without, k) * w for k, w in others.items())
    assert editorial_score(without) == pytest.approx(expected)
    assert sum(others.values()) == pytest.approx(1.0)
    assert "curator_score" not in others
    # a school whose curator equals the average of the rest scores exactly the same with or without it
    avg_rest = expected
    same = school(teachers_score=9, practice_score=8, feedback_score=8, curator_score=avg_rest, platform_score=7, workload_score=8, organization_score=9)
    assert editorial_score(same) == pytest.approx(editorial_score(without))
    assert editorial_score(full) != editorial_score(without)


def test_tier_criterion_stays_in_the_score():
    tier = school(status={"curator_score": "tier"}, curator_score=6)
    plain = school(curator_score=6)
    assert editorial_score(tier) == pytest.approx(editorial_score(plain))
    assert "curator_score" in applicable_criteria(tier)


def test_a_school_needs_five_of_seven_criteria_including_teachers():
    assert is_rated(school(status={"curator_score": "none", "feedback_score": "none"}))          # 5 left
    assert not is_rated(school(status={"curator_score": "none", "feedback_score": "none", "platform_score": "none"}))  # 4 left
    assert not is_rated(school(status={"teachers_score": "none"}))


def test_match_penalty_is_half_a_point_for_none_and_two_tenths_for_tier():
    needs_curator = profile(curator_need=4)
    delta, reasons = _need_penalty(school(status={"curator_score": "none"}), needs_curator)
    assert delta == -0.5 and reasons == ["нет куратора, а он тебе нужен"]
    delta, reasons = _need_penalty(school(status={"curator_score": "tier"}), needs_curator)
    assert delta == -0.2 and reasons == ["куратор — только на старших тарифах"]
    # not needed (or offered everywhere): no penalty at all
    assert _need_penalty(school(status={"curator_score": "none"}), profile(curator_need=1)) == (0.0, [])
    assert _need_penalty(school(), needs_curator) == (0.0, [])
    assert _need_penalty(school(status={"feedback_score": "none"}), profile(control_need=4))[0] == -0.5


def test_quiz_ignores_a_missing_criterion_when_it_is_not_needed():
    a = school(teachers_score=9, curator_score=0, status={"curator_score": "none"})
    b = school(teachers_score=9, curator_score=0)   # same numbers, but the zero is not marked as missing
    relaxed = profile(curator_need=1)
    assert school_score(a, relaxed)[0] > school_score(b, relaxed)[0]
    needy = profile(curator_need=4)
    assert "нет куратора, а он тебе нужен" in school_score(a, needy)[1]


def test_bot_skips_missing_criteria_in_texts_and_review_keyboards():
    pif = school(status={"curator_score": "none", "feedback_score": "none"})
    labels = [label for _, label, _ in school_criteria(pif)]
    assert "Кураторы" not in labels and "Проверка и обратная связь" not in labels and len(labels) == 5
    assert sum(w for _, _, w in school_criteria(pif)) == pytest.approx(1.0)
    text = school_criteria_text(pif)
    assert "Кураторы: не предусмотрено" in text and "Преподаватели:" in text
    assert "не предусмотрено" in school_criteria_simple_text(pif)
    callbacks = [b.callback_data for row in criterion_buttons(1, pif).inline_keyboard for b in row]
    assert not any(c and c.endswith(":curator_score") for c in callbacks)
    assert any(c and c.endswith(":teachers_score") for c in callbacks)
    # tariff-dependent criteria can be skipped in the full review, others cannot
    skippable = [b.callback_data for row in criterion_score_keyboard(skippable=True).inline_keyboard for b in row]
    assert "criterion_skip" in skippable
    assert "criterion_skip" not in [b.callback_data for row in criterion_score_keyboard().inline_keyboard for b in row]
    total, _ = school_total_score(pif)
    assert total == pytest.approx(round(editorial_score(pif), 1))


def test_seed_statuses_are_valid_and_every_school_is_rated():
    assert set(db.CRITERIA_STATUS) <= {s["name"] for s in db.SEED}
    for name, status in db.CRITERIA_STATUS.items():
        assert set(status) <= set(BASE_WEIGHTS) and set(status.values()) <= {"tier", "none"}, name
    for row in db.SEED:
        assert is_rated(row), row["name"]
        for key, value in json.loads(row["criteria_status"]).items():
            if value == "none":
                assert row[key] == 0.0, (row["name"], key)   # placeholder that never reaches a score
    assert json.loads(next(s for s in db.SEED if s["name"] == "Школа Пифагора")["criteria_status"]) == {
        "curator_score": "none", "feedback_score": "none"}


def test_catalog_carries_statuses_null_criteria_and_renormalised_scores():
    schools = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))["schools"]
    by_name = {s["name"]: s for s in schools}
    pif = by_name["Школа Пифагора"]
    assert pif["criteria"]["curator_score"] is None and pif["criteria"]["feedback_score"] is None
    assert pif["criteriaStatus"] == {"curator_score": "none", "feedback_score": "none"}
    assert by_name["Умскул"]["criteriaStatus"] == {} and by_name["StudyCats"]["criteriaStatus"] == {"curator_score": "tier"}
    rows = {r["name"]: r for r in db.SEED}
    for s in schools:
        assert s["score"] == round(editorial_score(rows[s["name"]]), 1), s["name"]


def test_supabase_migration_uses_the_same_weights_and_statuses():
    sql = (Path("supabase/migrations") / "011_criteria_availability.sql").read_text(encoding="utf-8")
    assert "criteria_status" in sql and "nullif(sum(weight), 0)" in sql
    weights = sorted(float(x) for x in re.findall(r"= 'none' then 0 else ([0-9.]+) end", sql))
    assert weights == sorted(BASE_WEIGHTS.values())


def test_seeding_stores_the_statuses_in_the_database(tmp_path):
    async def run():
        engine, sessions = await db.init_db(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        try:
            async with sessions() as session:
                row = (await session.execute(select(School).where(School.name == "Школа Пифагора"))).scalar_one()
                return json.loads(row.criteria_status), editorial_score(row)
        finally:
            await engine.dispose()

    status, score = asyncio.run(run())
    assert status == {"curator_score": "none", "feedback_score": "none"} and 7.9 < score < 8.1


def test_site_shows_missing_criteria_and_mirrors_the_quiz_rules():
    page = (WEB / "schools" / "shkolapifagora.html").read_text(encoding="utf-8")
    assert page.count("Не предусмотрено") == 2 and "В оценку не входит: проверка работ, кураторы" in page
    assert "зависит от тарифа" in (WEB / "schools" / "studycats.html").read_text(encoding="utf-8")
    assert "Не предусмотрено" in (WEB / "compare.js").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "offeredKeys" in app and "delta-=status==='none'?.5:.2" in app
    method = (WEB / "methodology.html").read_text(encoding="utf-8")
    assert "Если чего-то нет в школе" in method and "не меньше пяти критериев из семи" in method
