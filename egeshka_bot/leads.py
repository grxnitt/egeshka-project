"""Site leads: a student presses "Выбрать школу", leaves ONE contact and consents to hand it to that school.

Rules this module enforces (they come from the privacy policy, not from taste):
- a school receives leads only if it is enabled in lead_schools (after an agreement);
- consent is explicit, versioned and names the school; the consent version and time are stored;
- only name, one contact of the student's choosing and the exam subject are stored and delivered;
- no IP or user agent is stored; the rate limiter keeps IPs in memory only;
- the student can withdraw: personal fields are wiped and the school is told to delete its copy.
"""
import asyncio
import hashlib
import re
import secrets
import smtplib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Optional

import aiohttp
from sqlalchemy import delete, select

from .models import Lead, LeadSchool, School
from .subjects import SUBJECTS

CONSENT_VERSION = "2026-10-05"
CONTACT_TYPES = ("phone", "telegram", "vk")
DUPLICATE_WINDOW_DAYS = 90
RETENTION_DAYS = 365
MAX_ATTEMPTS = 5
RATE_LIMIT = (5, 3600)  # at most 5 requests per hour per visitor


class LeadError(ValueError):
    """A problem the student can fix; the message is shown to them as is."""


def normalize_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "3489":
        return None
    return "+7" + digits


def normalize_telegram(raw: str) -> Optional[str]:
    value = (raw or "").strip()
    value = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", value, flags=re.I).lstrip("@")
    return "@" + value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", value) else None


def normalize_vk(raw: str) -> Optional[str]:
    value = (raw or "").strip()
    value = re.sub(r"^(https?://)?(m\.)?(vk\.com|vk\.ru)/", "", value, flags=re.I).strip("/")
    return "https://vk.com/" + value if re.fullmatch(r"(id\d{1,12}|[A-Za-z0-9_.]{3,32})", value) else None


NORMALIZERS = {"phone": normalize_phone, "telegram": normalize_telegram, "vk": normalize_vk}
CONTACT_HINTS = {"phone": "телефон в формате +7 900 123-45-67", "telegram": "ник в Telegram, например @username", "vk": "ссылка на профиль VK"}


def contact_hash(school_id: int, contact_type: str, contact: str) -> str:
    return hashlib.sha256(f"{school_id}|{contact_type}|{contact}".encode()).hexdigest()


def consent_text(school_name: str, cfg: LeadSchool) -> str:
    recipient = f"{cfg.legal_name or school_name}" + (f" (ИНН {cfg.inn})" if cfg.inn else "")
    return (
        f"Я согласен(на) передать моё имя, выбранный мной контакт и предмет подготовки в {recipient}, чтобы школа связалась со мной "
        f"по вопросам обучения. После передачи школа обрабатывает эти данные самостоятельно по своей политике"
        + (f" ({cfg.policy_url})" if cfg.policy_url else "")
        + ". Согласие можно отозвать в любой момент, это удалит заявку в ЕГЭ Мэтче и отправит школе просьбу удалить данные. "
        "Если мне нет 18 лет, заявку оставляет мой родитель или законный представитель."
    )


def clean_request(data: dict, cfg: LeadSchool) -> dict:
    """Validate a request body; return clean fields or raise LeadError with a message for the student."""
    if not isinstance(data, dict):
        raise LeadError("Некорректный запрос.")
    if data.get("website"):  # honeypot field, hidden from people
        raise LeadError("Некорректный запрос.")
    if data.get("consent") is not True or data.get("consent_version") != CONSENT_VERSION:
        raise LeadError("Нужно согласие на передачу данных школе. Обновите страницу и отправьте заявку заново.")
    name = re.sub(r"\s+", " ", str(data.get("name") or "")).strip()
    if not 2 <= len(name) <= 80:
        raise LeadError("Укажите имя, от 2 до 80 символов.")
    contact_type = data.get("contact_type")
    accepted = [t for t in cfg.contact_types.split(",") if t in CONTACT_TYPES]
    if contact_type not in accepted:
        raise LeadError("Этот способ связи школа не принимает. Выберите другой.")
    contact = NORMALIZERS[contact_type](str(data.get("contact") or ""))
    if not contact:
        raise LeadError(f"Проверьте контакт: нужен {CONTACT_HINTS[contact_type]}.")
    subject = str(data.get("subject") or "")
    if subject not in SUBJECTS:
        raise LeadError("Выберите предмет.")
    return {"name": name, "contact_type": contact_type, "contact": contact, "subject": subject,
            "guardian": bool(data.get("guardian")), "source": str(data.get("source") or "site")[:30]}


