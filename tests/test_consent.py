import asyncio
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot.bot import (
    CONSENT_VERSION,
    ConsentMiddleware,
    consent_exempt,
    consent_text,
    user_has_consent,
)
from egeshka_bot.config import Settings
from egeshka_bot.models import Base, User


def make_settings(**extra):
    return Settings(bot_token="123:abc", admin_ids="777", **extra)


async def make_sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def test_consent_screen_names_the_operator_and_the_deletion_command():
    text = consent_text(make_settings(operator_name="ИП Иванов И. И.", operator_contact="help@egematch.online"))

    assert "ИП Иванов И. И." in text and "help@egematch.online" in text
    assert "/delete_data" in text and "Telegram ID" in text


def test_deletion_and_consent_buttons_work_without_consent():
    assert consent_exempt(text="/delete_data") and consent_exempt(text="/start delete_data")
    assert consent_exempt(callback_data="consent:yes") and consent_exempt(callback_data="delete_data_confirm")
    assert not consent_exempt(text="/start") and not consent_exempt(callback_data="menu")


def test_gate_asks_for_consent_first_and_holds_the_original_update():
    async def scenario():
        engine, sessions = await make_sessions()
        gate = ConsentMiddleware(sessions, make_settings())
        message = FakeMessage("/start q_1_0_low_70_yes")
        called = []

        async def handler(event, data):
            called.append(event)
            return "handled"

        data = {"event_from_user": SimpleNamespace(id=5, is_bot=False), "event_update": "the-update"}
        result = await gate(handler, message, data)
        await engine.dispose()
        return gate, message, result, called

    gate, message, result, called = asyncio.run(scenario())

    assert result is None and called == []
    assert "Согласие на обработку данных" in message.answers[0][0]
    assert gate.pending[5] == "the-update"


def test_gate_lets_consented_users_admins_and_deletion_through():
    async def scenario():
        engine, sessions = await make_sessions()
        async with sessions() as session:
            session.add(User(telegram_id=1, consent_at=datetime.utcnow(), consent_version=CONSENT_VERSION))
            session.add(User(telegram_id=2, consent_at=datetime.utcnow(), consent_version="old-version"))
            await session.commit()
        settings = make_settings()
        gate = ConsentMiddleware(sessions, settings)
        results = {}

        async def handler(event, data):
            return "handled"

        def data_for(uid):
            return {"event_from_user": SimpleNamespace(id=uid, is_bot=False), "event_update": None}

        results["consented"] = await gate(handler, FakeMessage("/start"), data_for(1))
        results["old_version"] = await gate(handler, FakeMessage("/start"), data_for(2))
        results["admin"] = await gate(handler, FakeMessage("/start"), data_for(777))
        results["delete"] = await gate(handler, FakeMessage("/delete_data"), data_for(99))
        results["has_consent"] = await user_has_consent(sessions, 1)
        results["stale"] = await user_has_consent(sessions, 2)
        await engine.dispose()
        return results

    results = asyncio.run(scenario())

    assert results["consented"] == "handled" and results["admin"] == "handled" and results["delete"] == "handled"
    assert results["old_version"] is None  # text version changed, ask again
    assert results["has_consent"] is True and results["stale"] is False


def test_first_start_shows_consent_then_resumes_the_start_after_agreeing(tmp_path):
    from datetime import datetime as dt

    from aiogram import Bot, Dispatcher
    from aiogram.methods import SendMessage
    from aiogram.types import Chat, Message, Update

    from egeshka_bot.bot import setup
    from egeshka_bot.db import init_db

    class RecordingBot(Bot):
        def __init__(self):
            super().__init__("123456:TEST-TOKEN")
            self.calls = []

        async def __call__(self, method, request_timeout=None):
            self.calls.append(method)
            if isinstance(method, SendMessage) or type(method).__name__ == "EditMessageText":
                return Message(message_id=99, date=dt.now(), chat=Chat(id=5, type="private"))
            return True

    def sender():
        return {"id": 5, "is_bot": False, "first_name": "Тест"}

    def message_update(update_id, text, entities):
        return Update.model_validate({
            "update_id": update_id,
            "message": {
                "message_id": update_id, "date": 1_700_000_000, "chat": {"id": 5, "type": "private"},
                "from": sender(), "text": text, "entities": entities,
            },
        })

    async def scenario():
        engine, sessions = await init_db(f"sqlite+aiosqlite:///{tmp_path}/consent.db")
        bot, dp = RecordingBot(), Dispatcher()
        await setup(dp, sessions, make_settings())

        await dp.feed_update(bot, message_update(1, "/start", [{"type": "bot_command", "offset": 0, "length": 6}]))
        first = list(bot.calls)
        bot.calls.clear()

        yes = Update.model_validate({
            "update_id": 2,
            "callback_query": {
                "id": "cb1", "from": sender(), "chat_instance": "x", "data": "consent:yes",
                "message": {"message_id": 10, "date": 1_700_000_000, "chat": {"id": 5, "type": "private"}, "text": "consent"},
            },
        })
        await dp.feed_update(bot, yes)
        second = list(bot.calls)
        consented = await user_has_consent(sessions, 5)
        await engine.dispose()
        await bot.session.close()
        return first, second, consented

    first, second, consented = asyncio.run(scenario())

    assert len(first) == 1 and "Согласие на обработку данных" in first[0].text
    assert consented is True
    texts = [getattr(call, "text", "") or "" for call in second]
    assert any("согласие сохранено" in text for text in texts)
    assert len(second) >= 3  # confirmation edit, callback answer and the resumed /start reply
