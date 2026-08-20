"""Public applicant-facing intake endpoints.

DEMO SECURITY NOTE, stated plainly: these endpoints are deliberately
unauthenticated because they represent the PUBLIC loan-application channel —
in a real deployment the intake surface is public by definition, hardened by
WAF/bot-management/rate limits rather than end-user JWTs. The applicant NEVER
receives the fraud decision — only a reference number. Rate limits apply.

NOTE: no `from __future__ import annotations` — FastAPI cannot resolve
UploadFile/File parameter annotations under PEP 563 string annotations.
"""

import json
import uuid as uuid_lib
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml.scoring_service import get_scoring_service
from app.models import Application
from app.rate_limit import limiter
from app.routers.applications import (
    _derived_velocity,
    apply_id_rules,
    apply_network_rules,
    persist_scored_application,
)
from app.routers.demo import UPLOADS_DIR
from app.schemas import EmploymentType, LoanPurpose
from app.services import network_service
from app.services.id_hash_service import check_id_reuse, record_id_hash
from app.services.llm_explainer import explain_result
from app.services.ocr_service import extract_id_fields, names_match

router = APIRouter(prefix="/public", tags=["public"])

# ₹ → model currency units. The model was trained on incomes in a 15k-250k
# range; Indian rupee amounts are normalised by a fixed FX rate so they land
# in the distribution the model actually saw. Ratios (loan-to-income) are
# currency-invariant either way.
INR_TO_MODEL_UNITS = 83.0
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class PublicApplyRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    date_of_birth: str = Field(max_length=10)  # YYYY-MM-DD
    pan_number: str = Field(default="", max_length=20)
    email: str = Field(default="", max_length=120)
    mobile: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=400)
    city: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=80)
    pin_code: str = Field(default="", max_length=10)
    employment_type: EmploymentType
    employer_name: str = Field(min_length=1, max_length=200)
    monthly_income_inr: float = Field(gt=0, le=100_000_000)
    years_in_employment: float = Field(default=0, ge=0, le=60)
    loan_amount_inr: float = Field(gt=0, le=500_000_000)
    loan_purpose: LoanPurpose
    purpose_text: str = Field(default="", max_length=500)
    # Client-side behavioral instrumentation (measured by the form itself).
    device_id: str = Field(min_length=1, max_length=64)
    ip_hash: str = Field(min_length=1, max_length=64)
    session_duration_seconds: int = Field(ge=0, le=86_400)
    mouse_movement_events: int = Field(ge=0, le=100_000)
    form_paste_count: int = Field(ge=0, le=1_000)
    # KYC-vendor signals: defaulted for public intake; a real deployment would
    # call the verification vendor here.
    income_employer_consistency_score: float = Field(default=0.85, ge=0, le=1)
    identity_consistency_score: float = Field(default=0.85, ge=0, le=1)
    # Demo hook: velocity is normally derived server-side from application
    # history, but the ring preset represents a device mid-burst, so it may
    # assert its own counts. Documented demo affordance.
    applications_from_device_last_24h: int | None = Field(default=None, ge=1, le=10_000)
    applications_from_ip_last_24h: int | None = Field(default=None, ge=1, le=10_000)


def _age_from_dob(dob: str) -> int:
    try:
        born = datetime.strptime(dob, "%Y-%m-%d").date()
        today = date(2026, 8, 19)  # demo clock; avoids timezone surprises
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return max(18, min(100, age))
    except ValueError:
        return 30


@router.post("/verify-id")
@limiter.limit("30/minute")
async def verify_id(request: Request, id_document: UploadFile = File(...)) -> dict:
    """OCR preview for the applicant form's 'Verify ID' box. Nothing is stored."""
    content = await id_document.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Document too large (5MB max)")
    return extract_id_fields(content)


