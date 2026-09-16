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
