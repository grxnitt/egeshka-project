"""Admin side of site leads, all in the bot and only for ADMIN_IDS: connect a school, switch it on or off,
send a test lead, see how leads are going and build the monthly report (appendix 3 of the school contract)."""
import csv
import io
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ChatMemberUpdated, Message
from sqlalchemy import func, select

from . import leads
from .models import Lead, LeadSchool, School

MSK = timedelta(hours=3)
WITHDRAW_FREE_HOURS = 24  # a lead withdrawn this soon after delivery is not paid (contract 5.3 "д")
CONTACT_LABELS = {"phone": "Телефон", "telegram": "Telegram", "vk": "VK", "email": "Почта"}

# /lead_set keys -> LeadSchool fields
SET_KEYS = {
    "name": "legal_name", "inn": "inn", "policy": "policy_url", "contacts": "contact_types", "email": "delivery_email",
    "webhook": "webhook_url", "tg": "tg_chat_id", "sales": "sales_contact", "pd": "pd_contact", "rate": "rate",
}

HELP = (
    "Заявки — команды админа\n\n"
    "/lead_schools — школы и их статус\n"
    "/lead_set Школа | name=ООО «…» | inn=… | policy=https://… | contacts=phone,telegram,vk,email | "
    "email=… | webhook=https://… | tg=-100… | sales=… | pd=… | rate=300 — подключить или изменить (любые ключи)\n"
    "/lead_secret Школа — новый ключ подписи вебхука\n"
    "/lead_test Школа — тестовая заявка (в отчёт не попадает)\n"
    "/lead_on Школа, /lead_off Школа — включить или поставить на паузу\n"
    "/leads — статистика за сегодня и месяц\n"
    "/lead_report Школа ГГГГ-ММ — отчёт за месяц файлом\n"
    "/lead_exclude ID причина — принять спор школы, /lead_include ID — вернуть заявку в оплату"
)


def parse_set(text: str):
    """'/lead_set Школа | key=value | ...' -> (school name, {field: value}) or raise ValueError with a hint."""
    parts = [part.strip() for part in text.split("|")]
    head = parts[0].split(maxsplit=1)
    if len(head) < 2 or not head[1].strip():
        raise ValueError("Формат: /lead_set Школа | key=value | ...")
    values = {}
    for part in parts[1:]:
        if "=" not in part:
            raise ValueError(f"Нет «=» в «{part}»")
        key, value = (item.strip() for item in part.split("=", 1))
        if key not in SET_KEYS:
            raise ValueError(f"Неизвестный ключ «{key}». Можно: {', '.join(SET_KEYS)}")
        if key == "contacts":
            types = [t.strip() for t in value.split(",") if t.strip()]
            if not types or any(t not in leads.CONTACT_TYPES for t in types):
                raise ValueError("contacts — через запятую из: phone, telegram, vk, email")
            value = ",".join(types)
        if key == "inn" and not re.fullmatch(r"\d{10}|\d{12}", value):
            raise ValueError("ИНН — 10 или 12 цифр")
        if key in ("policy", "webhook") and value and not value.startswith("https://"):
            raise ValueError(f"{key} должен начинаться с https://")
        if key == "rate":
            if not value.isdigit():
                raise ValueError("rate — целое число рублей")
            value = int(value)
        values[SET_KEYS[key]] = value
    return head[1].strip(), values


def missing_for_launch(cfg: LeadSchool) -> list:
    """What still has to be filled in before a school can be switched on."""
    missing = []
    if not cfg.legal_name:
        missing.append("name (юрлицо)")
    if not cfg.inn:
        missing.append("inn")
    if not (cfg.delivery_email or cfg.webhook_url or cfg.tg_chat_id):
        missing.append("канал доставки (email, webhook или tg)")
    if not cfg.pd_contact:
        missing.append("pd (кому слать отзывы согласия)")
    if not cfg.rate:
        missing.append("rate (ставка)")
    return missing


