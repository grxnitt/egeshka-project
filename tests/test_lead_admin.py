import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot import lead_admin, leads
from egeshka_bot.config import Settings
from egeshka_bot.models import Base, Lead, LeadSchool, School


def test_lead_set_parses_keys_and_rejects_bad_values():
    name, values = lead_admin.parse_set("/lead_set Умскул | name=ООО «Умскул» | inn=7700000000 | contacts=phone, vk | "
                                        "tg=-1001234 | rate=300 | pd=dpo@school.ru")
    assert name == "Умскул"
    assert values == {"legal_name": "ООО «Умскул»", "inn": "7700000000", "contact_types": "phone,vk", "tg_chat_id": "-1001234",
                      "rate": 300, "pd_contact": "dpo@school.ru"}
    for bad in ("/lead_set", "/lead_set Умскул | inn=123", "/lead_set Умскул | contacts=fax", "/lead_set Умскул | color=red",
                "/lead_set Умскул | webhook=http://insecure", "/lead_set Умскул | rate=много", "/lead_set Умскул | inn"):
        with pytest.raises(ValueError):
            lead_admin.parse_set(bad)


def test_a_school_cannot_be_switched_on_half_configured():
    cfg = LeadSchool(legal_name="", inn="", delivery_email="", webhook_url="", tg_chat_id="", pd_contact="", rate=0)
    assert len(lead_admin.missing_for_launch(cfg)) == 5
    cfg = LeadSchool(legal_name="ООО", inn="7700000000", delivery_email="", webhook_url="", tg_chat_id="-100", pd_contact="dpo", rate=300)
    assert lead_admin.missing_for_launch(cfg) == []


def test_webhook_signature_is_hmac_of_the_raw_body():
    body = b'{"lead_id": 1}'
    expected = hmac.new(b"key", body, hashlib.sha256).hexdigest()
    assert leads.sign_webhook("key", body) == f"sha256={expected}"


async def _db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(School(id=1, name="Школа", description="", official_url="https://school.example", subjects="Русский", monthly_price_from=0))
        session.add(LeadSchool(school_id=1, enabled=True, legal_name="ООО", inn="7700000000", tg_chat_id="-100", pd_contact="dpo", rate=300))
        await session.commit()
    return sessions


def _lead(lead_id, at, delivered=True, **extra):
    base = dict(id=lead_id, school_id=1, name="", contact_type="phone", contact="", contact_hash=str(lead_id), subject="Русский",
                consent_version="v", consent_at=at, status="sent", sent_at=at if delivered else None, created_at=at, delivered_via="telegram")
    base.update(extra)
    return Lead(**base)


def test_monthly_report_pays_only_valid_leads_and_hides_contacts():
    async def scenario():
        sessions = await _db()
        sent = datetime(2026, 11, 10, 9, 0)
        async with sessions() as session:
            session.add_all([
                _lead(1, sent),                                                         # valid
                _lead(2, sent, withdrawn_at=sent + timedelta(hours=2), status="withdrawn"),   # withdrawn fast -> free
                _lead(3, sent, withdrawn_at=sent + timedelta(days=3), status="withdrawn"),    # withdrawn late -> paid
                _lead(4, sent, excluded_reason="действующий ученик"),                   # dispute accepted
                _lead(5, sent, is_test=True),                                           # admin test -> not listed
                _lead(6, datetime(2026, 12, 1, 9, 0)),                                  # next month
                _lead(7, datetime(2026, 11, 10, 9, 0), delivered=False, status="failed"),                                        # never delivered
            ])
            await session.commit()
            school = await session.get(School, 1)
            cfg = await session.get(LeadSchool, 1)
            lines, summary, sales = await lead_admin.month_report(session, school, cfg, "2026-11")
        assert [line[0] for line in lines] == [1, 2, 3, 4]
        assert summary == {"delivered": 4, "excluded": 2, "valid": 2, "rate": 300, "leads_total": 600,
                           "sales": 0, "bonus_total": 0, "total": 600}
        assert lines[0][1] == "10.11.2026 12:00" and lines[0][4] == "Telegram"  # Moscow time, channel label
        data = lead_admin.report_csv("Школа", "2026-11", lines, summary, sales).decode("utf-8-sig")
        assert "Итого к оплате, ₽;600" in data and "@" not in data and "+7" not in data
    asyncio.run(scenario())


def test_months_are_counted_in_moscow_time():
    start, end = lead_admin.month_bounds("2026-12")
    assert start == datetime(2026, 11, 30, 21, 0) and end == datetime(2026, 12, 31, 21, 0)
    with pytest.raises(ValueError):
        lead_admin.month_bounds("2026-13")


