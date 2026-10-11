"""Everything a review must satisfy before it is stored. Error texts are shown to the visitor as they are."""
import json
import re
import unicodedata
from typing import Optional

CONSENT_VERSION = "reviews-2026-10-11"

SCHOOL_CRITERIA = ("teachers_score", "practice_score", "feedback_score", "curator_score",
                   "platform_score", "workload_score", "organization_score")
TEACHER_CRITERIA = ("explanation", "practice", "atmosphere", "structure", "exam_value")
STUDY_PERIODS = ("2026/27", "2025/26", "2024/25", "earlier")
MAX_TEXT = 2000
MIN_TEXT_TOTAL = 40

# Throwaway inbox services: a confirmation through them proves nothing.
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
    "10minutemail.net", "temp-mail.org", "temp-mail.io", "tempmail.com", "tempmail.net", "tempmailo.com",
    "yopmail.com", "yopmail.net", "trashmail.com", "getnada.com", "nada.email", "dispostable.com",
    "maildrop.cc", "mailnesia.com", "mintemail.com", "fakeinbox.com", "throwawaymail.com", "emailondeck.com",
    "mohmal.com", "mail.tm", "mailpoof.com", "moakt.com", "tempail.com", "dropmail.me", "1secmail.com",
    "1secmail.net", "1secmail.org", "inboxkitten.com", "burnermail.io", "spamgourmet.com", "mytemp.email",
    "tempr.email", "discard.email", "crazymailing.com", "emltmp.com", "minuteinbox.com", "linshiyouxiang.net",
}
YANDEX_DOMAINS = {"yandex.ru", "ya.ru", "yandex.com", "yandex.by", "yandex.kz", "yandex.ua"}
EMAIL_RE = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
LINK_RE = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(?:ru|com|net|org|рф|io|me|online|site|pro)\b/?)", re.I)


class ReviewError(ValueError):
    pass


def normalize_email(raw) -> str:
    """Lower-cased address the person receives mail at. Raises ReviewError if it is not a usable address."""
    email = str(raw or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ReviewError("Проверь адрес почты.")
    domain = email.rsplit("@", 1)[1]
    if domain in DISPOSABLE_DOMAINS:
        raise ReviewError("Временная почта не подходит: укажи адрес, которым пользуешься.")
    return email


def identity_email(email: str) -> str:
    """One person, one identity: drop +tags everywhere, dots in Gmail, Yandex domain aliases."""
    local, domain = email.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    elif domain in YANDEX_DOMAINS:
        local, domain = local.replace(".", "-"), "yandex.ru"
    return f"{local}@{domain}"


def mask_email(email: str) -> str:
    local, domain = email.rsplit("@", 1)
    return f"{local[:2]}{'•' * max(1, min(6, len(local) - 2))}@{domain}"


def clean_text(raw) -> str:
    """Plain text only: normalised, without control or invisible formatting characters, collapsed blank lines."""
    text = unicodedata.normalize("NFC", str(raw or ""))
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def school_offers(criteria_status_json: str) -> tuple:
    """(required, optional) school criteria: 'none' is not asked, 'tier' may be skipped ("не было в моём тарифе")."""
    try:
        status = json.loads(criteria_status_json or "{}")
    except (TypeError, ValueError):
        status = {}
    required = tuple(key for key in SCHOOL_CRITERIA if status.get(key, "yes") == "yes")
    optional = tuple(key for key in SCHOOL_CRITERIA if status.get(key) == "tier")
    return required, optional


def _score(value, key) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ReviewError("Поставь каждую оценку от 1 до 10.")
    return value


def clean_review(data, school, teacher) -> dict:
    """Validated review fields for a school (teacher is None) or for one of its teachers."""
    if not isinstance(data, dict):
        raise ReviewError("Некорректный запрос.")
    scores = data.get("scores")
    if not isinstance(scores, dict):
        raise ReviewError("Поставь оценки.")
    if teacher is None:
        required, optional = school_offers(school.criteria_status)
    else:
        required, optional = TEACHER_CRITERIA, ()
    unknown = set(scores) - set(required) - set(optional)
    if unknown:
        raise ReviewError("В отзыве есть лишние оценки. Обнови страницу и попробуй снова.")
    clean = {}
    for key in required:
        if key not in scores:
            raise ReviewError("Поставь все оценки.")
        clean[key] = _score(scores[key], key)
    for key in optional:
        if scores.get(key) is not None:
            clean[key] = _score(scores[key], key)
    positive, negative = clean_text(data.get("positive")), clean_text(data.get("negative"))
    if len(positive) > MAX_TEXT or len(negative) > MAX_TEXT:
        raise ReviewError(f"Каждое поле — не длиннее {MAX_TEXT} символов.")
    if len(positive) + len(negative) < MIN_TEXT_TOTAL:
        raise ReviewError("Расскажи чуть подробнее: хотя бы пару предложений о плюсах или минусах.")
    if LINK_RE.search(positive) or LINK_RE.search(negative):
        raise ReviewError("Ссылки в отзывах не публикуются. Убери их, пожалуйста.")
    period = data.get("period")
    if period not in STUDY_PERIODS:
        raise ReviewError("Укажи, когда ты учился.")
    overall = round(sum(clean.values()) / len(clean))
    return {"scores": clean, "score": max(1, min(10, overall)), "positive": positive, "negative": negative,
            "period": period}


def clean_target(data) -> tuple:
    """(school_id, teacher_id or None) from the request."""
    if not isinstance(data, dict):
        raise ReviewError("Некорректный запрос.")
    school_id, teacher_id = data.get("school_id"), data.get("teacher_id")
    if isinstance(school_id, bool) or not isinstance(school_id, int):
        raise ReviewError("Выбери школу.")
    if teacher_id is not None and (isinstance(teacher_id, bool) or not isinstance(teacher_id, int)):
        raise ReviewError("Выбери преподавателя.")
    return school_id, teacher_id


def check_consent(data) -> None:
    if data.get("consent") is not True or data.get("consent_version") != CONSENT_VERSION:
        raise ReviewError("Нужно согласие на обработку персональных данных.")


def honeypot_filled(data) -> bool:
    return bool(str(data.get("website") or "").strip())


def parse_payload(raw: Optional[str]) -> dict:
    if not raw or len(raw) > 20_000:
        raise ReviewError("Некорректный запрос.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise ReviewError("Некорректный запрос.") from None
    if not isinstance(data, dict):
        raise ReviewError("Некорректный запрос.")
    return data
