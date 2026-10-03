from types import SimpleNamespace
from egeshka_bot.scoring import QuizProfile, school_score


def profile(subject="русский", budget=5000):
    return QuizProfile(
        subject=subject,
        budget=budget,
        current_level="middle",
        target=80,
        curator_need=3,
        workload=2,
        control_need=3,
        priorities=("teacher",),
    )


def test_subject_is_hard_filter():
    school = SimpleNamespace(subjects="русский,математика", monthly_price_from=4000, teachers_score=8, practice_score=8, feedback_score=8, curator_score=8, platform_score=8, workload_score=8, organization_score=8)
    score, reasons = school_score(school, profile(subject="химия"))
    assert score == -1
    assert "предмету" in reasons[0]


def test_budget_affects_score():
    school = SimpleNamespace(subjects="русский", monthly_price_from=7000, teachers_score=8, practice_score=8, feedback_score=8, curator_score=8, platform_score=8, workload_score=8, organization_score=8)
    under, _ = school_score(school, profile(budget=8000))
    over, _ = school_score(school, profile(budget=3000))
    assert under > over


def test_price_priority_uses_real_budget_not_organization_score():
    affordable = SimpleNamespace(subjects="русский", monthly_price_from=3000, teachers_score=8, practice_score=8, feedback_score=8, curator_score=8, platform_score=8, workload_score=8, organization_score=6)
    expensive = SimpleNamespace(subjects="русский", monthly_price_from=9000, teachers_score=8, practice_score=8, feedback_score=8, curator_score=8, platform_score=8, workload_score=8, organization_score=10)
    budget_profile = profile(budget=4000)
    budget_profile.priorities = ("price",)
    affordable_score, _ = school_score(affordable, budget_profile)
    expensive_score, _ = school_score(expensive, budget_profile)
    assert affordable_score > expensive_score


def _school(**values):
    row = dict(subjects="русский", monthly_price_from=0, teachers_score=8, practice_score=8, feedback_score=8,
               curator_score=8, platform_score=8, workload_score=8, organization_score=8)
    row.update(values)
    return SimpleNamespace(**row)


def test_beginner_level_favours_curator_and_feedback_over_teachers_and_practice():
    # Same school, only current_level differs. Against peers it is strong on curator/feedback and weak on
    # teachers/practice, so a beginner (curator/feedback x1.5) should match it better than an advanced student.
    supportive = _school(teachers_score=7, practice_score=7, feedback_score=9, curator_score=9)
    peers = [supportive, _school(), _school(teachers_score=9, practice_score=9, feedback_score=7, curator_score=7)]
    beginner = profile()
    beginner.current_level = "low"
    advanced = profile()
    advanced.current_level = "high"
    assert school_score(supportive, beginner, peers=peers)[0] > school_score(supportive, advanced, peers=peers)[0]


def test_subject_teacher_score_pulls_the_match_toward_that_teacher():
    school = _school(teachers_score=7.0)
    peers = [school, _school(teachers_score=8.0)]
    baseline, _ = school_score(school, profile(), peers=peers)
    with_strong_teacher, reasons_strong = school_score(school, profile(), subject_teacher_score=9.5, peers=peers)
    with_weak_teacher, reasons_weak = school_score(school, profile(), subject_teacher_score=4.0, peers=peers)
    assert with_strong_teacher > baseline > with_weak_teacher
    assert any("именно по этому предмету" in r for r in reasons_strong)
    assert any("по этому предмету" in r for r in reasons_weak)


def test_subject_teacher_score_never_changes_a_school_without_teachers_score_weight():
    # A school missing the teachers criterion entirely (status "none") must ignore
    # a subject_teacher_score rather than crash or silently add a phantom criterion.
    school = SimpleNamespace(
        subjects="русский", monthly_price_from=0,
        practice_score=8, feedback_score=8, curator_score=8, platform_score=8, workload_score=8, organization_score=8,
        teachers_score=0, criteria_status='{"teachers_score": "none"}',
    )
    without, _ = school_score(school, profile())
    with_teacher, _ = school_score(school, profile(), subject_teacher_score=9.9)
    assert without == with_teacher