def test_stats_count_today_month_failures_and_withdrawals_without_tests():
    async def scenario():
        sessions = await _db()
        now = datetime(2026, 11, 20, 12, 0)
        async with sessions() as session:
            session.add_all([_lead(1, now), _lead(2, now - timedelta(days=5), delivered=False, status="failed"),
                             _lead(3, now, withdrawn_at=now), _lead(4, now, is_test=True)])
            await session.commit()
            text = await lead_admin.stats_text(session, now)
        assert "• Школа: 2 / 3 · 1 · 1" in text and "Всего за месяц: 3" in text
    asyncio.run(scenario())


def test_a_test_lead_skips_duplicate_check_and_admins_hear_about_undeliverable_leads(monkeypatch):
    sent = []

    async def fake_send(settings, chat_id, text):
        sent.append((chat_id, text))
        return "HTTP 400"

    monkeypatch.setattr(leads, "_telegram_send", fake_send)

    async def scenario():
        sessions = await _db()
        settings = Settings(bot_token="x", admin_ids="42")
        async with sessions() as session:
            school = await session.get(School, 1)
            cfg = await session.get(LeadSchool, 1)
            clean = {"name": "Тест", "contact_type": "phone", "contact": "+79000000000", "subject": "Русский", "guardian": False, "source": "admin_test"}
            first, _, _ = await leads.create_lead(session, school, clean, is_test=True)
            second, _, duplicate = await leads.create_lead(session, school, clean, is_test=True)
            assert not duplicate and first.id != second.id and second.is_test
            for _ in range(leads.MAX_ATTEMPTS):
                await leads.deliver_lead(session, settings, second, school, cfg)
        alerts = [text for chat, text in sent if chat == 42]
        assert len(alerts) == 1 and f"№{second.id}" in alerts[0]
        assert any("ТЕСТОВАЯ ЗАЯВКА" in text for chat, text in sent if chat == "-100")
    asyncio.run(scenario())


def test_admin_commands_are_registered():
    from aiogram import Dispatcher

    async def build():
        dp = Dispatcher()
        lead_admin.register(dp, None, Settings(bot_token="x"))
        return ({handler.callback.__name__ for handler in dp.message.handlers}, {h.callback.__name__ for h in dp.my_chat_member.handlers})
    names, member = asyncio.run(build())
    assert "added_to_group" in member
    assert {"lead_set", "lead_test", "lead_on", "lead_off", "leads_stats", "lead_report", "lead_exclude", "lead_secret", "lead_paid", "lead_unpaid"} <= names


def test_bonus_is_fixed_or_a_percent_with_a_floor():
    lead = Lead(first_payment=20000)
    assert lead_admin.sale_bonus(LeadSchool(bonus_fixed=1500, bonus_percent=0, bonus_min=0), lead) == 1500
    assert lead_admin.sale_bonus(LeadSchool(bonus_fixed=0, bonus_percent=15, bonus_min=1000), lead) == 3000
    assert lead_admin.sale_bonus(LeadSchool(bonus_fixed=0, bonus_percent=15, bonus_min=1000), Lead(first_payment=4000)) == 1000
    assert lead_admin.parse_set("/lead_set Школа | percent=15 | min=1000")[1] == {"bonus_percent": 15, "bonus_min": 1000}
    with pytest.raises(ValueError):
        lead_admin.parse_set("/lead_set Школа | percent=150")


def test_paid_students_are_billed_in_the_month_the_school_reported_them():
    async def scenario():
        sessions = await _db()
        async with sessions() as session:
            cfg = await session.get(LeadSchool, 1)
            cfg.rate, cfg.bonus_fixed = 400, 1500
            october = datetime(2026, 10, 25, 9, 0)
            session.add_all([
                _lead(1, october, paid_at=datetime(2026, 11, 3, 9, 0)),                  # delivered in Oct, paid in Nov
                _lead(2, datetime(2026, 11, 5, 9, 0), paid_at=datetime(2026, 11, 20, 9, 0)),
                _lead(3, datetime(2026, 11, 6, 9, 0), paid_at=datetime(2026, 11, 7, 9, 0), excluded_reason="действующий ученик"),
                _lead(4, datetime(2026, 11, 6, 9, 0), paid_at=datetime(2026, 11, 7, 9, 0), is_test=True),
            ])
            await session.commit()
            school = await session.get(School, 1)
            lines, summary, sales = await lead_admin.month_report(session, school, cfg, "2026-11")
        assert [row[0] for row in sales] == [1, 2] and all(row[4] == 1500 for row in sales)
        assert summary["valid"] == 1 and summary["leads_total"] == 400  # lead 3 is excluded, lead 1 was delivered in October
        assert summary["sales"] == 2 and summary["bonus_total"] == 3000 and summary["total"] == 3400
    asyncio.run(scenario())
