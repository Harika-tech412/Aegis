"""Core application endpoints: scoring, browsing, feedback, ring context.

NOTE: no `from __future__ import annotations` here — slowapi's decorator
wrapper breaks FastAPI's forward-ref resolution under PEP 563 string
annotations (ScoreRequest would be undefined in the wrapper's namespace).
Python 3.11 handles the `X | None` unions natively without it.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml.scoring_service import get_scoring_service
from app.models import Application, Decision, Investigator, InvestigatorFeedback
from app.rate_limit import SCORE_LIMIT, limiter
from app.schemas import (
    ApplicationDetailOut,
    ApplicationListOut,
    ApplicationSummaryOut,
    DecisionOut,
    FeedbackOut,
    FeedbackRequest,
    RingMemberOut,
    RingOut,
    ScoreRequest,
    ScoreResponse,
)
from app.services import audit
from app.services.auth import get_current_investigator
from app.services.llm_explainer import explain_result
from app.services.similar_cases import find_similar_cases

router = APIRouter(tags=["applications"])


def _derived_velocity(db: Session, column, value: str) -> int:
    """Applications sharing this device/IP in the DB in the prior 24h, inclusive."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    prior = db.scalar(
        select(func.count()).select_from(Application).where(column == value, Application.created_at >= cutoff)
    )
    return int(prior or 0) + 1


@router.post("/score", response_model=ScoreResponse)
@limiter.limit(SCORE_LIMIT)
def score_application(
    request: Request,
    body: ScoreRequest,
    db: Session = Depends(get_db),
    investigator: Investigator = Depends(get_current_investigator),
) -> ScoreResponse:
    payload = body.model_dump()

    # Server-side velocity when the caller did not supply it (see schema note).
    if payload["applications_from_device_last_24h"] is None:
        payload["applications_from_device_last_24h"] = _derived_velocity(
            db, Application.device_id, body.device_id
        )
    if payload["applications_from_ip_last_24h"] is None:
        payload["applications_from_ip_last_24h"] = _derived_velocity(
            db, Application.ip_hash, body.ip_hash
        )

    result = get_scoring_service().score(payload)
    explanation_text, explanation_source = explain_result(result)

    application = Application(
        applicant_age=body.applicant_age,
        annual_income=body.annual_income,
        employment_type=body.employment_type,
        employer_name=body.employer_name,
        requested_amount=body.requested_amount,
        loan_purpose=body.loan_purpose,
        loan_purpose_text=body.loan_purpose_text,
        device_id=body.device_id,
        ip_hash=body.ip_hash,
        session_duration_seconds=body.session_duration_seconds,
        mouse_movement_events=body.mouse_movement_events,
        form_paste_count=body.form_paste_count,
        id_document_filename=body.id_document_filename,
        raw_payload=payload,
    )
    db.add(application)
    db.flush()

    decision = Decision(
        application_id=application.id,
        model_version=result.model_version,
        xgboost_probability=result.xgboost_probability,
        anomaly_score=result.anomaly_score,
        calibrated_risk_score=result.calibrated_risk_score,
        decision_band=result.decision_band,
        top_shap_features=result.top_shap_features,
        explanation_text=explanation_text,
        counterfactual=result.counterfactual,
        ring_size=result.ring_size,
        ring_risk_score=result.ring_risk_score,
        latency_ms=result.latency_ms,
    )
    db.add(decision)
    db.flush()

    audit.log_event(
        db,
        event_type="application_scored",
        actor="system",
        target_type="application",
        target_id=str(application.id),
        details={
            "decision_band": result.decision_band,
            "calibrated_risk_score": result.calibrated_risk_score,
            "explanation_source": explanation_source,
            "requested_by": investigator.username,
        },
    )
    db.commit()

    decision_out = DecisionOut.model_validate(decision)
    decision_out.explanation_source = explanation_source
    return ScoreResponse(
        application_id=application.id,
        decision=decision_out,
        top_shap_features=result.top_shap_features,
        counterfactual=result.counterfactual,
        connected_applications=result.connected_applications,
    )


