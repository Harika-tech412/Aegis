"""Pydantic request/response schemas for the Aegis API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EmploymentType = Literal["salaried", "self_employed", "gig_worker", "unemployed"]
LoanPurpose = Literal[
    "debt_consolidation", "home_improvement", "medical", "education", "business", "other"
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """A loan application submission.

    The two consistency scores come from upstream verification services in a
    real deployment and are required inputs here. The two velocity counts are
    optional: when omitted, the server derives them from its own application
    history (same device/IP in the last 24h), which is the honest serving-time
    computation.
    """

    applicant_age: int = Field(ge=18, le=100)
    annual_income: float = Field(ge=0, le=10_000_000)
    employment_type: EmploymentType
    employer_name: str = Field(min_length=1, max_length=200)
    requested_amount: float = Field(gt=0, le=1_000_000)
    loan_purpose: LoanPurpose
    loan_purpose_text: str = Field(default="", max_length=500)
    device_id: str = Field(min_length=1, max_length=64)
    ip_hash: str = Field(min_length=1, max_length=64)
    session_duration_seconds: int = Field(ge=0, le=86_400)
    mouse_movement_events: int = Field(ge=0, le=100_000)
    form_paste_count: int = Field(ge=0, le=1_000)
    id_document_filename: str | None = Field(default=None, max_length=128)
    # Demo-only identity fields: used by the rule-based ID-name check, stored
    # in raw_payload for audit, never a DB column and never a model feature.
    applicant_name: str | None = Field(default=None, max_length=100)
    id_document_uploaded_name: str | None = Field(default=None, max_length=100)
    applications_from_device_last_24h: int | None = Field(default=None, ge=1, le=10_000)
    applications_from_ip_last_24h: int | None = Field(default=None, ge=1, le=10_000)
    income_employer_consistency_score: float = Field(ge=0.0, le=1.0)
    identity_consistency_score: float = Field(ge=0.0, le=1.0)


class ShapFeatureOut(BaseModel):
    feature: str
    label: str
    value: float
    shap_value: float
    direction: str
    explanation: str


class CounterfactualOut(BaseModel):
    feature: str
    current_value: float
    required_value: float | None
    would_change_decision_to: str | None
    note: str | None = None


class DecisionOut(BaseModel):
    id: uuid.UUID
    model_version: str
    xgboost_probability: float
    anomaly_score: float
    calibrated_risk_score: float
    decision_band: str
    explanation_text: str
    explanation_source: str | None = None
    ring_size: int
    ring_risk_score: float
    # Cross-institution Aegis Network matches that influenced this decision.
    network_hits: list[dict] | None = None
    # Layer 5: identity-continuity verdict and step-up outcome.
    identity_continuity: dict | None = None
    step_up_result: dict | None = None
    latency_ms: float
    created_at: datetime

    # protected_namespaces=() because the field is genuinely named model_version
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ApplicationSummaryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    applicant_age: int
    annual_income: float
    employment_type: str
    requested_amount: float
    loan_purpose: str
    device_id: str
    calibrated_risk_score: float | None = None
    decision_band: str | None = None


class IdentityCheckOut(BaseModel):
    applicant_name: str | None
    id_document_name: str | None
    mismatch: bool
    # OCR-extracted fields (present when a document was actually processed)
    form_dob: str | None = None
    ocr_dob: str | None = None
    ocr_id_number: str | None = None
    # Perceptual-hash reuse check
    reused_across_names: bool = False
    prior_names: list[str] = []
    prior_uses: int = 0


class ApplicationDetailOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    applicant_age: int
    annual_income: float
    employment_type: str
    employer_name: str
    requested_amount: float
    loan_purpose: str
    loan_purpose_text: str
    device_id: str
    ip_hash: str
    session_duration_seconds: int
    mouse_movement_events: int
    form_paste_count: int
    id_document_filename: str | None
    decision: DecisionOut | None
    top_shap_features: list[ShapFeatureOut] = []
    counterfactual: list[CounterfactualOut] | None = None
    connected_applications: list[str] = []
    identity_check: IdentityCheckOut | None = None


class ScoreResponse(BaseModel):
    application_id: uuid.UUID
    decision: DecisionOut
    top_shap_features: list[ShapFeatureOut]
    counterfactual: list[CounterfactualOut] | None
    connected_applications: list[str]


class ApplicationListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ApplicationSummaryOut]


# ---------------------------------------------------------------------------
# Feedback & ring
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    verdict: Literal["CONFIRMED_FRAUD", "CONFIRMED_LEGITIMATE", "UNCERTAIN"]
    notes: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    decision_id: uuid.UUID
    investigator_username: str
    verdict: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RingMemberOut(BaseModel):
    application_id: str
    decision_band: str | None = None
    source: Literal["database", "historical"]


class RingOut(BaseModel):
    application_id: uuid.UUID
    ring_size: int
    ring_risk_score: float
    members: list[RingMemberOut]
