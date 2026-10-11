"""Database work for site reviews. Public code only creates drafts, confirms them and deletes a person's own data;
moderation (approve, reject, mark verified) lives in admin code, which runs under a different database role."""
import json
from datetime import timedelta
from typing import Optional

from sqlalchemy import delete, func, select, text, update

from . import images
from .models import (DeletionRequest, Review, ReviewCriterionScore, ReviewDraft, ReviewProof, School, Teacher,
                     User, utcnow)
from .security import CODE_TTL_MINUTES, DRAFT_TTL_MINUTES, MAX_CODE_ATTEMPTS, same
from .validation import CONSENT_VERSION

PROOF_RETENTION_DAYS = 30  # a pending review's screenshots are deleted after this even if nobody moderated it


async def target(session, school_id: int, teacher_id: Optional[int]):
    """(school, teacher or None) if both exist and are active; (None, None) otherwise."""
    school = await session.get(School, school_id)
    if not school or not school.is_active:
        return None, None
    if teacher_id is None:
        return school, None
    teacher = await session.get(Teacher, teacher_id)
    if not teacher or not teacher.is_active or teacher.school_id != school.id:
        return None, None
    return school, teacher


async def create_draft(session, *, token_hash, email_hash, code_hash, payload: dict, ip_hash, proofs, now=None):
    """proofs: [(file_name, width, height, size)] already written to disk."""
    now = now or utcnow()
    draft = ReviewDraft(token_hash=token_hash, email_hash=email_hash, code_hash=code_hash,
                        payload=json.dumps(payload, ensure_ascii=False), ip_hash=ip_hash, last_sent_at=now,
                        expires_at=now + timedelta(minutes=DRAFT_TTL_MINUTES), created_at=now)
    session.add(draft)
    await session.flush()
    for file_name, width, height, size in proofs:
        session.add(ReviewProof(draft_id=draft.id, file_name=file_name, width=width, height=height, bytes=size,
                                created_at=now))
    await session.commit()
    return draft


async def draft_by_token(session, token_hash, now=None):
    now = now or utcnow()
    draft = (await session.execute(select(ReviewDraft).where(ReviewDraft.token_hash == token_hash))).scalar_one_or_none()
    if draft is None or draft.expires_at < now:
        return None
    return draft


class CodeResult:
    OK, WRONG, EXPIRED, LOCKED = "ok", "wrong", "expired", "locked"


def check_code(record, code_hash: str, now=None) -> str:
    """A draft's code lives CODE_TTL_MINUTES from the last send; a deletion request's until it expires."""
    now = now or utcnow()
    if record.attempts >= MAX_CODE_ATTEMPTS:
        return CodeResult.LOCKED
    sent = getattr(record, "last_sent_at", None)
    if record.expires_at < now or (sent is not None and now - sent > timedelta(minutes=CODE_TTL_MINUTES)):
        return CodeResult.EXPIRED
    return CodeResult.OK if same(record.code_hash, code_hash) else CodeResult.WRONG


async def confirm_draft(session, draft: ReviewDraft, now=None):
    """Turn a confirmed draft into a pending review. A newer review of the same school/teacher by the same person
    replaces the older one. Returns (review id, proof files of the replaced review to remove, replaced?)."""
    now = now or utcnow()
    payload = json.loads(draft.payload)
    user = (await session.execute(select(User).where(User.email_hash == draft.email_hash))).scalar_one_or_none()
    if user is None:
        user = User(email_hash=draft.email_hash, created_at=now)
        session.add(user)
        await session.flush()
    user.consent_at, user.consent_version = now, CONSENT_VERSION
    old_ids = list((await session.execute(select(Review.id).where(
        Review.user_id == user.id, Review.school_id == payload["school_id"],
        Review.teacher_id.is_(None) if payload["teacher_id"] is None else Review.teacher_id == payload["teacher_id"],
    ))).scalars())
    removed_files = await _delete_reviews(session, old_ids)
    review = Review(user_id=user.id, school_id=payload["school_id"], teacher_id=payload["teacher_id"],
                    criteria_json=json.dumps(payload["scores"], ensure_ascii=False), score=float(payload["score"]),
                    text_positive=payload["positive"], text_negative=payload["negative"], moderation_status="pending",
                    verified=False, created_at=now, source="site", study_period=payload["period"],
                    ip_hash=draft.ip_hash or None, consent_version=CONSENT_VERSION)
    session.add(review)
    await session.flush()
    for key, value in payload["scores"].items():
        session.add(ReviewCriterionScore(review_id=review.id, criterion=key, score=float(value)))
    await session.execute(update(ReviewProof).where(ReviewProof.draft_id == draft.id)
                          .values(review_id=review.id, draft_id=None))
    await session.delete(draft)
    await session.commit()
    return review.id, removed_files, bool(old_ids)


