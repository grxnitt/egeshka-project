from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text)
    fit_text: Mapped[str] = mapped_column(Text, default="")
    results_text: Mapped[str] = mapped_column(Text, default="")
    official_url: Mapped[str] = mapped_column(String(500))
    subjects: Mapped[str] = mapped_column(String(500))
    monthly_price_from: Mapped[int] = mapped_column(Integer)
    price_text: Mapped[str] = mapped_column(Text, default="")
    price_comment: Mapped[str] = mapped_column(Text, default="")
    scale_reputation: Mapped[str] = mapped_column(Text, default="")
    format_text: Mapped[str] = mapped_column(Text, default="")
    support_text: Mapped[str] = mapped_column(Text, default="")
    homework_text: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    review_summary: Mapped[str] = mapped_column(Text, default="")
    evidence_types: Mapped[str] = mapped_column(String(200), default="")
    teachers_text: Mapped[str] = mapped_column(Text, default="")
    teachers_score: Mapped[float] = mapped_column(Float, default=7.0)
    practice_score: Mapped[float] = mapped_column(Float, default=7.0)
    feedback_score: Mapped[float] = mapped_column(Float, default=7.0)
    curator_score: Mapped[float] = mapped_column(Float, default=7.0)
    platform_score: Mapped[float] = mapped_column(Float, default=7.0)
    workload_score: Mapped[float] = mapped_column(Float, default=7.0)
    price_quality_score: Mapped[float] = mapped_column(Float, default=7.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    subject: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[float] = mapped_column(Float, default=7.0)
    review_summary: Mapped[str] = mapped_column(Text, default="")
    social_url: Mapped[str] = mapped_column(String(500), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    evidence_type: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    proof_file_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    proof_file_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, index=True)
    event_name: Mapped[str] = mapped_column(String(80), index=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
