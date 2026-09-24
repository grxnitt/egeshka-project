import asyncio
import json
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from egeshka_bot.bot import _proof_admin_copies, approved_reviews_text, erase_review_proof
from egeshka_bot.models import Base, Review, User


class FakeBot:
    def __init__(self, undeletable=()):
        self.deleted = []
        self.undeletable = set(undeletable)

    async def delete_message(self, chat_id, message_id):
        if (chat_id, message_id) in self.undeletable:
            raise RuntimeError("message can't be deleted")
        self.deleted.append((chat_id, message_id))


def make_review(**extra):
    values = dict(
        proof_file_id="AgAC-file",
        proof_file_type="photo",
        proof_delete_after=object(),
        proof_admin_messages=json.dumps([[1, 10], [2, 20]]),
    )
    values.update(extra)
    return SimpleNamespace(**values)


def test_erase_review_proof_deletes_admin_copies_and_forgets_the_file():
    bot, review = FakeBot(), make_review()

    failed = asyncio.run(erase_review_proof(bot, review))

    assert failed == 0
    assert bot.deleted == [(1, 10), (2, 20)]
    assert review.proof_file_id is None and review.proof_file_type is None
    assert review.proof_delete_after is None and review.proof_admin_messages is None


def test_erase_review_proof_still_clears_data_when_a_copy_is_too_old():
    bot, review = FakeBot(undeletable={(2, 20)}), make_review()

    failed = asyncio.run(erase_review_proof(bot, review))

    assert failed == 1
    assert bot.deleted == [(1, 10)]
    assert review.proof_file_id is None


def test_broken_admin_copy_data_is_ignored():
    assert _proof_admin_copies(make_review(proof_admin_messages=None)) == []
    assert _proof_admin_copies(make_review(proof_admin_messages="not json")) == []
    assert _proof_admin_copies(make_review(proof_admin_messages=json.dumps([[1], "x", [3, 30]]))) == [(3, 30)]


def test_public_reviews_are_labelled_by_verification():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=1)
            session.add(user)
            await session.flush()
            session.add(Review(user_id=user.id, school_id=1, score=9, text_positive="ок", moderation_status="approved", verified=True))
            session.add(Review(user_id=user.id, school_id=1, score=7, text_positive="норм", moderation_status="approved", verified=False))
            await session.commit()
            text = await approved_reviews_text(session, 1)
        await engine.dispose()
        return text

    text = asyncio.run(scenario())
    assert "✅ подтверждённый" in text
    assert "без подтверждения" in text
