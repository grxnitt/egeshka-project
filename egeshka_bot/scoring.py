import json
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

# Some schools simply do not offer a criterion (no curators, no manual checking,
# no platform). Each school records that per criterion:
#   yes  - part of every tariff (default)
#   tier - only on some tariffs
#   none - not offered at all: it is not scored, not asked from students and its
#          weight is redistributed over the criteria the school does offer.
STATUS_YES = "yes"
STATUS_TIER = "tier"
STATUS_NONE = "none"
MIN_RATED_CRITERIA = 5          # a school needs at least this many offered criteria (incl. teachers) to be rated
NEED_PENALTY = {STATUS_NONE: 0.5, STATUS_TIER: 0.2}  # match penalty when the student needs it and it is missing

PRIORITY_TO_FIELD = {
    "teacher": "teachers_score",
    "practice": "practice_score",
    "curator": "curator_score",
    "platform": "platform_score",
}


def criteria_status(school) -> dict:
    """Non-default statuses of a school as {criterion: 'tier'|'none'} (accepts ORM rows, dicts and JSON text)."""
    raw = school.get("criteria_status") if isinstance(school, dict) else getattr(school, "criteria_status", None)
    if not raw:
        return {}
    data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return {key: value for key, value in data.items() if key in BASE_WEIGHTS and value in (STATUS_TIER, STATUS_NONE)}


def status_of(school, key: str) -> str:
    return criteria_status(school).get(key, STATUS_YES)


def applicable_criteria(school) -> list:
    """Criteria the school offers, in BASE_WEIGHTS order."""
    status = criteria_status(school)
    return [key for key in BASE_WEIGHTS if status.get(key) != STATUS_NONE]


def is_rated(school) -> bool:
    keys = applicable_criteria(school)
    return len(keys) >= MIN_RATED_CRITERIA and "teachers_score" in keys


def effective_weights(school) -> dict:
    """Base weights restricted to the offered criteria and renormalised to sum to 1."""
    keys = applicable_criteria(school)
    total = sum(BASE_WEIGHTS[key] for key in keys)
    return {key: BASE_WEIGHTS[key] / total for key in keys}


def _value(school, key: str) -> float:
    raw = school.get(key) if isinstance(school, dict) else getattr(school, key, 0)
    return float(raw or 0)


def editorial_score(school) -> float:
    """Weighted 0-10 average over the criteria the school offers (missing ones neither help nor hurt)."""
    return sum(_value(school, key) * weight for key, weight in effective_weights(school).items())


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


def _personalized_weights(profile: QuizProfile, keys=None) -> dict:
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

    if keys is not None:
        weights = {key: value for key, value in weights.items() if key in keys}
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


_NEEDS = {
    "curator_score": lambda p: p.curator_need >= 3 or "curator" in p.priorities,
    "feedback_score": lambda p: p.control_need >= 3,
    "platform_score": lambda p: "platform" in p.priorities,
    "practice_score": lambda p: "practice" in p.priorities,
}
_NEED_REASONS = {
    ("curator_score", STATUS_NONE): "нет куратора, а он тебе нужен",
    ("curator_score", STATUS_TIER): "куратор — только на старших тарифах",
    ("feedback_score", STATUS_NONE): "нет проверки работ, а она тебе нужна",
    ("feedback_score", STATUS_TIER): "проверка работ — не на всех тарифах",
    ("platform_score", STATUS_NONE): "нет платформы, а она тебе важна",
    ("platform_score", STATUS_TIER): "платформа — не на всех тарифах",
    ("practice_score", STATUS_NONE): "нет практики, а она тебе важна",
    ("practice_score", STATUS_TIER): "практика — не на всех тарифах",
}


def _need_penalty(school, profile: QuizProfile):
    """Matching-only adjustment (the school's own rating is untouched): the student needs
    something the school does not offer (-0.5) or offers only on some tariffs (-0.2)."""
    delta, reasons = 0.0, []
    for key, needed in _NEEDS.items():
        status = status_of(school, key)
        if status != STATUS_YES and needed(profile):
            delta -= NEED_PENALTY[status]
            reasons.append(_NEED_REASONS[(key, status)])
    return delta, reasons


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

    keys = applicable_criteria(school)
    weights = _personalized_weights(profile, keys)
    fit = sum(_value(school, key) * weight for key, weight in weights.items())
    need_delta, need_reasons = _need_penalty(school, profile)
    fit += _budget_fit(school, profile) + need_delta
    fit = max(0.0, min(10.0, fit))

    reasons = []
    budget_delta = _budget_fit(school, profile)
    if budget_delta > 0:
        reasons.append("входит в бюджет")
    elif budget_delta < 0:
        reasons.append("может быть выше бюджета")

    reasons.extend(need_reasons)

    baseline = effective_weights(school)
    boosted = sorted(
        (key for key in weights if weights[key] > baseline[key] + 0.01),
        key=lambda key: weights[key],
        reverse=True,
    )
    for key in boosted:
        label = CRITERION_LABELS[key]
        value = _value(school, key)
        if value >= 8.5:
            reasons.append(f"сильные {label} ({value:.1f})")
        elif value <= 7.5:
            reasons.append(f"стоит проверить {label} ({value:.1f})")

    if not reasons:
        reasons.append("ровное совпадение по всем критериям")

    return round(fit / 10 * 100, 1), reasons[:3]