@router.post("/apply")
@limiter.limit("20/minute")
async def submit_application(
    request: Request,
    payload: str = Form(...),
    id_document: UploadFile | None = File(default=None),
    address_proof: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict:
    try:
        body = PublicApplyRequest(**json.loads(payload))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid application payload: {exc}")

    # ---- Transform the public form into model inputs ------------------------
    annual_income = round(body.monthly_income_inr * 12 / INR_TO_MODEL_UNITS, 2)
    requested = round(min(max(body.loan_amount_inr / INR_TO_MODEL_UNITS, 1_000), 50_000), 2)
    score_payload: dict = {
        "applicant_age": _age_from_dob(body.date_of_birth),
        "annual_income": max(1_000.0, annual_income),
        "employment_type": body.employment_type,
        "employer_name": body.employer_name,
        "requested_amount": requested,
        "loan_purpose": body.loan_purpose,
        "loan_purpose_text": body.purpose_text,
        "device_id": body.device_id,
        "ip_hash": body.ip_hash,
        "session_duration_seconds": body.session_duration_seconds,
        "mouse_movement_events": body.mouse_movement_events,
        "form_paste_count": body.form_paste_count,
        "id_document_filename": None,
        "applications_from_device_last_24h": body.applications_from_device_last_24h
        or _derived_velocity(db, Application.device_id, body.device_id),
        "applications_from_ip_last_24h": body.applications_from_ip_last_24h
        or _derived_velocity(db, Application.ip_hash, body.ip_hash),
        "income_employer_consistency_score": body.income_employer_consistency_score,
        "identity_consistency_score": body.identity_consistency_score,
        "applicant_name": body.full_name,
        "date_of_birth": body.date_of_birth,
    }

    # ---- ID document: OCR + perceptual-hash reuse check ----------------------
    ocr_result = None
    reuse_result = None
    stored_filename = None
    id_bytes = b""
    if id_document is not None:
        id_bytes = await id_document.read()
        if len(id_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="ID document too large (5MB max)")
        ocr_result = extract_id_fields(id_bytes)
        reuse_result = check_id_reuse(db, id_bytes, body.full_name)

        ext = "jpg" if (id_document.content_type or "").endswith("jpeg") else "png"
        stored_filename = f"upload_{uuid_lib.uuid4().hex[:12]}.{ext}"
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOADS_DIR / stored_filename).write_bytes(id_bytes)

        score_payload["id_document_filename"] = stored_filename
        score_payload["id_document_uploaded_name"] = ocr_result["name"]
        score_payload["ocr"] = {k: ocr_result[k] for k in ("name", "dob", "id_number")}

    if address_proof is not None:
        # Captured for KYC-compliance realism; recorded, not OCR'd (documented scope).
        score_payload["address_proof_filename"] = address_proof.filename

    # ---- Score + rules layer --------------------------------------------------
    service = get_scoring_service()
    result = service.score(score_payload)

    name_mismatch = bool(
        ocr_result and ocr_result["name"] and not names_match(ocr_result["name"], body.full_name)
    )
    reuse_across_names = bool(
        reuse_result
        and reuse_result["reused"]
        and any(not names_match(n, body.full_name) for n in reuse_result["prior_names"])
    )
    if reuse_result:
        score_payload["id_reuse"] = {
            "reused": reuse_result["reused"],
            "prior_uses": reuse_result["prior_uses"],
            "prior_names": reuse_result["prior_names"],
            "reused_across_names": reuse_across_names,
        }

    apply_id_rules(
        service,
        result,
        name_mismatch=name_mismatch,
        reuse_across_names=reuse_across_names,
        form_name=body.full_name,
        id_name=ocr_result["name"] if ocr_result else None,
        prior_names=reuse_result["prior_names"] if reuse_result else [],
        name_verified=bool(
            ocr_result and ocr_result["name"] and names_match(ocr_result["name"], body.full_name)
        ),
    )

    # ---- Aegis Network: cross-institution signal check ---------------------
    own = network_service.get_institution(db, network_service.SYNC_DEMO)
    network_hits = network_service.check_network(
        db, body.device_id, body.ip_hash, own.id if own else None
    )
    apply_network_rules(service, result, network_hits)

    explanation_text, explanation_source = explain_result(result)
    application, _decision = persist_scored_application(
        db,
        score_payload,
        result,
        explanation_text,
        explanation_source,
        requested_by="public_portal",
        id_document_filename=stored_filename,
        institution_id=own.id if own else None,
        network_hits=network_hits,
    )
    if id_document is not None and id_bytes:
        record_id_hash(db, id_bytes, application.id, ocr_result["name"] if ocr_result else None)
    db.commit()

    # The applicant sees ONLY a reference — never the decision.
    return {
        "status": "received",
        "reference": f"QL-{str(application.id)[:8].upper()}",
        "message": "Application received. You will hear back within 24 hours.",
        # OCR echo so the form can show its 'Verify ID' box post-submit if needed
        "id_verification": {"extracted_name": ocr_result["name"]} if ocr_result else None,
    }
