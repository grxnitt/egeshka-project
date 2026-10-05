"""Typical students and what the quiz must do for them. If a weight change breaks one of these,
the change is wrong or the expectation needs a conscious update."""
from types import SimpleNamespace

from egeshka_bot.db import SEED
from egeshka_bot.scoring import QuizProfile, school_match

PEERS = [SimpleNamespace(**{k: v for k, v in school.items() if k.isidentifier()}) for school in SEED]


def profile(**kw):
    base = dict(subject="русский", budget=None, current_level="middle", target=70, curator_need=2, workload=2,
                control_need=2, priorities=(), lesson_format="any", teacher_need=2)
    base.update(kw)
    return QuizProfile(**base)


def ranking(p, teacher_scores=None):
    out = []
    for school in PEERS:
        match = school_match(school, p, (teacher_scores or {}).get(school.name), peers=PEERS)
        if match:
            out.append((match["score"], school.name, match))
    return sorted(out, key=lambda item: -item[0])


def test_scores_are_spread_and_bounded():
    scores = [score for score, _, _ in ranking(profile())]
    assert all(5 <= s <= 97 for s in scores)
    assert max(scores) - min(scores) >= 20  # the quiz actually separates schools


def test_tight_budget_pushes_expensive_schools_down():
    rich = {name: score for score, name, _ in ranking(profile())}
    poor = {name: score for score, name, _ in ranking(profile(budget=3000))}
    expensive = [s.name for s in PEERS if (s.monthly_price_from or 0) > 6000 and s.name in poor]
    assert expensive and all(poor[name] < rich[name] - 10 for name in expensive)


def test_individual_format_keeps_only_schools_that_have_it_on_top():
    top = ranking(profile(lesson_format="individual"))[:3]
    assert all("занятия один на один" in " ".join(m["pros"]) for _, _, m in top)


def test_needing_a_curator_penalises_schools_without_one():
    for score, name, match in ranking(profile(curator_need=4))[:3]:
        assert not any("нет куратора" in con for con in match["cons"]), name


def test_subject_teacher_moves_the_match_by_bounded_points_only():
    base = {name: score for score, name, _ in ranking(profile(teacher_need=3))}
    school = PEERS[0].name
    teachers = PEERS[0].teachers_score
    strong = {name: score for score, name, _ in ranking(profile(teacher_need=3), {school: 10})}
    weak = {name: score for score, name, _ in ranking(profile(teacher_need=3), {school: teachers - 0.9})}
    assert 0 < strong[school] - base[school] <= 12
    assert 0 < base[school] - weak[school] <= 9  # slightly below the school average is a small minus, not a collapse


def test_every_result_explains_what_moved_it():
    for _, _, match in ranking(profile(budget=4000, curator_need=3, priorities=("practice",)))[:3]:
        assert match["factors"] and all(isinstance(points, int) for _, points in match["factors"])
