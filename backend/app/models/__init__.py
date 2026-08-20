"""SQLAlchemy 2.0 ORM models for Aegis."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionBand(str, enum.Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    AUTO_FLAG = "AUTO_FLAG"


class SignalType(str, enum.Enum):
    DEVICE_HASH = "DEVICE_HASH"
    IP_HASH = "IP_HASH"
    ID_DOCUMENT_HASH = "ID_DOCUMENT_HASH"


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
    # Owning institution. Nullable so existing rows migrate cleanly; startup
    # backfills every legacy row to SYNC_DEMO.
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id"), nullable=True, index=True
    )
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
    # Cross-institution network signal matches that influenced this decision.
    network_hits: Mapped[list | None] = mapped_column(JSON, nullable=True)
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


class IdDocumentHash(Base):
    """Perceptual hash of every uploaded ID image, for reuse detection."""

    __tablename__ = "id_document_hashes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phash: Mapped[str] = mapped_column(String(80), index=True)  # 256-bit hash = 64 hex chars
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    extracted_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentInvestigation(Base):
    """Cached output of the LangGraph investigation agent for one application."""

    __tablename__ = "agent_investigations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    investigation_log: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    synthesis_source: Mapped[str] = mapped_column(String(24), default="template")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Institution(Base):
    """A member institution of the Aegis Network.

    Two are seeded: SYNC_DEMO and PARTNER_A. They are genuinely separate —
    each owns its own applications and publishes its own signals.
    """

    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    joined_network_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class NetworkFraudSignal(Base):
    """A confirmed-fraud signal shared across the network.

    PRIVACY CONTRACT: `signal_hash` is SHA-256(salt + raw_value). The raw
    device fingerprint / IP / document is NEVER stored here and cannot be
    recovered from the hash. A partner institution can only ever answer
    "have I seen this exact value before?" — never "what was the value?".
    """

    __tablename__ = "network_fraud_signals"
    __table_args__ = (Index("ix_network_signal_lookup", "signal_type", "signal_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    signal_type: Mapped[SignalType] = mapped_column(
        Enum(SignalType, native_enum=False, length=24), index=True
    )
    signal_hash: Mapped[str] = mapped_column(String(64), index=True)
    reported_by_institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    original_application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True
    )
    fraud_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    notes: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Investigator(Base):
    __tablename__ = "investigators"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