def _status(lead: Lead):
    """(status, reason, billable) of a delivered lead for the monthly report."""
    if lead.excluded_reason:
        return "Исключена", lead.excluded_reason, False
    if lead.withdrawn_at and lead.sent_at and lead.withdrawn_at - lead.sent_at < timedelta(hours=WITHDRAW_FREE_HOURS):
        return "Отозвана", "отзыв согласия в течение 24 часов", False
    if lead.withdrawn_at:
        return "Валидная", "отозвана позже 24 часов — оплачивается", True
    return "Валидная", "", True


def month_bounds(month: str):
    match = re.fullmatch(r"(\d{4})-(\d{2})", month or "")
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise ValueError("Месяц в формате ГГГГ-ММ, например 2026-11")
    year, number = int(match.group(1)), int(match.group(2))
    start = datetime(year, number, 1) - MSK  # months are counted in Moscow time
    end = (datetime(year + 1, 1, 1) if number == 12 else datetime(year, number + 1, 1)) - MSK
    return start, end


async def month_report(session, school: School, cfg: Optional[LeadSchool], month: str):
    start, end = month_bounds(month)
    rows = (await session.execute(
        select(Lead).where(Lead.school_id == school.id, Lead.is_test == False, Lead.sent_at.is_not(None),  # noqa: E712
                           Lead.sent_at >= start, Lead.sent_at < end).order_by(Lead.id)
    )).scalars().all()
    lines, valid = [], 0
    for lead in rows:
        status, reason, billable = _status(lead)
        valid += billable
        channels = ", ".join(leads.CHANNEL_LABELS.get(c, c) for c in lead.delivered_via.split(",") if c)
        lines.append([lead.id, (lead.sent_at + MSK).strftime("%d.%m.%Y %H:%M"), lead.subject,
                      CONTACT_LABELS.get(lead.contact_type, lead.contact_type), channels, status, reason or "—"])
    rate = cfg.rate if cfg else 0
    summary = {"delivered": len(rows), "excluded": len(rows) - valid, "valid": valid, "rate": rate, "total": valid * rate}
    return lines, summary


