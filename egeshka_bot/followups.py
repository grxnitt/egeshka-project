"""Opt-in follow-ups: every two months after a quiz the bot asks how the studies are going.

The answers go to the events table (no new personal data beyond the Telegram ID the bot already has) and later
feed the "students like you" matching and the calibration of the editorial weights.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Followup

INTERVAL_DAYS = 60
MAX_ROUNDS = 4


def exam_end(today: Optional[date] = None) -> date:
    """End of the exam season the student is preparing for (30 June)."""
    today = today or date.today()
    return date(today.year + 1 if today.month >= 7 else today.year, 6, 30)


def encode_schools(school_ids) -> str:
    return ".".join(str(int(item)) for item in school_ids)[:60]


def decode_schools(raw: str) -> List[int]:
    return [int(item) for item in (raw or "").split(".") if item.isdigit()]


async def subscribe(session: AsyncSession, telegram_id: int, subject: str, school_ids, now: Optional[datetime] = None) -> Followup:
    """Start (or restart) the reminders for this student and subject."""
    now = now or datetime.utcnow()
    await session.execute(update(Followup).where(Followup.telegram_id == telegram_id, Followup.subject == subject)
                          .values(active=False))
    item = Followup(telegram_id=telegram_id, subject=subject, school_ids=encode_schools(school_ids),
                    next_due_at=now + timedelta(days=INTERVAL_DAYS), created_at=now)
    session.add(item)
    await session.commit()
    return item


async def stop_all(session: AsyncSession, telegram_id: int) -> int:
    result = await session.execute(update(Followup).where(Followup.telegram_id == telegram_id, Followup.active == True)
                                   .values(active=False))
    await session.commit()
    return result.rowcount or 0


async def due(session: AsyncSession, now: Optional[datetime] = None) -> List[Followup]:
    now = now or datetime.utcnow()
    return list((await session.execute(
        select(Followup).where(Followup.active == True, Followup.next_due_at <= now).order_by(Followup.next_due_at).limit(50)
    )).scalars())


async def mark_sent(session: AsyncSession, item: Followup, now: Optional[datetime] = None) -> None:
    """Schedule the next round, or finish when the rounds or the exam season are over."""
    now = now or datetime.utcnow()
    item.round += 1
    item.next_due_at = now + timedelta(days=INTERVAL_DAYS)
    if item.round >= MAX_ROUNDS or item.next_due_at.date() > exam_end(now.date()):
        item.active = False
    await session.commit()


async def deactivate(session: AsyncSession, item: Followup) -> None:
    item.active = False
    await session.commit()


def message_text(item: Followup) -> str:
    return (f"Привет! Прошло около {item.round * 2 + 2} мес. после подбора по предмету «{item.subject}». "
            "Как идут дела: уже занимаешься в школе?")
