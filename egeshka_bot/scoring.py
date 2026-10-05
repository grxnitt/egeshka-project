from datetime import date
import json
from dataclasses import dataclass
from typing import Optional, Tuple


BASE_WEIGHTS = {
    "teachers_score": 0.20,
    "practice_score": 0.16,
    "feedback_score": 0.14,
    "curator_score": 0.14,
    "platform_score": 0.14,
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
    lesson_format: str = "any"   # live / recorded / individual / any
    teacher_need: int = 2        # 1 not essential, 2 important, 3 decisive


# ---- Quiz matching: mirrors web/app.js "Quiz matching" block, number for number ------------------
# 1. Each criterion starts at its methodology weight; answers multiply it by an importance factor.
# 2. A school is judged per criterion by its percentile among the other schools, not by the raw score.
# 3. Format, budget and missing services subtract fixed percentage points and are listed as cautions.
IMPORTANCE = {
    "support": {1: {"curator_score": 0.5}, 3: {"curator_score": 2, "feedback_score": 2, "organization_score": 1.5},
                4: {"curator_score": 3, "feedback_score": 3, "organization_score": 2}},
    "level": {"low": {"curator_score": 1.5, "feedback_score": 1.5, "platform_score": 1.5},
              "high": {"teachers_score": 1.5, "practice_score": 1.5}},
    "target": {90: {"teachers_score": 1.5, "practice_score": 1.5}, 5: {"teachers_score": 1.3, "practice_score": 1.3}},
    "workload": {1: {"workload_score": 2}, 4: {"practice_score": 1.5}},
    "teacher": {1: {"teachers_score": 0.7}, 2: {"teachers_score": 1.5}, 3: {"teachers_score": 3}},
}
PRIORITY_MULTIPLIER = 2
MAX_IMPORTANCE = 4
PENALTY = {"format_missing": 35, "recorded_missing": 12, "format_unsure": 6, "need_none": 15, "need_tier": 5,
           "over_budget_max": 40, "price_unknown": 3}
FORMAT_LABELS = {"live": "живые занятия", "recorded": "занятия в записи", "individual": "занятия один на один"}
FORMAT_MISSING = {"live": "живых занятий", "recorded": "занятий в записи", "individual": "занятий один на один"}
# Same data as schoolFilters in web/school-content.js (a test keeps them identical):
# school -> (formats offered on at least one tariff, formats the school's materials don't confirm).
LESSON_FORMATS = {
    "Умскул": (("live", "recorded"), ()),
    "100балльный репетитор": (("live", "recorded"), ()),
    "Сотка": (("recorded",), ("live",)),
    "Фоксфорд": (("live", "recorded", "individual"), ()),
    "Вебиум": (("live", "recorded"), ()),
    "99 Баллов": (("live", "recorded"), ()),
    "Турбо ЕГЭ": (("live", "recorded"), ()),
    "ЕГЭLand": (("live", "recorded"), ()),
    "СМИТАП": (("live", "recorded"), ()),
    "PARTA": (("live", "recorded"), ()),
    "Skysmart": (("live", "recorded", "individual"), ()),
    "Школково": (("live", "recorded"), ()),
    "ЕГЭ Налегке": (("live", "recorded"), ()),
    "StudyCats": (("live", "recorded"), ()),
    "NeoFamily": (("live", "recorded"), ()),
    "Морозилка": (("live", "recorded", "individual"), ()),
    "Инсперия": (("live", "recorded", "individual"), ()),
    "ЕГЭХАБ": (("live", "recorded"), ()),
    "Школа Пифагора": (("recorded",), ()),
    "НОО": (("live", "recorded"), ()),
    "Тетрика": (("individual",), ()),
    "MAXIMUM Education": (("live", "individual"), ()),
    "Годограф": (("live", "recorded"), ()),
    "Коалиция": (("live", "recorded"), ()),
    "Lomonosov School": ((), ("live", "recorded")),
    "EXAMMY": (("recorded",), ()),
    "Лектариум": (("live", "recorded"), ()),
}


def _offered_subjects(school):
    return {s.strip().lower() for s in school.subjects.split(",") if s.strip()}


def _support_level(profile: QuizProfile) -> int:
    return max(profile.curator_need, profile.control_need)


def importance_of(profile: QuizProfile) -> dict:
    """Importance multiplier per criterion for this student (1 = as in the methodology)."""
    multipliers = {key: 1.0 for key in BASE_WEIGHTS}
    answers = {"support": _support_level(profile), "level": profile.current_level, "target": profile.target,
               "workload": profile.workload, "teacher": profile.teacher_need}
    for answer, table in IMPORTANCE.items():
        for key, factor in table.get(answers[answer], {}).items():
            multipliers[key] *= factor
    for priority in profile.priorities:
        field = PRIORITY_TO_FIELD.get(priority)
        if field:
            multipliers[field] *= PRIORITY_MULTIPLIER
    return {key: min(MAX_IMPORTANCE, value) for key, value in multipliers.items()}


def _position(key: str, value: float, peers):
    """(percentile, score) of a value among peer schools that offer the criterion.
    percentile: share of peers it beats (ties count half) - used for "лучше N% школ".
    score: half percentile, half place on the min..max scale, so 8.7 vs 8.9 stays close
    instead of looking like "worst" vs "best" when every school is between 8.5 and 9."""
    values = [_value(peer, key) for peer in peers if status_of(peer, key) != STATUS_NONE]
    if len(values) < 2:
        return 0.5, 0.5
    below = sum(1 for v in values if v < value - 1e-9)
    equal = sum(1 for v in values if abs(v - value) < 1e-9)
    percentile = (below + equal / 2) / len(values)
    low, high = min(values), max(values)
    scale = 0.5 if high - low < 1e-9 else min(1.0, max(0.0, (value - low) / (high - low)))
    return percentile, (percentile + scale) / 2


def _percentile(key: str, value: float, peers) -> float:
    return _position(key, value, peers)[0]


# A rated teacher for the chosen subject moves the match by a bounded number of points instead of
# replacing the school's teacher score: 4 points per point of difference, from -6 to +8,
# x0.5 / x1 / x1.5 for "не критично" / "важно" / "решающий".
SUBJECT_TEACHER = {"per_point": 4, "min": -6, "max": 8, "need": {1: 0.5, 2: 1, 3: 1.5}}
FACTOR_LABELS = {"teachers_score": "преподаватели", "practice_score": "практика", "feedback_score": "проверка работ",
                 "curator_score": "кураторы", "platform_score": "платформа", "workload_score": "нагрузка",
                 "organization_score": "организация", "subject_teacher": "препод по предмету", "format": "формат занятий",
                 "budget": "бюджет", "needs": "нужные услуги"}


def months_to_exam(today: Optional[date] = None) -> int:
    """Months of payments left until the exam (ЕГЭ in late May / June), counting the current month."""
    today = today or date.today()
    exam_year = today.year + 1 if today.month >= 7 else today.year
    return max(1, (exam_year - today.year) * 12 + 5 - today.month + 1)


def _subject_teacher_points(subject_score, school_teachers: float, profile) -> float:
    if subject_score is None:
        return 0.0
    raw = (subject_score - school_teachers) * SUBJECT_TEACHER["per_point"]
    raw = max(SUBJECT_TEACHER["min"], min(SUBJECT_TEACHER["max"], raw))
    return round(raw * SUBJECT_TEACHER["need"].get(profile.teacher_need, 1), 1)


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
    """Percentage points lost because the student needs a service the school lacks (or has only on some tariffs)."""
    points, reasons = 0.0, []
    for key, needed in _NEEDS.items():
        status = status_of(school, key)
        if status != STATUS_YES and needed(profile):
            points += PENALTY["need_none"] if status == STATUS_NONE else PENALTY["need_tier"]
            reasons.append(_NEED_REASONS[(key, status)])
    return points, reasons


# With "цена" as a priority, cheapness is a real advantage: up to PRICE_BONUS_MAX points for being cheaper than
# the budget (or, without a budget, than the median catalog price). Same scale as the over-budget penalty.
PRICE_BONUS_MAX = 20


def _median_price(peers) -> float:
    prices = sorted(float(getattr(p, "monthly_price_from", 0) or 0) for p in peers)
    prices = [p for p in prices if p > 0]
    if not prices:
        return 0.0
    middle = len(prices) // 2
    return prices[middle] if len(prices) % 2 else (prices[middle - 1] + prices[middle]) / 2


def _budget_fit(school, profile: QuizProfile, peers=()):
    """(points, pro, con): over budget costs 50 points per 100% over, at most 40; with "price" as a priority,
    a cheaper school earns up to PRICE_BONUS_MAX points."""
    if profile.subject == "математика базовая":
        return 0.0, None, None
    wants_cheap = "price" in profile.priorities
    price = float(getattr(school, "monthly_price_from", 0) or 0)
    if not profile.budget:
        reference = _median_price(peers) if wants_cheap else 0.0
        if reference and 0 < price < reference:
            return round(PRICE_BONUS_MAX * (1 - price / reference), 1), "дешевле большинства школ", None
        return 0.0, None, None
    if price <= 0:
        return -PENALTY["price_unknown"], None, "цена не опубликована — уточни у школы"
    if price <= profile.budget:
        bonus = round(PRICE_BONUS_MAX * (1 - price / profile.budget), 1) if wants_cheap else 0.0
        return bonus, "входит в бюджет", None
    return -min(PENALTY["over_budget_max"], (price - profile.budget) / profile.budget * 50), None, "может быть выше бюджета"


def _format_fit(school, profile: QuizProfile):
    fmt = profile.lesson_format
    if not fmt or fmt == "any":
        return 0.0, None, None
    lessons, unsure = LESSON_FORMATS.get(getattr(school, "name", ""), ((), ()))
    if fmt in lessons:
        return 0.0, f"есть {FORMAT_LABELS[fmt]}", None
    if fmt in unsure:
        return -PENALTY["format_unsure"], None, f"{FORMAT_LABELS[fmt]} не подтверждены — уточни у школы"
    missing = PENALTY["recorded_missing"] if fmt == "recorded" else PENALTY["format_missing"]
    return -missing, None, f"нет {FORMAT_MISSING[fmt]}"


def school_match(school, profile: QuizProfile, subject_teacher_score: Optional[float] = None, peers=None):
    """Match of one school for this student: {score, pros, cons, factors}, or None if it doesn't teach the subject.
    score = 50 + the sum of factors (each in percentage points against an average school), kept within 5..97.
    peers: all schools in the catalog; defaults to the school alone."""
    if profile.subject.lower() not in _offered_subjects(school):
        return None
    peers = list(peers) if peers else [school]
    keys = applicable_criteria(school)
    importance = importance_of(profile)
    pros, cons, factors = [], [], {}
    teachers_value = _value(school, "teachers_score")
    teacher_points = 0.0
    if subject_teacher_score is not None and "teachers_score" in keys:
        if subject_teacher_score >= teachers_value + 0.5:
            pros.append(f"сильный препод именно по этому предмету ({subject_teacher_score:.1f})")
        elif subject_teacher_score <= teachers_value - 1.0:
            cons.append(f"по этому предмету отзывы ниже, чем в среднем по школе ({subject_teacher_score:.1f})")
        teacher_points = _subject_teacher_points(subject_teacher_score, teachers_value, profile)

    weights = {key: BASE_WEIGHTS[key] * importance[key] for key in keys}
    weight_sum = sum(weights.values())
    emphasised = []
    for key in keys:
        percentile, position = _position(key, _value(school, key), peers)
        factors[key] = weights[key] / weight_sum * (position - 0.5) * 100 if weight_sum else 0.0
        if importance[key] >= 1.5:
            emphasised.append((importance[key], key, percentile))

    format_points, format_pro, format_con = _format_fit(school, profile)
    budget_points, budget_pro, budget_con = _budget_fit(school, profile, peers)
    need_points, need_reasons = _need_penalty(school, profile)
    factors.update({"subject_teacher": teacher_points, "format": format_points, "budget": budget_points, "needs": -need_points})
    pros += [item for item in (format_pro, budget_pro) if item]
    cons += [item for item in (format_con, budget_con) if item] + need_reasons
    for _, key, p in sorted(emphasised, key=lambda item: -item[0]):
        label = CRITERION_LABELS[key]
        if p >= 0.7:
            pros.append(f"{label} — лучше {round(p * 100)}% школ")
        elif p <= 0.3:
            cons.append(f"{label} — слабее большинства школ")
    if not pros:
        pros.append("ровное совпадение по всем критериям")
    percent = 50 + sum(factors.values())
    shown = sorted(((FACTOR_LABELS[key], round(value)) for key, value in factors.items() if abs(value) >= 1.5),
                   key=lambda item: -abs(item[1]))[:3]
    return {"score": round(max(5.0, min(97.0, percent)), 1), "pros": pros[:3], "cons": cons[:2], "factors": shown}


def school_score(school, profile: QuizProfile, subject_teacher_score: Optional[float] = None, peers=None) -> Tuple[float, list]:
    """(match %, reasons) — reasons are the pros followed by the cautions; -1 if the subject isn't taught."""
    match = school_match(school, profile, subject_teacher_score, peers)
    if match is None:
        return -1, ["не готовит по выбранному предмету"]
    return match["score"], match["pros"] + match["cons"]
