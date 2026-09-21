import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot.db import delete_user_data
from egeshka_bot.models import Base, Event, Review, ReviewCriterionScore, User


def test_delete_user_data_removes_profile_reviews_criteria_and_events():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            user = User(telegram_id=123456)
            session.add(user)
            await session.flush()
            review = Review(user_id=user.id, school_id=1, score=4.5)
            session.add(review)
            await session.flush()
            session.add(ReviewCriterionScore(review_id=review.id, criterion="explanation", score=4.5))
            session.add(Event(telegram_id=123456, event_name="start"))
            session.add(Event(telegram_id=999999, event_name="start"))
            await session.commit()

            result = await delete_user_data(session, 123456)
            assert result == {"users": 1, "reviews": 1, "events": 1}
            assert await session.scalar(select(func.count(User.id))) == 0
            assert await session.scalar(select(func.count(Review.id))) == 0
            assert await session.scalar(select(func.count(ReviewCriterionScore.review_id))) == 0
            assert await session.scalar(select(func.count(Event.id))) == 1

            assert await delete_user_data(session, 123456) == {"users": 0, "reviews": 0, "events": 0}

        await engine.dispose()

    asyncio.run(scenario())
