"""Tables the site review service touches. Its own declarative base: the service never imports the Telegram bot.

The physical tables are created by supabase/migrations (001..018) on the Russian server; tests build them from
this metadata on SQLite. Only the columns the service reads or writes are mapped.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    criteria_status: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    teachers_score: Mapped[float] = mapped_column(Float, default=7.0)
    practice_score: Mapped[float] = mapped_column(Float, default=7.0)
    feedback_score: Mapped[float] = mapped_column(Float, default=7.0)
    curator_score: Mapped[float] = mapped_column(Float, default=7.0)
    platform_score: Mapped[float] = mapped_column(Float, default=7.0)
    workload_score: Mapped[float] = mapped_column(Float, default=7.0)
    organization_score: Mapped[float] = mapped_column("price_quality_score", Float, default=7.0)
    scores_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)
    email_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consent_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    criterion: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    criteria_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float)
    text_positive: Mapped[str] = mapped_column(Text, default="")
    text_negative: Mapped[str] = mapped_column(Text, default="")
    moderation_status: Mapped[str] = mapped_column(String(30), default="pending")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(10), default="site")
    study_period: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    moderated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consent_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class ReviewCriterionScore(Base):
    __tablename__ = "review_criterion_scores"
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True)
    criterion: Mapped[str] = mapped_column(String(80), primary_key=True)
    score: Mapped[float] = mapped_column(Float)


class ReviewDraft(Base):
    """A review written on the site whose email is not confirmed yet. Expires in an hour with its files."""
    __tablename__ = "review_drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    resends: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    payload: Mapped[str] = mapped_column(Text)
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewProof(Base):
    """A screenshot proving the author studied there. Stored re-encoded, deleted right after moderation."""
    __tablename__ = "review_proofs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), nullable=True, index=True)
    draft_id: Mapped[Optional[int]] = mapped_column(ForeignKey("review_drafts.id", ondelete="CASCADE"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(80), unique=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DeletionRequest(Base):
    """'Delete my data' confirmed by a code sent to the email. Expires in an hour."""
    __tablename__ = "deletion_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email_hash: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SiteFlag(Base):
    """Global switches. 'leads_enabled' (requests to schools on the site) starts OFF and only the console flips it."""
    __tablename__ = "site_flags"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdminLog(Base):
    __tablename__ = "admin_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")


class Blocked(Base):
    """Keyed hash of an email or a network that may not send reviews any more."""
    __tablename__ = "blocked"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SchoolScoreHistory(Base):
    __tablename__ = "school_score_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reason: Mapped[str] = mapped_column(String(500))
    changes: Mapped[str] = mapped_column(Text, default="{}")
