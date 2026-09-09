from dataclasses import dataclass
from typing import Optional, Tuple


BASE_WEIGHTS = {
    "teachers_score": 0.24,
    "practice_score": 0.16,
    "feedback_score": 0.14,
    "curator_score": 0.14,
    "platform_score": 0.10,
    "workload_score": 0.08,
    "price_quality_score": 0.14,
}


PRIORITY_TO_FIELD = {
    "teacher": "teachers_score",
    "practice": "practice_score",
    "curator": "curator_score",
    "platform": "platform_score",
    "price": "price_quality_score",
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


def school_score(school, profile: QuizProfile) -> Tuple[float, list]:
    if profile.subject.lower() not in _offered_subjects(school):
        return -1, ["не готовит по выбранному предмету"]

    score = 0.0
    reasons = []
    for key, weight in BASE_WEIGHTS.items():
        score += float(getattr(school, key, 0)) * weight * 10

    if profile.budget is not None:
        if school.monthly_price_from <= 0:
            pass
        elif school.monthly_price_from <= profile.budget:
            score += 8
            reasons.append("входит в бюджет")
        else:
            penalty = min(18, (school.monthly_price_from - profile.budget) / max(profile.budget, 1) * 12)
            score -= penalty
            reasons.append("может быть выше бюджета")

    if profile.curator_need >= 3:
        score += float(school.curator_score) * 0.8
        if school.curator_score >= 8:
            reasons.append("сильное сопровождение")

    if profile.control_need >= 3:
        score += (float(school.feedback_score) + float(school.practice_score)) * 0.35
        reasons.append("подходит для контроля и дедлайнов")

    if profile.workload <= 2 and school.workload_score >= 8.5:
        score -= 3
        reasons.append("темп может быть интенсивным")
    elif profile.workload >= 3 and school.workload_score >= 8:
        score += 4
        reasons.append("подходит под высокий темп")

    if profile.target >= 85:
        score += (float(school.teachers_score) + float(school.practice_score)) * 0.35
        reasons.append("сильнее для высокой цели")

    if profile.current_level == "low":
        score += float(school.curator_score) * 0.25
        reasons.append("есть запас поддержки для старта")

    for priority in profile.priorities:
        field = PRIORITY_TO_FIELD.get(priority)
        if field:
            score += float(getattr(school, field, 0)) * 0.7

    return round(max(0, min(100, score)), 1), reasons[:3]