async def _delete_reviews(session, review_ids) -> list:
    """Delete reviews with their scores and proof rows; returns proof file names to remove from disk."""
    if not review_ids:
        return []
    files = list((await session.execute(select(ReviewProof.file_name).where(ReviewProof.review_id.in_(review_ids)))).scalars())
    await session.execute(delete(ReviewProof).where(ReviewProof.review_id.in_(review_ids)))
    await session.execute(delete(ReviewCriterionScore).where(ReviewCriterionScore.review_id.in_(review_ids)))
    await session.execute(delete(Review).where(Review.id.in_(review_ids)))
    return files


async def delete_person(session, email_hash: str) -> tuple:
    """Everything tied to this email: reviews, scores, proofs, drafts, the user row. Returns (reviews, files)."""
    user = (await session.execute(select(User).where(User.email_hash == email_hash))).scalar_one_or_none()
    files, count = [], 0
    if user is not None:
        ids = list((await session.execute(select(Review.id).where(Review.user_id == user.id))).scalars())
        count = len(ids)
        files += await _delete_reviews(session, ids)
        await session.delete(user)
    draft_ids = list((await session.execute(select(ReviewDraft.id).where(ReviewDraft.email_hash == email_hash))).scalars())
    if draft_ids:
        files += list((await session.execute(select(ReviewProof.file_name).where(ReviewProof.draft_id.in_(draft_ids)))).scalars())
        await session.execute(delete(ReviewProof).where(ReviewProof.draft_id.in_(draft_ids)))
        await session.execute(delete(ReviewDraft).where(ReviewDraft.id.in_(draft_ids)))
    await session.commit()
    return count, files


async def drop_draft(session, draft_id: int) -> None:
    await session.execute(delete(ReviewProof).where(ReviewProof.draft_id == draft_id))
    await session.execute(delete(ReviewDraft).where(ReviewDraft.id == draft_id))
    await session.commit()


async def create_deletion_request(session, token_hash, email_hash, code_hash, now=None):
    now = now or utcnow()
    session.add(DeletionRequest(token_hash=token_hash, email_hash=email_hash, code_hash=code_hash,
                                expires_at=now + timedelta(minutes=CODE_TTL_MINUTES), created_at=now))
    await session.commit()


async def refresh_ratings(session) -> None:
    """Recalculate public snapshots (Postgres only; SQLite in tests has no such function)."""
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("select public.refresh_all_rating_snapshots()"))
        await session.commit()


async def cleanup(session, proof_dir: str, now=None) -> int:
    """Expired drafts and deletion requests; screenshots of reviews pending longer than PROOF_RETENTION_DAYS."""
    now = now or utcnow()
    expired = list((await session.execute(select(ReviewDraft.id).where(ReviewDraft.expires_at < now))).scalars())
    files = []
    if expired:
        files += list((await session.execute(select(ReviewProof.file_name).where(ReviewProof.draft_id.in_(expired)))).scalars())
        await session.execute(delete(ReviewProof).where(ReviewProof.draft_id.in_(expired)))
        await session.execute(delete(ReviewDraft).where(ReviewDraft.id.in_(expired)))
    old = now - timedelta(days=PROOF_RETENTION_DAYS)
    stale = list((await session.execute(select(ReviewProof.file_name).where(
        ReviewProof.review_id.is_not(None), ReviewProof.created_at < old))).scalars())
    if stale:
        files += stale
        await session.execute(delete(ReviewProof).where(ReviewProof.file_name.in_(stale)))
    await session.execute(delete(DeletionRequest).where(DeletionRequest.expires_at < now))
    await session.commit()
    for name in files:
        images.remove_file(proof_dir, name)
    return len(files)


async def pending_count(session) -> int:
    return (await session.execute(select(func.count()).select_from(Review).where(
        Review.moderation_status == "pending", Review.source == "site"))).scalar_one()