def report_csv(school_name: str, month: str, lines: list, summary: dict) -> bytes:
    """Semicolon CSV with a BOM, so Excel in Russian locale opens it with the right columns and letters."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow([f"Отчёт ЕГЭ Мэтч за {month}", school_name])
    writer.writerow(["№ заявки", "Дата и время доставки (МСК)", "Предмет", "Вид контакта", "Канал доставки", "Статус",
                     "Основание исключения"])
    writer.writerows(lines)
    writer.writerow([])
    writer.writerow(["Доставлено", summary["delivered"]])
    writer.writerow(["Исключено", summary["excluded"]])
    writer.writerow(["Валидных заявок", summary["valid"]])
    writer.writerow(["Ставка, ₽", summary["rate"]])
    writer.writerow(["К оплате, ₽", summary["total"]])
    writer.writerow(["Отчёт не содержит имён и контактов учеников."])
    return ("﻿" + out.getvalue()).encode("utf-8")


async def stats_text(session, now: Optional[datetime] = None) -> str:
    now = now or datetime.utcnow()
    local = now + MSK
    day_start = datetime(local.year, local.month, local.day) - MSK
    month_start = datetime(local.year, local.month, 1) - MSK
    schools = {s.id: s.name for s in (await session.execute(select(School))).scalars().all()}
    rows = (await session.execute(
        select(Lead.school_id, Lead.status, Lead.created_at, Lead.withdrawn_at).where(
            Lead.is_test == False, Lead.created_at >= month_start)  # noqa: E712
    )).all()
    if not rows:
        return f"Заявок за {local:%m.%Y} пока нет."
    per = {}
    for school_id, status, created_at, withdrawn_at in rows:
        item = per.setdefault(schools.get(school_id, str(school_id)), {"today": 0, "month": 0, "failed": 0, "withdrawn": 0})
        item["month"] += 1
        item["today"] += created_at >= day_start
        item["failed"] += status in ("new", "failed")
        item["withdrawn"] += withdrawn_at is not None
    lines = [f"Заявки: сегодня / за {local:%m.%Y} · не доставлено · отозвано"]
    for name, item in sorted(per.items(), key=lambda kv: -kv[1]["month"]):
        lines.append(f"• {name}: {item['today']} / {item['month']} · {item['failed']} · {item['withdrawn']}")
    total = sum(item["month"] for item in per.values())
    lines.append(f"Всего за месяц: {total}")
    return "\n".join(lines)


async def _school(session, name: str):
    school = (await session.execute(select(School).where(func.lower(School.name) == name.strip().lower()))).scalar_one_or_none()
    cfg = await session.get(LeadSchool, school.id) if school else None
    return school, cfg


def register(dp: Dispatcher, session_factory, settings):
    def admin(message: Message) -> bool:
        return bool(message.from_user) and message.from_user.id in settings.admin_id_set

    def arg(message: Message) -> str:
        parts = (message.text or "").split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    @dp.my_chat_member()
    async def added_to_group(event: ChatMemberUpdated):
        """A school added the bot to its sales chat: tell the admins the chat ID, say nothing in the group."""
        if event.chat.type not in ("group", "supergroup", "channel"):
            return
        if event.new_chat_member.status not in ("member", "administrator") or event.old_chat_member.status in ("member", "administrator"):
            return
        who = event.from_user.full_name if event.from_user else "кто-то"
        text = (f"Бота добавили в чат «{event.chat.title}» ({who}).\nID чата: {event.chat.id}\n\n"
                f"Подключить к школе: /lead_set Школа | tg={event.chat.id}")
        for admin_id in settings.admin_id_set:
            try:
                await event.bot.send_message(admin_id, text)
            except Exception:  # noqa: BLE001 - an admin who never opened the bot can't be messaged
                pass

    @dp.message(Command("lead_help"))
    async def lead_help(message: Message):
        if admin(message):
            await message.answer(HELP)

    @dp.message(Command("lead_schools"))
    async def lead_schools(message: Message):
        if not admin(message):
            return
        async with session_factory() as session:
            rows = (await session.execute(select(School.name, LeadSchool).join(LeadSchool, LeadSchool.school_id == School.id))).all()
        if not rows:
            await message.answer("Ни одна школа ещё не подключена. /lead_help")
            return
        lines = []
        for name, cfg in rows:
            channels = [label for label, on in (("почта", cfg.delivery_email), ("CRM", cfg.webhook_url), ("Telegram", cfg.tg_chat_id)) if on]
            missing = missing_for_launch(cfg)
            state = "🟢 включена" if cfg.enabled else "⏸ выключена"
            lines.append(f"{state} {name}: {', '.join(channels) or 'нет канала'}; контакты {cfg.contact_types}; ставка {cfg.rate} ₽"
                         + (f"; не хватает: {', '.join(missing)}" if missing else ""))
        await message.answer("\n".join(lines))

    @dp.message(Command("lead_set"))
    async def lead_set(message: Message):
        if not admin(message):
            return
        try:
            name, values = parse_set(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return
        async with session_factory() as session:
            school, cfg = await _school(session, name)
            if not school:
                await message.answer(f"Школа «{name}» не найдена в каталоге.")
                return
            if cfg is None:
                cfg = LeadSchool(school_id=school.id, enabled=False)
                session.add(cfg)
            for field, value in values.items():
                setattr(cfg, field, value)
            await session.commit()
            missing = missing_for_launch(cfg)
        await message.answer(f"Сохранено для «{school.name}». "
                             + (f"Для запуска не хватает: {', '.join(missing)}." if missing else "Можно отправить /lead_test, затем /lead_on."))

    @dp.message(Command("lead_secret"))
    async def lead_secret(message: Message):
        if not admin(message):
            return
        async with session_factory() as session:
            school, cfg = await _school(session, arg(message))
            if not cfg:
                await message.answer("Сначала подключи школу через /lead_set.")
                return
            cfg.webhook_secret = secrets.token_hex(24)
            await session.commit()
            secret = cfg.webhook_secret
        await message.answer(f"Ключ подписи вебхука для «{school.name}»:\n{secret}\n\nПередай его школе. Каждый запрос приходит с заголовком "
                             "X-EgeMatch-Signature: sha256=<HMAC-SHA256 тела запроса этим ключом>.")

    @dp.message(Command("lead_test"))
    async def lead_test(message: Message):
        if not admin(message):
            return
        async with session_factory() as session:
            school, cfg = await _school(session, arg(message))
            if not cfg:
                await message.answer("Сначала подключи школу через /lead_set.")
                return
            contact_type = cfg.contact_types.split(",")[0] or "phone"
            sample = {"phone": "+79000000000", "telegram": "@egematch_test", "vk": "https://vk.com/id1", "email": "test@egematch.ru"}
            clean = {"name": "Тест ЕГЭ Мэтч", "contact_type": contact_type, "contact": sample.get(contact_type, "+79000000000"),
                     "subject": "Русский", "guardian": False, "source": "admin_test"}
            lead, _token, _dup = await leads.create_lead(session, school, clean, is_test=True)
            ok = await leads.deliver_lead(session, settings, lead, school, cfg)
            channels = lead.delivered_via or "—"
            error = lead.last_error
        await message.answer(f"Тестовая заявка №{lead.id}: " + ("доставлена" if ok else f"ошибка: {error}") + f" (каналы: {channels}). "
                             "Попроси школу подтвердить, что она дошла.")

    async def switch(message: Message, on: bool):
        if not admin(message):
            return
        async with session_factory() as session:
            school, cfg = await _school(session, arg(message))
            if not cfg:
                await message.answer("Школа не подключена. /lead_set")
                return
            missing = missing_for_launch(cfg)
            if on and missing:
                await message.answer(f"Нельзя включить: не хватает {', '.join(missing)}.")
                return
            cfg.enabled = on
            await session.commit()
        await message.answer(f"«{school.name}»: приём заявок {'включён' if on else 'на паузе'}. На сайте это видно сразу при следующем открытии страницы.")

    @dp.message(Command("lead_on"))
    async def lead_on(message: Message):
        await switch(message, True)

    @dp.message(Command("lead_off"))
    async def lead_off(message: Message):
        await switch(message, False)

    @dp.message(Command("leads"))
    async def leads_stats(message: Message):
        if not admin(message):
            return
        async with session_factory() as session:
            await message.answer(await stats_text(session))

    @dp.message(Command("lead_report"))
    async def lead_report(message: Message):
        if not admin(message):
            return
        text = arg(message)
        match = re.fullmatch(r"(.+?)\s+(\d{4}-\d{2})", text)
        if not match:
            await message.answer("Формат: /lead_report Школа ГГГГ-ММ")
            return
        async with session_factory() as session:
            school, cfg = await _school(session, match.group(1))
            if not school:
                await message.answer("Школа не найдена.")
                return
            try:
                lines, summary = await month_report(session, school, cfg, match.group(2))
            except ValueError as exc:
                await message.answer(str(exc))
                return
        data = report_csv(school.name, match.group(2), lines, summary)
        await message.answer_document(BufferedInputFile(data, filename=f"egematch-{match.group(2)}-{school.id}.csv"),
                                      caption=f"«{school.name}», {match.group(2)}: доставлено {summary['delivered']}, "
                                              f"валидных {summary['valid']}, к оплате {summary['total']} ₽.")

    @dp.message(Command("lead_exclude"))
    async def lead_exclude(message: Message):
        if not admin(message):
            return
        match = re.fullmatch(r"(\d+)\s+(.+)", arg(message))
        if not match:
            await message.answer("Формат: /lead_exclude ID причина")
            return
        async with session_factory() as session:
            lead = await session.get(Lead, int(match.group(1)))
            if not lead:
                await message.answer("Заявка не найдена.")
                return
            lead.excluded_reason = match.group(2)[:200]
            await session.commit()
        await message.answer(f"Заявка №{lead.id} исключена из оплаты: {lead.excluded_reason}")

    @dp.message(Command("lead_include"))
    async def lead_include(message: Message):
        if not admin(message):
            return
        value = arg(message)
        async with session_factory() as session:
            lead = await session.get(Lead, int(value)) if value.isdigit() else None
            if not lead:
                await message.answer("Формат: /lead_include ID")
                return
            lead.excluded_reason = ""
            await session.commit()
        await message.answer(f"Заявка №{lead.id} снова учитывается в оплате.")
