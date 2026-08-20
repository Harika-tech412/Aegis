"""Layer 5 endpoints — out-of-band step-up verification.

DEMO SCOPE, stated plainly:

  * /step-up/send RETURNS THE CODE IN THE RESPONSE. A real deployment sends it
    over SMS or push to the registered contact and never puts it on the wire
    back to the caller. It is returned here so the demo can complete the loop
    without an SMS provider.
  * These two routes are unauthenticated, because the applicant-side page
    (/apply) drives the challenge and holds no investigator token. Everything
    they touch is synthetic demo data.

Everything else is real: the code is derived from the identity's stored seed,
the comparison is a real comparison, and the risk adjustment is written to the
decision row and re-bands it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml.scoring_service import get_scoring_service
from app.models import Application, Decision
from app.services import audit, identity_continuity

router = APIRouter(tags=["identity"])


class VerifyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12)


def _load(db: Session, application_id: uuid.UUID) -> tuple[Application, Decision]:
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
    if decision is None:
        raise HTTPException(status_code=404, detail="Application has no decision")
    return application, decision


@router.post("/applications/{application_id}/step-up/send")
def send_step_up(application_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Issue a challenge to the contact already on file for this identity."""
    application, decision = _load(db, application_id)
    key = identity_continuity.key_for_application(db, application)
    contact = identity_continuity.get_contact(db, key)

    if contact is None:
        return {
            "eligible": False,
            "reason": "No registered contact on file for this identity.",
            "identity_status": (decision.identity_continuity or {}).get("status"),
        }

    code = identity_continuity.expected_code(contact.demo_code_seed, application.id)
    audit.log_event(
        db,
        event_type="step_up_sent",
        actor="public_portal",
        target_type="application",
        target_id=str(application_id),
        details={"masked_contact": contact.masked_contact},
    )
    db.commit()
    return {
        "eligible": True,
        "masked_contact": contact.masked_contact,
        "identity_status": (decision.identity_continuity or {}).get("status"),
        # DEMO ONLY — a real deployment never returns this.
        "demo_code": code,
        "note": "Code returned in-response for demo purposes only; production sends it out-of-band.",
    }


@router.post("/applications/{application_id}/step-up/verify")
def verify_step_up(
    application_id: uuid.UUID, body: VerifyRequest, db: Session = Depends(get_db)
) -> dict:
    """Check the answer and move the risk score accordingly."""
    application, decision = _load(db, application_id)
    key = identity_continuity.key_for_application(db, application)
    contact = identity_continuity.get_contact(db, key)
    if contact is None:
        raise HTTPException(status_code=400, detail="No registered contact for this identity")

    expected = identity_continuity.expected_code(contact.demo_code_seed, application.id)
    correct = body.code.strip() == expected
    delta = (
        identity_continuity.STEP_UP_CORRECT_DELTA
        if correct
        else identity_continuity.STEP_UP_WRONG_DELTA
    )

    service = get_scoring_service()
    before = float(decision.calibrated_risk_score)
    after = min(1.0, max(0.0, before + delta))
    band_before = (
        decision.decision_band.value
        if hasattr(decision.decision_band, "value")
        else str(decision.decision_band)
    )
    band_after = service.band_of(after)

    decision.calibrated_risk_score = after
    decision.decision_band = band_after
    decision.step_up_result = {
        "outcome": "CORRECT" if correct else "INCORRECT",
        "masked_contact": contact.masked_contact,
        "risk_delta": delta,
        "risk_before": round(before, 4),
        "risk_after": round(after, 4),
        "band_before": band_before,
        "band_after": band_after,
    }

    # Disclosed the same way the ID and network rules are: a named pseudo-feature
    # in top_shap_features, so the explanation panel shows where the move came
    # from rather than a score that silently changed.
    features = list(decision.top_shap_features or [])
    features.insert(
        0,
        {
            "feature": "STEP_UP_VERIFIED" if correct else "STEP_UP_FAILED",
            "label": "Step-up verification (rule)",
            # Numeric like every other disclosed rule; the words live in
            # `explanation`, which is what the panel renders.
            "value": 1.0,
            "shap_value": delta,  # rule weight, NOT a SHAP value
            "direction": "decreases_risk" if correct else "increases_risk",
            "explanation": (
                f"Code sent to the contact on file ({contact.masked_contact}) was "
                + ("answered correctly" if correct else "answered incorrectly")
                + f" — {delta:+.2f} risk."
            ),
        },
    )
    decision.top_shap_features = features

    audit.log_event(
        db,
        event_type="step_up_verified",
        actor="public_portal",
        target_type="application",
        target_id=str(application_id),
        details=decision.step_up_result,
    )
    db.commit()

    return {
        "outcome": decision.step_up_result["outcome"],
        "identity_status": (decision.identity_continuity or {}).get("status"),
        **decision.step_up_result,
    }