class RateLimiter:
    """Per-visitor request limit. Keys are hashed and kept in memory only; nothing is written to disk."""

    def __init__(self, limit: int = RATE_LIMIT[0], window: int = RATE_LIMIT[1]):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        bucket = self.hits[hashlib.sha256(key.encode()).hexdigest()]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


async def school_config(session, school_name: str):
    row = (await session.execute(
        select(School, LeadSchool).join(LeadSchool, LeadSchool.school_id == School.id).where(School.name == school_name)
    )).first()
    return (row[0], row[1]) if row and row[1].enabled else (None, None)


async def enabled_schools(session) -> list:
    rows = (await session.execute(
        select(School.name, LeadSchool.contact_types).join(LeadSchool, LeadSchool.school_id == School.id).where(LeadSchool.enabled == True)  # noqa: E712
    )).all()
    return [{"name": name, "contactTypes": [t for t in types.split(",") if t in CONTACT_TYPES]} for name, types in rows]


async def create_lead(session, school: School, clean: dict, now: Optional[datetime] = None):
    """Store the lead. Returns (lead, withdraw_token, duplicate). A repeat of the same contact for the same
    school within 90 days is not stored or delivered again (the school would pay twice for one student)."""
    now = now or datetime.utcnow()
    digest = contact_hash(school.id, clean["contact_type"], clean["contact"])
    existing = (await session.execute(
        select(Lead).where(Lead.contact_hash == digest, Lead.created_at >= now - timedelta(days=DUPLICATE_WINDOW_DAYS),
                           Lead.status != "withdrawn")
    )).scalars().first()
    if existing:
        return existing, "", True
    token = secrets.token_urlsafe(24)
    lead = Lead(school_id=school.id, contact_hash=digest, consent_version=CONSENT_VERSION, consent_at=now, created_at=now,
                withdraw_hash=hashlib.sha256(token.encode()).hexdigest(), **clean)
    session.add(lead)
    await session.commit()
    return lead, token, False


def lead_message(lead: Lead, school_name: str) -> str:
    kind = {"phone": "Телефон", "telegram": "Telegram", "vk": "VK"}[lead.contact_type]
    return (
        f"Новая заявка с ЕГЭ Мэтч №{lead.id} для школы «{school_name}»\n"
        f"Имя: {lead.name}\n{kind}: {lead.contact}\nПредмет: {lead.subject}\n"
        + ("Заявку оставил родитель или законный представитель.\n" if lead.guardian else "")
        + f"Согласие на передачу данных получено {lead.consent_at:%d.%m.%Y %H:%M} UTC (версия {lead.consent_version}).\n"
        "Если ученик отзовёт согласие, мы пришлём уведомление с номером заявки: данные нужно будет удалить."
    )


def withdrawal_message(lead_id: int, school_name: str) -> str:
    return f"Заявка с ЕГЭ Мэтч №{lead_id} для школы «{school_name}» отозвана: ученик забрал согласие. Удалите его данные и не связывайтесь с ним."


