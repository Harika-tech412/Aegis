"""SQLAlchemy 2.0 ORM models for Aegis."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionBand(str, enum.Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    AUTO_FLAG = "AUTO_FLAG"


class Verdict(str, enum.Enum):
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    CONFIRMED_LEGITIMATE = "CONFIRMED_LEGITIMATE"
    UNCERTAIN = "UNCERTAIN"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    applicant_age: Mapped[int] = mapped_column(Integer)
    annual_income: Mapped[float] = mapped_column(Float)
    employment_type: Mapped[str] = mapped_column(String(32))
    employer_name: Mapped[str] = mapped_column(String(200))
    requested_amount: Mapped[float] = mapped_column(Float)
    loan_purpose: Mapped[str] = mapped_column(String(32))
    loan_purpose_text: Mapped[str] = mapped_column(Text, default="")
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    session_duration_seconds: Mapped[int] = mapped_column(Integer)
    mouse_movement_events: Mapped[int] = mapped_column(Integer)
    form_paste_count: Mapped[int] = mapped_column(Integer)
    id_document_filename: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Full original submission (including signal fields that are not first-class
    # columns, e.g. consistency scores and velocity counts) kept for audit.
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    decisions: Mapped[list["Decision"]] = relationship(back_populates="application")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    xgboost_probability: Mapped[float] = mapped_column(Float)
    anomaly_score: Mapped[float] = mapped_column(Float)
    calibrated_risk_score: Mapped[float] = mapped_column(Float)
    decision_band: Mapped[DecisionBand] = mapped_column(
        Enum(DecisionBand, native_enum=False, length=20), index=True
    )
    top_shap_features: Mapped[list] = mapped_column(JSON, default=list)
    explanation_text: Mapped[str] = mapped_column(Text, default="")
    counterfactual: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ring_size: Mapped[int] = mapped_column(Integer, default=0)
    ring_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    application: Mapped[Application] = relationship(back_populates="decisions")
    feedback: Mapped[list["InvestigatorFeedback"]] = relationship(back_populates="decision")


class InvestigatorFeedback(Base):
    __tablename__ = "investigator_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decisions.id"), index=True)
    investigator_username: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[Verdict] = mapped_column(Enum(Verdict, native_enum=False, length=24))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    decision: Mapped[Decision] = relationship(back_populates="feedback")


class CaseNarrative(Base):
    __tablename__ = "case_narratives"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[str] = mapped_column(String(32), unique=True)
    fraud_type: Mapped[str] = mapped_column(String(32), index=True)
    narrative_text: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(32))
    embedding = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Investigator(Base):
    __tablename__ = "investigators"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