@router.get("/applications", response_model=ApplicationListOut)
def list_applications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision_band: str | None = Query(default=None, pattern="^(AUTO_APPROVE|HUMAN_REVIEW|AUTO_FLAG)$"),
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> ApplicationListOut:
    query = (
        select(Application, Decision)
        .join(Decision, Decision.application_id == Application.id)
        .order_by(Application.created_at.desc())
    )
    count_query = select(func.count()).select_from(Application).join(
        Decision, Decision.application_id == Application.id
    )
    if decision_band:
        query = query.where(Decision.decision_band == decision_band)
        count_query = count_query.where(Decision.decision_band == decision_band)

    total = int(db.scalar(count_query) or 0)
    rows = db.execute(query.limit(limit).offset(offset)).all()

    items = [
        ApplicationSummaryOut(
            id=app.id,
            created_at=app.created_at,
            applicant_age=app.applicant_age,
            annual_income=app.annual_income,
            employment_type=app.employment_type,
            requested_amount=app.requested_amount,
            loan_purpose=app.loan_purpose,
            device_id=app.device_id,
            calibrated_risk_score=decision.calibrated_risk_score,
            decision_band=decision.decision_band.value
            if hasattr(decision.decision_band, "value")
            else decision.decision_band,
        )
        for app, decision in rows
    ]
    return ApplicationListOut(total=total, limit=limit, offset=offset, items=items)


def _load_application(db: Session, application_id: uuid.UUID) -> tuple[Application, Decision | None]:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    decision = (
        db.execute(
            select(Decision)
            .where(Decision.application_id == application_id)
            .order_by(Decision.created_at.desc())
        )
        .scalars()
        .first()
    )
    return application, decision


@router.get("/applications/{application_id}", response_model=ApplicationDetailOut)
def get_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> ApplicationDetailOut:
    application, decision = _load_application(db, application_id)

    connected: list[str] = []
    if decision is not None and decision.ring_size > 0:
        ctx = get_scoring_service().ring_context(
            application.device_id, application.ip_hash, own_id=str(application.id)
        )
        connected = ctx["connected_applications"]

    return ApplicationDetailOut(
        id=application.id,
        created_at=application.created_at,
        applicant_age=application.applicant_age,
        annual_income=application.annual_income,
        employment_type=application.employment_type,
        employer_name=application.employer_name,
        requested_amount=application.requested_amount,
        loan_purpose=application.loan_purpose,
        loan_purpose_text=application.loan_purpose_text,
        device_id=application.device_id,
        ip_hash=application.ip_hash,
        session_duration_seconds=application.session_duration_seconds,
        mouse_movement_events=application.mouse_movement_events,
        form_paste_count=application.form_paste_count,
        id_document_filename=application.id_document_filename,
        decision=DecisionOut.model_validate(decision) if decision else None,
        top_shap_features=(decision.top_shap_features or []) if decision else [],
        counterfactual=decision.counterfactual if decision else None,
        connected_applications=connected,
    )


@router.post("/applications/{application_id}/feedback", response_model=FeedbackOut)
def submit_feedback(
    application_id: uuid.UUID,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    investigator: Investigator = Depends(get_current_investigator),
) -> FeedbackOut:
    _, decision = _load_application(db, application_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Application has no decision to review")

    # Username comes from the authenticated token, never from the payload.
    feedback = InvestigatorFeedback(
        decision_id=decision.id,
        investigator_username=investigator.username,
        verdict=body.verdict,
        notes=body.notes,
    )
    db.add(feedback)
    db.flush()
    audit.log_event(
        db,
        event_type="feedback_submitted",
        actor=investigator.username,
        target_type="decision",
        target_id=str(decision.id),
        details={"verdict": body.verdict, "application_id": str(application_id)},
    )
    db.commit()
    return FeedbackOut.model_validate(feedback)


@router.get("/applications/{application_id}/similar-cases")
def get_similar_cases(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    application, decision = _load_application(db, application_id)
    return find_similar_cases(db, application, decision)


@router.get("/applications/{application_id}/ring", response_model=RingOut)
def get_ring(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> RingOut:
    application, _decision = _load_application(db, application_id)
    service = get_scoring_service()
    ctx = service.ring_context(application.device_id, application.ip_hash, own_id=str(application.id))

    # Live DB members sharing the device/IP (scored during this demo session).
    db_rows = db.execute(
        select(Application, Decision)
        .join(Decision, Decision.application_id == Application.id)
        .where(
            (Application.device_id == application.device_id)
            | (Application.ip_hash == application.ip_hash),
            Application.id != application.id,
        )
    ).all()
    db_members = {
        str(app.id): (
            decision.decision_band.value
            if hasattr(decision.decision_band, "value")
            else decision.decision_band
        )
        for app, decision in db_rows
    }

    members = [
        RingMemberOut(application_id=m, decision_band=db_members.get(m), source="historical")
        for m in ctx["connected_applications"]
        if m not in db_members
    ] + [
        RingMemberOut(application_id=m, decision_band=band, source="database")
        for m, band in db_members.items()
    ]

    total_others = len(members)
    return RingOut(
        application_id=application.id,
        ring_size=total_others + 1 if total_others else 0,
        ring_risk_score=ctx["ring_risk_score"],
        members=members,
    )
