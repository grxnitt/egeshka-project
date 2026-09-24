import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot.bot import (
    ReviewCount,
    approved_review_stats,
    blend_rating,
    review_count_label,
    weighted_review_stats,
)
from egeshka_bot.models import Base, Review, User


def test_verified_reviews_weigh_more_than_unverified():
    average, count = weighted_review_stats([(10, True), (4, False)])

    assert average == pytest.approx((10 + 4 * 0.4) / 1.4)
    assert float(count) == pytest.approx(1.4)
    assert (count.verified, count.unverified, count.total) == (1, 1, 2)


def test_only_verified_reviews_behave_like_a_plain_average():
    average, count = weighted_review_stats([(8, True), (6, True), (10, True)])

    assert average == pytest.approx(8.0)
    assert float(count) == 3.0


def test_unverified_pile_cannot_outvote_confirmed_students():
    average, count = weighted_review_stats([(5, True), (5, True)] + [(10, False)] * 20)

    assert float(count) == pytest.approx(5.0)  # 2 verified + capped unverified weight of 3
    assert average == pytest.approx((5 * 2 + 10 * 3) / 5)


def test_unverified_alone_are_capped_to_a_single_review_of_weight():
    average, count = weighted_review_stats([(10, False)] * 10)

    assert average == 10
    assert float(count) == pytest.approx(1.0)


def test_no_reviews_returns_nothing():
    average, count = weighted_review_stats([])

    assert average is None and float(count) == 0 and not count


def test_blend_uses_effective_weight_for_the_three_review_threshold():
    editorial_only, preliminary = blend_rating(7.0, 10.0, ReviewCount(2.9, 2, 1))
    blended, _ = blend_rating(7.0, 10.0, ReviewCount(3.4, 3, 1))

    assert editorial_only == 7.0 and preliminary
    assert blended > 7.0


def test_review_count_label_shows_raw_counts():
    assert review_count_label(5) == "5 подтверждённых отзывов"
    assert review_count_label(ReviewCount(4.4, 4, 1)) == "5 отзывов, из них подтверждённых 4"


def test_approved_review_stats_mixes_verified_and_unverified_but_skips_pending():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=1)
            session.add(user)
            await session.flush()
            for score, verified, status in ((9, True, "approved"), (5, False, "approved"), (1, False, "pending"), (2, True, "rejected")):
                session.add(Review(user_id=user.id, school_id=1, score=score, verified=verified, moderation_status=status))
            await session.commit()
            result = await approved_review_stats(session, 1)
        await engine.dispose()
        return result

    average, count = asyncio.run(scenario())

    assert average == pytest.approx((9 + 5 * 0.4) / 1.4)
    assert (count.verified, count.unverified) == (1, 1)