def _send_email(settings, to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.smtp_from or settings.smtp_user, to, subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def deliver(settings, cfg: LeadSchool, subject: str, body: str, payload: Optional[dict] = None) -> Optional[str]:
    """Send one message through every channel the school configured. Returns None on success, else an error text.
    A lead counts as delivered only if all configured channels worked."""
    errors, tried = [], 0
    if cfg.delivery_email and settings.smtp_host:
        tried += 1
        try:
            await asyncio.to_thread(_send_email, settings, cfg.delivery_email, subject, body)
        except Exception as exc:  # noqa: BLE001 - any SMTP failure is retried later
            errors.append(f"email: {type(exc).__name__}")
    timeout = aiohttp.ClientTimeout(total=20)
    if cfg.webhook_url:
        tried += 1
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.post(cfg.webhook_url, json={"text": body, **(payload or {})}) as response:
                    if response.status >= 300:
                        errors.append(f"webhook: HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"webhook: {type(exc).__name__}")
    if cfg.tg_chat_id and settings.bot_token:
        tried += 1
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.post(f"https://api.telegram.org/bot{settings.bot_token}/sendMessage",
                                     json={"chat_id": cfg.tg_chat_id, "text": body}) as response:
                    if response.status >= 300:
                        errors.append(f"telegram: HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"telegram: {type(exc).__name__}")
    if not tried:
        return "no delivery channel configured"
    return "; ".join(errors)[:300] or None


async def deliver_lead(session, settings, lead: Lead, school: School, cfg: LeadSchool) -> bool:
    lead.attempts += 1
    error = await deliver(settings, cfg, f"Заявка с ЕГЭ Мэтч №{lead.id}", lead_message(lead, school.name),
                          {"lead_id": lead.id, "name": lead.name, "contact_type": lead.contact_type, "contact": lead.contact,
                           "subject": lead.subject, "guardian": lead.guardian})
    lead.last_error = error or ""
    if error is None:
        lead.status, lead.sent_at = "sent", datetime.utcnow()
    else:
        lead.status = "failed"
    await session.commit()
    return error is None


async def retry_pending(session_factory, settings, now: Optional[datetime] = None) -> int:
    """Resend leads that failed or never got sent, with growing pauses (1, 2, 4... minutes), up to 5 attempts."""
    now = now or datetime.utcnow()
    sent = 0
    async with session_factory() as session:
        pending = (await session.execute(
            select(Lead).where(Lead.status.in_(("new", "failed")), Lead.attempts < MAX_ATTEMPTS)
        )).scalars().all()
        for lead in pending:
            last = lead.sent_at or lead.created_at
            if lead.attempts and now - last < timedelta(minutes=2 ** (lead.attempts - 1)):
                continue
            school = await session.get(School, lead.school_id)
            cfg = await session.get(LeadSchool, lead.school_id)
            if school and cfg and cfg.enabled and await deliver_lead(session, settings, lead, school, cfg):
                sent += 1
    return sent


async def withdraw(session, settings, token: str) -> bool:
    """Wipe the student's personal fields and tell the school (by lead number only) to delete its copy."""
    digest = hashlib.sha256((token or "").encode()).hexdigest()
    lead = (await session.execute(select(Lead).where(Lead.withdraw_hash == digest, Lead.status != "withdrawn"))).scalars().first()
    if not lead:
        return False
    school = await session.get(School, lead.school_id)
    cfg = await session.get(LeadSchool, lead.school_id)
    was_sent = lead.status == "sent"
    lead.name, lead.contact, lead.contact_hash, lead.withdraw_hash, lead.status = "", "", "", "", "withdrawn"
    await session.commit()
    if was_sent and school and cfg:
        await deliver(settings, cfg, f"Отзыв заявки №{lead.id}", withdrawal_message(lead.id, school.name))
    return True


async def purge_old(session, days: int = RETENTION_DAYS, now: Optional[datetime] = None) -> int:
    cutoff = (now or datetime.utcnow()) - timedelta(days=days)
    result = await session.execute(delete(Lead).where(Lead.created_at < cutoff))
    await session.commit()
    return result.rowcount or 0
