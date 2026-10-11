"""School partnerships and leads in the moderation console (localhost only, behind the SSH tunnel).

Every change goes through the guards of admin_app (host check, token header, origin check). The rules that protect
students are enforced here and not only in the page:
- a school can be switched on only when its legal entity, INN, delivery channel, privacy contact and the date of the
  agreement are filled in, and only the leads service reads that switch;
- the global switch needs both confirmations (Roskomnadzor notice, tax answer) to be ticked and the word typed;
- lists never show a student's name or contact, only the technical state of the request.
"""
import re
import secrets
from datetime import date, datetime, timedelta

from aiohttp import web
from sqlalchemy import func, select, text

from egeshka_bot import lead_admin, leads
from egeshka_bot.models import Lead, LeadSchool, School

from .lead_settings import LeadSettings

SCHOOL_TEXT = {"legal_name": 200, "policy_url": 500, "delivery_email": 200, "webhook_url": 500, "tg_chat_id": 40,
               "sales_contact": 200, "pd_contact": 200, "notes": 4000}
SCHOOL_INT = ("rate", "bonus_fixed", "bonus_percent", "bonus_min")
GLOBAL_WORD = "ВКЛЮЧИТЬ"


class FieldError(ValueError):
    pass


def clean_school_update(data: dict) -> dict:
    """Validated LeadSchool fields from the console form. Raises FieldError with the text shown to the owner."""
    if not isinstance(data, dict):
        raise FieldError("Некорректный запрос.")
    values = {}
    for field, limit in SCHOOL_TEXT.items():
        if field in data:
            value = str(data[field] or "").strip()
            if len(value) > limit:
                raise FieldError(f"«{field}» длиннее {limit} символов.")
            values[field] = value
    if values.get("inn") or "inn" in data:
        inn = str(data.get("inn") or "").strip()
        if inn and not re.fullmatch(r"\d{10}|\d{12}", inn):
            raise FieldError("ИНН — 10 или 12 цифр.")
        values["inn"] = inn
    for field in ("policy_url", "webhook_url"):
        if values.get(field) and not values[field].startswith("https://"):
            raise FieldError(f"Ссылка «{field}» должна начинаться с https://")
    if values.get("delivery_email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", values["delivery_email"]):
        raise FieldError("Проверь адрес почты школы.")
    if values.get("tg_chat_id") and not re.fullmatch(r"-?\d{5,20}|@[A-Za-z][A-Za-z0-9_]{4,31}", values["tg_chat_id"]):
        raise FieldError("Чат Telegram — число (например, -1001234567890) или @имя_канала.")
    if "contact_types" in data:
        types = [t for t in (data["contact_types"] if isinstance(data["contact_types"], list) else []) if t in leads.CONTACT_TYPES]
        if not types:
            raise FieldError("Оставь хотя бы один способ связи ученика с школой.")
        values["contact_types"] = ",".join(t for t in leads.CONTACT_TYPES if t in types)
    for field in SCHOOL_INT:
        if field in data:
            raw = data[field]
            if isinstance(raw, bool) or not (isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit())):
                raise FieldError(f"«{field}» — целое число рублей или процентов.")
            number = int(raw)
            if number < 0 or number > 10_000_000 or (field == "bonus_percent" and number > 100):
                raise FieldError(f"«{field}» вне допустимых пределов.")
            values[field] = number
    if "agreement_date" in data:
        raw = str(data["agreement_date"] or "").strip()
        if raw:
            try:
                values["agreement_date"] = date.fromisoformat(raw)
            except ValueError:
                raise FieldError("Дата договора — в виде ГГГГ-ММ-ДД.") from None
            if values["agreement_date"] > date.today() + timedelta(days=30):
                raise FieldError("Дата договора слишком далеко в будущем.")
        else:
            values["agreement_date"] = None
    return values


MISSING_LABELS = {
    "name (юрлицо)": "юрлицо", "inn": "ИНН", "канал доставки (email, webhook или tg)": "хотя бы один канал доставки",
    "pd (кому слать отзывы согласия)": "контакт школы для уведомлений об отзыве согласия",
}


def missing_labels(cfg: LeadSchool) -> list:
    return [MISSING_LABELS.get(item, item) for item in lead_admin.missing_for_launch(cfg)]


def school_row(school: School, cfg: LeadSchool, counts: dict) -> dict:
    missing = missing_labels(cfg)
    return {
        "id": school.id, "name": school.name, "enabled": bool(cfg.enabled), "missing": missing,
        "legal_name": cfg.legal_name, "inn": cfg.inn, "policy_url": cfg.policy_url,
        "contact_types": [t for t in cfg.contact_types.split(",") if t],
        "delivery_email": cfg.delivery_email, "webhook_url": cfg.webhook_url, "tg_chat_id": cfg.tg_chat_id,
        "has_secret": bool(cfg.webhook_secret), "sales_contact": cfg.sales_contact, "pd_contact": cfg.pd_contact,
        "rate": cfg.rate, "bonus_fixed": cfg.bonus_fixed, "bonus_percent": cfg.bonus_percent, "bonus_min": cfg.bonus_min,
        "agreement_date": cfg.agreement_date.isoformat() if cfg.agreement_date else "", "notes": cfg.notes,
        "counts": counts,
    }


