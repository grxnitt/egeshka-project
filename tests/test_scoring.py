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


def test_beginner_level_favours_curator_and_feedback_over_teachers_and_practice():
    # Same school, only current_level differs: a beginner should score a
    # curator/feedback-heavy school higher than an advanced student would,
    # and an advanced student should score a teachers/practice-heavy school higher.
    supportive = SimpleNamespace(subjects="русский", monthly_price_from=0, teachers_score=7, practice_score=7, feedback_score=9, curator_score=9, platform_score=7, workload_score=7, organization_score=7)
    beginner = profile()
    beginner.current_level = "low"
    advanced = profile()
    advanced.current_level = "high"
    low_score, _ = school_score(supportive, beginner)
    high_score, _ = school_score(supportive, advanced)
    assert low_score > high_score


def test_subject_teacher_score_pulls_the_match_toward_that_teacher():
    school = SimpleNamespace(subjects="русский", monthly_price_from=0, teachers_score=7.0, practice_score=8, feedback_score=8, curator_score=8, platform_score=8, workload_score=8, organization_score=8)
    baseline, _ = school_score(school, profile())
    with_strong_teacher, reasons_strong = school_score(school, profile(), subject_teacher_score=9.5)
    with_weak_teacher, reasons_weak = school_score(school, profile(), subject_teacher_score=4.0)
    assert with_strong_teacher > baseline > with_weak_teacher
    assert any("по этому предмету" in r or "именно по этому предмету" in r for r in reasons_strong)
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
