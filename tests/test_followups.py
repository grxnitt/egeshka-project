import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot import followups
from egeshka_bot.db import delete_user_data
from egeshka_bot.models import Base, Followup


def run(coro):
    async def wrapper():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            return await coro(session)
    return asyncio.run(wrapper())


def test_school_ids_round_trip():
    assert followups.decode_schools(followups.encode_schools([3, 12, 7])) == [3, 12, 7]
    assert followups.decode_schools("") == []


def test_reminder_is_due_after_two_months_and_repeats_up_to_the_limit():
    async def scenario(session):
        start = datetime(2026, 10, 10)
        await followups.subscribe(session, 111, "Химия", [1, 2, 3], now=start)
        assert await followups.due(session, now=start + timedelta(days=59)) == []
        for number in range(1, followups.MAX_ROUNDS + 1):
            now = start + timedelta(days=60 * number)
            items = await followups.due(session, now=now)
            assert len(items) == 1
            await followups.mark_sent(session, items[0], now=now)
        assert await followups.due(session, now=start + timedelta(days=1000)) == []
    run(scenario)


def test_reminders_stop_after_the_exam_season():
    async def scenario(session):
        start = datetime(2027, 5, 10)
        await followups.subscribe(session, 111, "Химия", [1], now=start)
        item = (await followups.due(session, now=start + timedelta(days=61)))[0]
        await followups.mark_sent(session, item, now=datetime(2027, 6, 25))
        assert item.active is False
    run(scenario)


def test_resubscribing_replaces_the_old_reminder_and_stop_turns_it_off():
    async def scenario(session):
        await followups.subscribe(session, 111, "Химия", [1])
        await followups.subscribe(session, 111, "Химия", [2])
        active = (await session.execute(select(Followup).where(Followup.active == True))).scalars().all()
        assert len(active) == 1
        assert await followups.stop_all(session, 111) == 1
        assert await followups.stop_all(session, 111) == 0
    run(scenario)


def test_deleting_user_data_removes_reminders():
    async def scenario(session):
        await followups.subscribe(session, 111, "Химия", [1])
        await followups.subscribe(session, 222, "Физика", [1])
        await delete_user_data(session, 111)
        rest = (await session.execute(select(Followup))).scalars().all()
        assert [item.telegram_id for item in rest] == [222]
    run(scenario)


def test_exam_season_ends_in_june():
    assert followups.exam_end(date(2026, 10, 10)) == date(2027, 6, 30)
    assert followups.exam_end(date(2027, 3, 1)) == date(2027, 6, 30)
