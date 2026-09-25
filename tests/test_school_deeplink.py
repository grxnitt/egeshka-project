import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update

from egeshka_bot.bot import CONSENT_VERSION, setup
from egeshka_bot.config import Settings
from egeshka_bot.db import init_db
from egeshka_bot.models import User


class RecordingBot(Bot):
    def __init__(self):
        super().__init__("123456:TEST-TOKEN")
        self.calls = []

    async def __call__(self, method, request_timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=99, date=datetime.now(), chat=Chat(id=5, type="private"))
        return True


def start_update(text):
    return Update.model_validate({
        "update_id": 1,
        "message": {
            "message_id": 1, "date": 1_700_000_000, "chat": {"id": 5, "type": "private"},
            "from": {"id": 5, "is_bot": False, "first_name": "Тест"}, "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
        },
    })


def open_deeplink(tmp_path, payload):
    async def scenario():
        engine, sessions = await init_db(f"sqlite+aiosqlite:///{tmp_path}/deeplink.db")
        async with sessions() as session:
            session.add(User(telegram_id=5, consent_at=datetime.utcnow(), consent_version=CONSENT_VERSION))
            await session.commit()
        bot, dp = RecordingBot(), Dispatcher()
        await setup(dp, sessions, Settings(bot_token="123456:TEST-TOKEN", admin_ids="777"))
        await dp.feed_update(bot, start_update(f"/start {payload}"))
        await engine.dispose()
        await bot.session.close()
        return bot.calls

    return asyncio.run(scenario())


def test_school_deeplink_opens_the_school_card_with_its_keyboard(tmp_path):
    calls = open_deeplink(tmp_path, "school_umskul")

    assert len(calls) == 1
    assert "Умскул" in calls[0].text
    assert calls[0].reply_markup is not None


def test_unknown_school_deeplink_falls_back_to_the_welcome_menu(tmp_path):
    calls = open_deeplink(tmp_path, "school_does_not_exist")

    assert len(calls) == 1
    assert "Привет! Я ЕГЭ Мэтч" in calls[0].text
