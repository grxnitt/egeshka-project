from dataclasses import dataclass
from typing import Optional, Tuple


BASE_WEIGHTS = {
    "teachers_score": 0.24,
    "practice_score": 0.16,
    "feedback_score": 0.14,
    "curator_score": 0.14,
    "platform_score": 0.10,
    "workload_score": 0.08,
    "organization_score": 0.14,
}

CRITERION_LABELS = {
    "teachers_score": "преподаватели",
    "practice_score": "практика",
    "feedback_score": "проверка работ",
    "curator_score": "кураторы",
    "platform_score": "платформа",
    "workload_score": "нагрузка и темп",
    "organization_score": "организация обучения",
}

PRIORITY_TO_FIELD = {
    "teacher": "teachers_score",
    "practice": "practice_score",
    "curator": "curator_score",
    "platform": "platform_score",
}


@dataclass
class QuizProfile:
    subject: str
    budget: Optional[int]
    current_level: str
    target: int
    curator_need: int
    workload: int
    control_need: int
    priorities: Tuple[str, ...]


def _offered_subjects(school):
    return {s.strip().lower() for s in school.subjects.split(",") if s.strip()}


def _personalized_weights(profile: QuizProfile) -> dict:
    """Reweight the editorial criteria toward what this student's answers say
    matters most to them, then renormalize so weights still sum to 1.

    This replaces a flat point-bonus system: instead of adding arbitrary
    points on top of an already-0-10 score (which used to blow past 100
    for almost every well-rated school), a student's answers shift *how
    much each criterion counts*, and the match is the resulting weighted
    average of that school's own (already 0-10) criteria.
    """
    weights = dict(BASE_WEIGHTS)

    for priority in profile.priorities:
        field = PRIORITY_TO_FIELD.get(priority)
        if field:
            weights[field] += 0.10

    if profile.curator_need >= 3:
        weights["curator_score"] += 0.06
    if profile.curator_need >= 4:
        weights["curator_score"] += 0.04

    if profile.control_need >= 3:
        weights["feedback_score"] += 0.05
        weights["organization_score"] += 0.03
    if profile.control_need >= 4:
        weights["feedback_score"] += 0.04

    if profile.current_level == "low":
        weights["curator_score"] += 0.06
        weights["feedback_score"] += 0.03
    elif profile.current_level == "high":
        weights["teachers_score"] += 0.04
        weights["practice_score"] += 0.04

    if profile.target >= 90:
        weights["teachers_score"] += 0.06
        weights["practice_score"] += 0.06
    elif profile.target >= 85:
        weights["teachers_score"] += 0.03
        weights["practice_score"] += 0.03

    if profile.workload in (1, 4):
        weights["workload_score"] += 0.05

    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def _budget_fit(school, profile: QuizProfile) -> float:
    if profile.budget is None or profile.subject == "математика базовая":
        return 0.0
    price = float(getattr(school, "monthly_price_from", 0) or 0)
    if price <= 0:
        return 0.0
    # A student who picked "price" as a priority feels budget fit more
    # strongly than someone for whom it is just a filter.
    amplify = 1.6 if "price" in profile.priorities else 1.0
    if price <= profile.budget:
        return 0.4 * amplify
    over_ratio = (price - profile.budget) / max(profile.budget, 1)
    return -min(1.2 * amplify, over_ratio * 0.8 * amplify)


def school_score(school, profile: QuizProfile) -> Tuple[float, list]:
    if profile.subject.lower() not in _offered_subjects(school):
        return -1, ["не готовит по выбранному предмету"]

    weights = _personalized_weights(profile)
    fit = sum(float(getattr(school, key, 0)) * weight for key, weight in weights.items())
    fit += _budget_fit(school, profile)
    fit = max(0.0, min(10.0, fit))

    reasons = []
    budget_delta = _budget_fit(school, profile)
    if budget_delta > 0:
        reasons.append("входит в бюджет")
    elif budget_delta < 0:
        reasons.append("может быть выше бюджета")

    boosted = sorted(
        (key for key in BASE_WEIGHTS if weights[key] > BASE_WEIGHTS[key] + 0.01),
        key=lambda key: weights[key],
        reverse=True,
    )
    for key in boosted:
        label = CRITERION_LABELS[key]
        value = float(getattr(school, key, 0))
        if value >= 8.5:
            reasons.append(f"сильные {label} ({value:.1f})")
        elif value <= 7.5:
            reasons.append(f"стоит проверить {label} ({value:.1f})")

    if not reasons:
        reasons.append("ровное совпадение по всем критериям")

    return round(fit / 10 * 100, 1), reasons[:3]
