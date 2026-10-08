import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot import leads
from egeshka_bot.config import Settings
from egeshka_bot.leads_api import create_app
from egeshka_bot.models import Base, Lead, LeadSchool, School


def test_contacts_are_normalised_and_bad_ones_rejected():
    assert leads.normalize_phone("8 (900) 123-45-67") == "+79001234567"
    assert leads.normalize_phone("+7 900 123 45 67") == "+79001234567"
    assert leads.normalize_phone("9001234567") == "+79001234567"
    assert leads.normalize_phone("12345") is None and leads.normalize_phone("+7 100 123 45 67") is None
    assert leads.normalize_telegram("https://t.me/ivan_petrov") == "@ivan_petrov" and leads.normalize_telegram("@ab") is None
    assert leads.normalize_vk("https://vk.com/id12345") == "https://vk.com/id12345" and leads.normalize_vk("vk.com/a b") is None
    assert leads.normalize_vk("m.vk.com/ivan.petrov/") == "https://vk.com/ivan.petrov"
    assert leads.normalize_vk("https://vk.com/profile.php?id=777") == "https://vk.com/id777"
    for not_a_link in ("ivan", "id12345", "@ivan", "https://example.com/ivan", "https://vk.com/"):
        assert leads.normalize_vk(not_a_link) is None  # a VK contact must be a profile link
    assert leads.normalize_email(" Anya@Mail.RU ") == "anya@mail.ru"
    for bad in ("anya", "anya@", "anya@mail", "a b@mail.ru", "a@@mail.ru"):
        assert leads.normalize_email(bad) is None


def cfg(**kw):
    base = dict(enabled=True, legal_name="ООО «Школа»", inn="7700000000", policy_url="https://school.example/policy",
                contact_types="phone,telegram", delivery_email="", webhook_url="", tg_chat_id="")
    base.update(kw)
    return SimpleNamespace(**base)


def body(**kw):
    base = dict(name="Аня", contact_type="phone", contact="8 900 123 45 67", subject="Русский", consent=True,
                consent_version=leads.CONSENT_VERSION, applicant="adult", website="")
    base.update(kw)
    return base


def test_request_needs_consent_a_valid_subject_and_an_accepted_contact_type():
    assert leads.clean_request(body(), cfg())["contact"] == "+79001234567"
    for bad in (body(consent=False), body(consent_version="old"), body(website="x"), body(name="A"),
                body(contact_type="vk", contact="vk.com/ivan"), body(contact="123"), body(subject="Астрология"),
                body(applicant=""), body(applicant="child")):
        with pytest.raises(leads.LeadError):
            leads.clean_request(bad, cfg())


def test_consent_text_names_the_school_and_what_is_passed():
    text = leads.consent_text("Школа", cfg())
    assert "ООО «Школа»" in text and "ИНН 7700000000" in text and "имени" in text and "предмет" in text and "отозвать" in text
    operator = SimpleNamespace(operator_name="Иванов И. И., ИНН 123", operator_contact="help@example.ru")
    full = leads.consent_text("Школа", cfg(policy_url="https://school.example/policy"), operator)
    for required in ("Иванов И. И.", "help@example.ru", "https://school.example/policy", "https://egematch.ru/privacy", "365", "18 лет"):
        assert required in full  # operator, withdrawal contact, both policies, retention and the age line (art. 9(4) of 152-FZ)


def test_a_guardian_request_is_marked_and_a_vk_school_gets_the_link():
    clean = leads.clean_request(body(applicant="guardian", contact_type="vk", contact="vk.com/ivan"), cfg(contact_types="vk,email"))
    assert clean["guardian"] is True and clean["contact"] == "https://vk.com/ivan"
    mail = leads.clean_request(body(contact_type="email", contact="A@B.ru"), cfg(contact_types="email"))
    assert mail["contact"] == "a@b.ru" and mail["guardian"] is False


def test_rate_limiter_blocks_the_sixth_request_in_an_hour_and_recovers():
    limiter = leads.RateLimiter()
    assert all(limiter.allow("1.2.3.4", now=10 + i) for i in range(5)) and not limiter.allow("1.2.3.4", now=20)
    assert limiter.allow("1.2.3.4", now=4000) and limiter.allow("5.6.7.8", now=20)


async def make_db(enabled=True, **school_cfg):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(School(id=1, name="Школа", description="", official_url="https://school.example", subjects="Русский", monthly_price_from=0))
        session.add(LeadSchool(school_id=1, enabled=enabled, legal_name="ООО «Школа»", inn="7700000000",
                               contact_types="phone,telegram", webhook_url="http://127.0.0.1:1/x", **school_cfg))
        await session.commit()
    return sessions