def register(app: web.Application, settings, session_factory):
    lead_settings = LeadSettings(settings)

    async def counts_by_school(session):
        rows = (await session.execute(select(Lead.school_id, Lead.status, func.count()).where(Lead.is_test == False)  # noqa: E712
                                      .group_by(Lead.school_id, Lead.status))).all()
        result = {}
        for school_id, status, number in rows:
            item = result.setdefault(school_id, {"total": 0, "sent": 0, "waiting": 0, "withdrawn": 0})
            item["total"] += number
            item["sent"] += number if status == "sent" else 0
            item["waiting"] += number if status in ("new", "failed") else 0
            item["withdrawn"] += number if status == "withdrawn" else 0
        return result

    async def ensure_config(session, school_id: int):
        school = await session.get(School, school_id)
        if school is None:
            raise web.HTTPNotFound()
        cfg = await session.get(LeadSchool, school_id)
        if cfg is None:
            cfg = LeadSchool(school_id=school_id, enabled=False)
            session.add(cfg)
            await session.flush()
        return school, cfg

    async def flag(session) -> dict:
        row = (await session.execute(text("select value, note, updated_at from site_flags where key = 'leads_enabled'"))).first()
        return {"enabled": bool(row and row[0]), "note": (row[1] if row else ""), "updated": str(row[2])[:16] if row else ""}

    async def overview(request):
        async with session_factory() as session:
            schools = (await session.execute(select(School).where(School.is_active == True).order_by(School.name))).scalars().all()  # noqa: E712
            configs = {c.school_id: c for c in (await session.execute(select(LeadSchool))).scalars().all()}
            counts = await counts_by_school(session)
            rows = []
            for school in schools:
                cfg = configs.get(school.id) or LeadSchool(school_id=school.id, enabled=False)
                rows.append(school_row(school, cfg, counts.get(school.id, {"total": 0, "sent": 0, "waiting": 0, "withdrawn": 0})))
            return web.json_response({"schools": rows, "global": await flag(session), "word": GLOBAL_WORD,
                                      "telegram_relay": bool(settings.telegram_api_base)})

    async def save(request):
        school_id = int(request.match_info["id"])
        try:
            values = clean_school_update(await request.json())
        except (FieldError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        async with session_factory() as session:
            school, cfg = await ensure_config(session, school_id)
            for field, value in values.items():
                setattr(cfg, field, value)
            missing = missing_labels(cfg)
            if cfg.enabled and missing:           # editing a live school must not leave it half-configured
                cfg.enabled = False
            await session.commit()
            counts = (await counts_by_school(session)).get(school_id, {"total": 0, "sent": 0, "waiting": 0, "withdrawn": 0})
            return web.json_response({"school": school_row(school, cfg, counts)})

    async def switch(request):
        school_id = int(request.match_info["id"])
        data = await request.json()
        on = isinstance(data, dict) and data.get("enabled") is True
        async with session_factory() as session:
            school, cfg = await ensure_config(session, school_id)
            missing = missing_labels(cfg)
            if on and missing:
                return web.json_response({"error": "Нельзя включить: не хватает — " + ", ".join(missing)}, status=400)
            cfg.enabled = on
            await session.commit()
            counts = (await counts_by_school(session)).get(school_id, {"total": 0, "sent": 0, "waiting": 0, "withdrawn": 0})
            return web.json_response({"school": school_row(school, cfg, counts)})

    async def secret(request):
        school_id = int(request.match_info["id"])
        async with session_factory() as session:
            school, cfg = await ensure_config(session, school_id)
            cfg.webhook_secret = secrets.token_hex(24)
            await session.commit()
            return web.json_response({"secret": cfg.webhook_secret})   # shown once; hand it to the school

    async def test(request):
        school_id = int(request.match_info["id"])
        async with session_factory() as session:
            school, cfg = await ensure_config(session, school_id)
            channels = [name for name, used in (("почта", cfg.delivery_email), ("CRM", cfg.webhook_url), ("Telegram", cfg.tg_chat_id)) if used]
            if not channels:
                return web.json_response({"error": "Сначала укажи хотя бы один канал доставки."}, status=400)
            contact_type = (cfg.contact_types.split(",") or ["phone"])[0] or "phone"
            sample = {"phone": "+79000000000", "telegram": "@egematch_test", "vk": "https://vk.com/id1", "email": "test@egematch.ru"}
            clean = {"name": "Тест ЕГЭ Мэтч", "contact_type": contact_type, "contact": sample[contact_type], "subject": "Русский",
                     "guardian": False, "source": "admin_test"}
            lead, _token, _dup = await leads.create_lead(session, school, clean, is_test=True)
            ok = await leads.deliver_lead(session, lead_settings, lead, school, cfg)
            return web.json_response({"ok": ok, "channels": lead.delivered_via, "error": lead.last_error, "id": lead.id,
                                      "asked": channels})

    async def global_flag(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise web.HTTPBadRequest()
        turning_on = data.get("enabled") is True
        if turning_on:
            if data.get("word") != GLOBAL_WORD or data.get("rkn") is not True or data.get("tax") is not True:
                return web.json_response({"error": f"Чтобы включить заявки на всём сайте, отметь оба пункта и введи слово «{GLOBAL_WORD}»."}, status=400)
        note = (f"on: РКН={data.get('rkn')}, налоговая={data.get('tax')}" if turning_on else "off")[:300]
        async with session_factory() as session:
            await session.execute(text("update site_flags set value = :v, note = :n, updated_at = (now() at time zone 'utc') where key = 'leads_enabled'")
                                  if session.bind.dialect.name == "postgresql" else
                                  text("update site_flags set value = :v, note = :n, updated_at = CURRENT_TIMESTAMP where key = 'leads_enabled'"),
                                  {"v": turning_on, "n": note})
            await session.commit()
            return web.json_response({"global": await flag(session)})

    async def leads_list(request):
        school_id = request.query.get("school")
        async with session_factory() as session:
            query = select(Lead, School.name).join(School, School.id == Lead.school_id).order_by(Lead.id.desc()).limit(200)
            if school_id and school_id.isdigit():
                query = query.where(Lead.school_id == int(school_id))
            rows = (await session.execute(query)).all()
            result = []
            for lead, school_name in rows:
                status, reason, billable = lead_admin._status(lead)
                result.append({
                    "id": lead.id, "school": school_name, "subject": lead.subject, "contact_type": lead.contact_type,
                    "status": lead.status, "attempts": lead.attempts, "error": lead.last_error, "channels": lead.delivered_via,
                    "test": lead.is_test, "created": (lead.created_at + lead_admin.MSK).strftime("%Y-%m-%d %H:%M"),
                    "paid": lead.paid_at.date().isoformat() if lead.paid_at else "", "first_payment": lead.first_payment,
                    "excluded": lead.excluded_reason, "billable": billable and lead.status == "sent" and not lead.is_test,
                })
            return web.json_response({"leads": result})

    async def lead_action(request):
        lead_id, action = int(request.match_info["id"]), request.match_info["action"]
        data = await request.json() if request.can_read_body else {}
        if not isinstance(data, dict):
            raise web.HTTPBadRequest()
        async with session_factory() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                raise web.HTTPNotFound()
            if action == "retry":
                school, cfg = await session.get(School, lead.school_id), await session.get(LeadSchool, lead.school_id)
                if lead.status == "withdrawn":
                    return web.json_response({"error": "Заявка отозвана учеником."}, status=400)
                lead.attempts = 0
                ok = await leads.deliver_lead(session, lead_settings, lead, school, cfg)
                return web.json_response({"ok": ok, "error": lead.last_error})
            if action == "paid":
                payment = data.get("first_payment", 0)
                if isinstance(payment, bool) or not isinstance(payment, int) or payment < 0:
                    return web.json_response({"error": "Первый платёж — целое число рублей."}, status=400)
                lead.paid_at, lead.first_payment = datetime.utcnow(), payment
            elif action == "unpaid":
                lead.paid_at, lead.first_payment = None, 0
            elif action == "exclude":
                reason = str(data.get("reason") or "").strip()[:200]
                if not reason:
                    return web.json_response({"error": "Укажи причину исключения."}, status=400)
                lead.excluded_reason = reason
            elif action == "include":
                lead.excluded_reason = ""
            else:
                raise web.HTTPNotFound()
            await session.commit()
            return web.json_response({"ok": True})

    async def report(request):
        school_id, month = request.query.get("school", ""), request.query.get("month", "")
        if not school_id.isdigit() or not re.fullmatch(r"\d{4}-\d{2}", month):
            raise web.HTTPBadRequest()
        async with session_factory() as session:
            school = await session.get(School, int(school_id))
            if school is None:
                raise web.HTTPNotFound()
            cfg = await session.get(LeadSchool, school.id)
            lines, summary, sales = await lead_admin.month_report(session, school, cfg, month)
        body = lead_admin.report_csv(school.name, month, lines, summary, sales)
        return web.Response(body=body, content_type="text/csv", charset="utf-8",
                            headers={"Content-Disposition": f'attachment; filename="report-{school.id}-{month}.csv"'})

    app.add_routes([
        web.get("/api/partners", overview),
        web.post("/api/partners/{id:\\d+}/save", save),
        web.post("/api/partners/{id:\\d+}/switch", switch),
        web.post("/api/partners/{id:\\d+}/secret", secret),
        web.post("/api/partners/{id:\\d+}/test", test),
        web.post("/api/partners/global", global_flag),
        web.get("/api/leads", leads_list),
        web.post("/api/leads/{id:\\d+}/{action}", lead_action),
        web.get("/api/lead-report", report),
    ])
