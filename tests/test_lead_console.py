"""School partnerships in the moderation console: the guards that protect students and the global switch."""
import asyncio
import re
from datetime import date

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot import leads_api
from egeshka_bot.models import Base, Lead, LeadSchool, School
from reviews_service import admin_app
from reviews_service.config import Settings
from reviews_service.lead_admin_api import FieldError, clean_school_update
from reviews_service.lead_settings import LeadSettings
from reviews_service.models import SiteFlag

LOCAL = {"Host": "127.0.0.1:8090"}


def run(coro):
    return asyncio.run(coro)


def test_school_form_validation():
    ok = clean_school_update({"legal_name": " ООО «Школа» ", "inn": "7700000000", "policy_url": "https://school.ru/p",
                              "contact_types": ["email", "phone", "bogus"], "rate": "300", "agreement_date": "2026-10-01"})
    assert ok["legal_name"] == "ООО «Школа»" and ok["contact_types"] == "phone,email" and ok["rate"] == 300
    assert ok["agreement_date"] == date(2026, 10, 1)
    for bad in ({"inn": "123"}, {"policy_url": "http://insecure.ru"}, {"webhook_url": "ftp://x"}, {"delivery_email": "nope"},
                {"tg_chat_id": "abc"}, {"contact_types": []}, {"rate": -1}, {"bonus_percent": 150}, {"rate": True},
                {"agreement_date": "1 октября"}, {"agreement_date": "2099-01-01"}, {"notes": "x" * 5000}):
        with pytest.raises(FieldError):
            clean_school_update(bad)


async def make_env(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'leads.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(lambda sync: SiteFlag.__table__.create(sync))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(School(id=1, name="Школа", description="", official_url="https://school.example", subjects="Русский", monthly_price_from=0))
        session.add(LeadSchool(school_id=1))
        session.add(SiteFlag(key="leads_enabled", value=False))
        await session.commit()
    settings = Settings(hmac_secret="x" * 40, proof_dir=str(tmp_path / "proofs"), database_url="sqlite://")
    return engine, sessions, settings


def test_a_school_is_switched_on_only_when_complete_and_the_global_switch_is_separate(tmp_path):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        admin = TestClient(TestServer(admin_app.create_app(settings, sessions)))
        await admin.start_server()
        try:
            page = await (await admin.get("/", headers=LOCAL)).text()
            h = {**LOCAL, "X-Admin-Token": re.search(r'admin-token" content="([^"]+)', page).group(1)}
            listing = await (await admin.get("/api/partners", headers=LOCAL)).json()
            assert listing["global"]["enabled"] is False
            row = listing["schools"][0]
            assert row["enabled"] is False and "дата договора со школой" in row["missing"]

            # cannot be switched on half configured
            r = await admin.post("/api/partners/1/switch", json={"enabled": True}, headers=h)
            assert r.status == 400 and "не хватает" in (await r.json())["error"]
            # every change needs the page token
            assert (await admin.post("/api/partners/1/save", json={}, headers=LOCAL)).status == 403

            full = {"legal_name": "ООО «Школа»", "inn": "7700000000", "delivery_email": "z@school.ru", "pd_contact": "dpo@school.ru",
                    "agreement_date": "2026-10-01", "contact_types": ["phone", "email"], "rate": 0}
            r = await admin.post("/api/partners/1/save", json=full, headers=h)
            assert r.status == 200 and (await r.json())["school"]["missing"] == []
            r = await admin.post("/api/partners/1/switch", json={"enabled": True}, headers=h)
            assert (await r.json())["school"]["enabled"] is True          # free of charge (rate 0) is allowed

            # editing a live school so that it becomes incomplete takes it off the air
            r = await admin.post("/api/partners/1/save", json={"delivery_email": ""}, headers=h)
            assert (await r.json())["school"]["enabled"] is False

            # the global switch needs both confirmations and the word
            assert (await admin.post("/api/partners/global", json={"enabled": True}, headers=h)).status == 400
            assert (await admin.post("/api/partners/global", json={"enabled": True, "rkn": True, "tax": True, "word": "да"}, headers=h)).status == 400
            lead_settings = LeadSettings(settings)
            assert await lead_settings.refresh(sessions) is False
            r = await admin.post("/api/partners/global", json={"enabled": True, "rkn": True, "tax": True, "word": "ВКЛЮЧИТЬ"}, headers=h)
            assert (await r.json())["global"]["enabled"] is True
            assert await lead_settings.refresh(sessions) is True          # the leads service sees it without a restart
            await admin.post("/api/partners/global", json={"enabled": False}, headers=h)
            assert await lead_settings.refresh(sessions) is False
        finally:
            await admin.close()
            await engine.dispose()
    run(scenario())


def test_public_leads_api_obeys_the_global_and_the_school_switch(tmp_path):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        async with sessions() as session:
            cfg = await session.get(LeadSchool, 1)
            cfg.enabled, cfg.legal_name, cfg.inn, cfg.delivery_email, cfg.pd_contact = True, "ООО", "7700000000", "z@s.ru", "dpo"
            await session.commit()
        lead_settings = LeadSettings(settings)
        client = TestClient(TestServer(leads_api.create_app(lead_settings, sessions)))
        await client.start_server()
        try:
            h = {"Origin": "https://egematch.ru"}
            assert (await (await client.get("/api/lead-schools", headers=h)).json())["schools"] == []     # global switch off
            lead_settings.leads_enabled = True
            names = [s["name"] for s in (await (await client.get("/api/lead-schools", headers=h)).json())["schools"]]
            assert names == ["Школа"]
            async with sessions() as session:
                (await session.get(LeadSchool, 1)).enabled = False
                await session.commit()
            assert (await (await client.get("/api/lead-schools", headers=h)).json())["schools"] == []     # school switched off
        finally:
            await client.close()
            await engine.dispose()
    run(scenario())


def test_console_lists_never_show_a_student_name_or_contact(tmp_path):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        async with sessions() as session:
            from datetime import datetime
            session.add(Lead(school_id=1, name="Иван Иванов", contact_type="phone", contact="+79001234567", contact_hash="h",
                             subject="Русский", consent_version="v", consent_at=datetime.utcnow(), status="sent"))
            await session.commit()
        admin = TestClient(TestServer(admin_app.create_app(settings, sessions)))
        await admin.start_server()
        try:
            data = await (await admin.get("/api/leads", headers=LOCAL)).json()
            flat = str(data)
            assert "Иван" not in flat and "79001234567" not in flat
            assert data["leads"][0]["school"] == "Школа" and not {"name", "contact"} & set(data["leads"][0])
            page = await (await admin.get("/", headers=LOCAL)).text()
            h = {**LOCAL, "X-Admin-Token": re.search(r'admin-token" content="([^"]+)', page).group(1)}
            r = await admin.post("/api/partners/1/test", json={}, headers=h)
            assert r.status == 400                                   # no delivery channel yet: nothing is created
            await admin.post("/api/partners/1/save", json={"delivery_email": "z@school.ru"}, headers=h)
            result = await (await admin.post("/api/partners/1/test", json={}, headers=h)).json()
            assert result["ok"] is False and "email" in result["error"]   # no SMTP in tests: reported, not hidden
            async with sessions() as session:
                test_lead = (await session.execute(text("select is_test from leads where id = :i"), {"i": result["id"]})).scalar_one()
                assert bool(test_lead) is True                           # test leads never count in reports
        finally:
            await admin.close()
            await engine.dispose()
    run(scenario())


def test_console_page_renders_text_only():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "reviews_service" / "admin_static" / "partners.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script and "eval(" not in script