def test_duplicates_are_not_stored_twice_and_withdrawal_wipes_personal_data():
    async def scenario():
        sessions = await make_db()
        async with sessions() as session:
            school = await session.get(School, 1)
            clean = leads.clean_request(body(), cfg())
            lead, token, duplicate = await leads.create_lead(session, school, clean)
            assert not duplicate and token and lead.consent_version == leads.CONSENT_VERSION
            again, no_token, duplicate = await leads.create_lead(session, school, clean)
            assert duplicate and again.id == lead.id and no_token == ""
            later = await leads.create_lead(session, school, clean, now=datetime.utcnow() + timedelta(days=91))
            assert later[2] is False  # outside the 90-day window it is a new request
            assert await leads.withdraw(session, Settings(bot_token="x"), token)
            wiped = (await session.execute(select(Lead).where(Lead.id == lead.id))).scalar_one()
            assert (wiped.name, wiped.contact, wiped.status) == ("", "", "withdrawn")
            assert not await leads.withdraw(session, Settings(bot_token="x"), token)
    asyncio.run(scenario())


def test_old_leads_are_purged():
    async def scenario():
        sessions = await make_db()
        async with sessions() as session:
            school = await session.get(School, 1)
            await leads.create_lead(session, school, leads.clean_request(body(), cfg()), now=datetime.utcnow() - timedelta(days=400))
            assert await leads.purge_old(session) == 1
    asyncio.run(scenario())


def test_api_is_off_by_default_and_a_disabled_school_gets_nothing():
    async def scenario():
        sessions = await make_db(enabled=False)
        for flag in (False, True):
            app = create_app(Settings(bot_token="x", leads_enabled=flag), sessions)
            async with TestClient(TestServer(app)) as client:
                assert (await (await client.get("/api/lead-schools")).json())["schools"] == []
                response = await client.post("/api/leads", json=body(school="Школа"))
                assert response.status == 404
    asyncio.run(scenario())


def test_api_creates_a_lead_when_enabled_and_reports_a_failed_delivery_for_retry():
    async def scenario():
        sessions = await make_db()
        app = create_app(Settings(bot_token="", leads_enabled=True), sessions)
        async with TestClient(TestServer(app)) as client:
            listed = (await (await client.get("/api/lead-schools", headers={"Origin": "https://egematch.ru"})).json())["schools"]
            assert listed == [{"name": "Школа", "contactTypes": ["phone", "telegram"]}]
            consent = await (await client.get("/api/lead-consent", params={"school": "Школа"})).json()
            assert consent["version"] == leads.CONSENT_VERSION and "ООО «Школа»" in consent["text"]
            bad = await client.post("/api/leads", json=body(school="Школа", consent=False))
            assert bad.status == 400
            ok = await client.post("/api/leads", json=body(school="Школа"))
            data = await ok.json()
            assert ok.status == 200 and data["ok"] and data["token"]
            repeat = await (await client.post("/api/leads", json=body(school="Школа"))).json()
            assert repeat == {"ok": True, "duplicate": True}
        async with sessions() as session:
            lead = (await session.execute(select(Lead))).scalar_one()
            assert lead.status == "failed" and lead.attempts == 1 and lead.last_error  # webhook unreachable -> retried later
    asyncio.run(scenario())


def test_site_form_is_wired_but_switched_off_until_an_api_address_is_set():
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "web"
    assert "window.EGE_LEADS_API = '';" in (web / "analytics-config.js").read_text(encoding="utf-8")
    assert "if(window.EGE_LEADS_API)" in (web / "analytics.js").read_text(encoding="utf-8")
    script = (web / "lead.js").read_text(encoding="utf-8")
    assert "a[data-choose-school]" in script and "innerHTML" not in script  # never builds markup from user input
    assert "https://api.egematch.ru" in (web / "vercel.json").read_text(encoding="utf-8")

def test_rate_limit_ignores_forged_forwarded_for_entries_and_withdraw_is_limited():
    async def scenario():
        sessions = await make_db()
        app = create_app(Settings(bot_token="", leads_enabled=True), sessions)
        async with TestClient(TestServer(app)) as client:
            # The proxy appends the real address LAST; a visitor can only forge the first entries.
            statuses = []
            for forged in range(8):
                response = await client.post(
                    "/api/leads", json=body(school="Школа", name=f"Имя {forged}", phone=f"+7900000{forged:04d}"),
                    headers={"X-Forwarded-For": f"10.0.0.{forged}, 203.0.113.7"},
                )
                statuses.append(response.status)
            assert statuses[-1] == 429, statuses  # the same real address hits the limit despite changing forged entries
            codes = [(await client.post("/api/leads/withdraw", json={"token": "x" * 30},
                                         headers={"X-Forwarded-For": "198.51.100.9"})).status for _ in range(25)]
            assert codes[0] == 200 and codes[-1] == 429
    asyncio.run(scenario())
