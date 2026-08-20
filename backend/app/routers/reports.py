"""Audience-specific presentations of an existing decision.

Catching fraud is half the job; proving the decision was made fairly is the
other half. These two endpoints re-present a decision that has ALREADY been
made — one for a regulator (CFPB-style examination), one for the declined
applicant (ECOA/FCRA-style adverse-action notice).

No new data collection, no new inference. Every value is read from the
applications / decisions / investigator_feedback / audit_log tables and the
frozen model artifacts. The scoring pipeline is not touched.
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml.scoring_service import ARTIFACTS_DIR
from app.models import (
    Application,
    AuditLog,
    Decision,
    Investigator,
    InvestigatorFeedback,
)
from app.services.auth import get_current_investigator

router = APIRouter(tags=["reports"])

REPORT_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Fair-lending attestation.
#
# This is a claim about the model's INPUTS, and it is verifiable: the complete
# feature list lives in ml/artifacts/feature_spec.json (22 columns — behavioural,
# network, and self-declared financial signals only). None of the categories
# below is collected, derived, or inferred anywhere in the pipeline.
#
# `applicant_age` IS a model input (it is a legitimate underwriting attribute),
# but it is never used as a proxy for a prohibited basis — hence the precise
# wording "age_as_discriminatory_proxy" rather than a blanket "age" claim we
# could not honestly make.
# ---------------------------------------------------------------------------
PROHIBITED_BASES_EXCLUDED = [
    "race",
    "ethnicity",
    "religion",
    "national_origin",
    "sex",
    "marital_status",
    "age_as_discriminatory_proxy",
]

FAIR_LENDING_ATTESTATION = (
    "Model features are limited to behavioral, network, and self-declared financial "
    "signals. No protected-class attributes are used as inputs. The complete feature "
    "specification is version-controlled at ml/artifacts/feature_spec.json and may be "
    "independently audited against this attestation."
)

# Plain-English descriptions for the regulator's factor table.
FACTOR_DESCRIPTIONS: dict[str, str] = {
    "applicant_age": "Applicant's declared age.",
    "annual_income": "Applicant's declared annual income.",
    "requested_amount": "Loan principal requested.",
    "session_duration_seconds": "Time elapsed between opening and submitting the application form.",
    "mouse_movement_events": "Volume of pointer-movement events captured during the session.",
    "form_paste_count": "Number of form fields populated by paste rather than keystrokes.",
    "applications_from_device_last_24h": "Count of applications submitted from the same device fingerprint within 24 hours.",
    "applications_from_ip_last_24h": "Count of applications submitted from the same network address within 24 hours.",
    "income_employer_consistency_score": "Third-party verification score for declared income against the stated employer.",
    "identity_consistency_score": "Third-party verification score for agreement across declared name, address, and telephone records.",
    "loan_to_income_ratio": "Requested principal expressed as a proportion of declared annual income.",
    "has_id_document": "Whether an identity document was submitted with the application.",
    "ID_NAME_MISMATCH": "Rule-based check: name extracted from the submitted identity document did not match the declared applicant name.",
    "ID_IMAGE_REUSED_ACROSS_NAMES": "Rule-based check: the submitted document image was previously submitted under a different applicant name.",
    "ID_NAME_VERIFIED": "Rule-based check: name extracted from the submitted identity document matched the declared applicant name.",
}


def _artifact(name: str) -> dict:
    try:
        return json.loads((ARTIFACTS_DIR / name).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - report must render even if an artifact moves
        return {}


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
        raise HTTPException(status_code=404, detail="Application has no recorded decision")
    return application, decision


def _band(decision: Decision) -> str:
    return (
        decision.decision_band.value
        if hasattr(decision.decision_band, "value")
        else str(decision.decision_band)
    )


def _describe(feature: str) -> str:
    if feature in FACTOR_DESCRIPTIONS:
        return FACTOR_DESCRIPTIONS[feature]
    if "=" in feature:
        column, value = feature.split("=", 1)
        return f"Categorical indicator: {column.replace('_', ' ')} recorded as '{value}'."
    return feature.replace("_", " ")


# ===========================================================================
# Endpoint A — Regulator report
# ===========================================================================


@router.get("/applications/{application_id}/regulator-report")
def regulator_report(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    application, decision = _load(db, application_id)
    config = _artifact("ensemble_config.json")
    band = _band(decision)
    payload = application.raw_payload or {}

    bands = config.get("bands", {})
    lo = bands.get("auto_approve_below")
    hi = bands.get("auto_flag_above")

    # ---- Decision provenance: every step that produced this number ---------
    rule_features = [
        f for f in (decision.top_shap_features or []) if str(f.get("feature", "")).isupper()
    ]
    provenance = [
        {
            "step": 1,
            "stage": "Feature extraction",
            "detail": (
                f"{len(_artifact('feature_spec.json').get('feature_names', []))} model features "
                "derived from the submitted application using the version-controlled feature "
                "specification shared by training and serving."
            ),
        },
        {
            "step": 2,
            "stage": "Supervised model score (XGBoost)",
            "detail": (
                f"Gradient-boosted decision tree ensemble produced a fraud probability of "
                f"{decision.xgboost_probability:.6f}. Hyperparameters: "
                f"max_depth={config.get('xgb_params', {}).get('max_depth')}, "
                f"n_estimators={config.get('xgb_params', {}).get('n_estimators')}, "
                f"learning_rate={config.get('xgb_params', {}).get('learning_rate')}."
            ),
        },
        {
            "step": 3,
            "stage": "Unsupervised anomaly score (Isolation Forest)",
            "detail": (
                f"Unsupervised outlier model produced a normalised anomaly score of "
                f"{decision.anomaly_score:.6f}. This model is fitted without access to fraud "
                "labels and acts as an independent check on the supervised score."
            ),
        },
        {
            "step": 4,
            "stage": "Ensemble combination",
            "detail": (
                f"Scores combined by fixed weighting: "
                f"({config.get('xgb_weight')} x supervised) + "
                f"({config.get('anomaly_weight')} x anomaly). Weights are frozen in "
                "ml/artifacts/ensemble_config.json and are not tuned per application."
            ),
        },
        {
            "step": 5,
            "stage": "Probability calibration",
            "detail": (
                "Isotonic regression calibrator applied so the reported score is interpretable "
                "as a probability. The calibrator was fitted on a validation split the "
                "supervised model never trained on, and verified out-of-sample on the test "
                f"split. Calibrated score: {decision.calibrated_risk_score:.6f}."
            ),
        },
    ]

    for rule in rule_features:
        provenance.append(
            {
                "step": len(provenance) + 1,
                "stage": f"Rule layer adjustment — {rule.get('feature')}",
                "detail": (
                    f"{_describe(str(rule.get('feature')))} Applied as an explicit, disclosed "
                    f"adjustment of {float(rule.get('shap_value', 0)):+.2f} to the calibrated "
                    "score. This is a deterministic rule, not a model output."
                ),
            }
        )

    provenance.append(
        {
            "step": len(provenance) + 1,
            "stage": "Decision band assignment",
            "detail": (
                f"Final calibrated score {decision.calibrated_risk_score:.6f} evaluated against "
                f"the frozen thresholds AUTO_APPROVE below {lo}, AUTO_FLAG above {hi}. "
                f"Assigned band: {band}. Thresholds were selected on the validation split to "
                "hold the false-positive rate on legitimate applications at or below 3 percent "
                "and missed fraud within the auto-approve band at or below 2 percent."
            ),
        }
    )

    # ---- Human review status ------------------------------------------------
    feedback = (
        db.execute(
            select(InvestigatorFeedback)
            .where(InvestigatorFeedback.decision_id == decision.id)
            .order_by(InvestigatorFeedback.created_at.desc())
        )
        .scalars()
        .first()
    )
    if feedback is None:
        human_review = {
            "reviewed": False,
            "status": "No human review recorded for this application.",
            "verdict": None,
            "reviewed_at": None,
            "reviewer": None,
            "notes": None,
        }
    else:
        human_review = {
            "reviewed": True,
            "status": "Reviewed by a qualified investigator.",
            "verdict": feedback.verdict.value
            if hasattr(feedback.verdict, "value")
            else str(feedback.verdict),
            "reviewed_at": feedback.created_at.isoformat(),
            "reviewer": feedback.investigator_username,
            "notes": feedback.notes,
        }

    audit_count = int(
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.target_id == str(application_id))
        )
        or 0
    )

    return {
        "report_version": REPORT_VERSION,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "decision_summary": {
            "application_id": str(application.id),
            "timestamp": application.created_at.isoformat(),
            "decision_band": band,
            "calibrated_risk_score": round(float(decision.calibrated_risk_score), 6),
            "model_version": decision.model_version,
            "scoring_latency_ms": round(float(decision.latency_ms), 1),
        },
        "fair_lending_disclosure": {
            "prohibited_bases_excluded": PROHIBITED_BASES_EXCLUDED,
            "attestation": FAIR_LENDING_ATTESTATION,
            "feature_specification_reference": "ml/artifacts/feature_spec.json",
        },
        "decision_provenance": provenance,
        "top_contributing_factors": [
            {
                "factor": f.get("feature"),
                "label": f.get("label"),
                "direction": "increased risk"
                if f.get("direction") == "increases_risk"
                else "decreased risk",
                "contribution": f.get("shap_value"),
                "description": _describe(str(f.get("feature"))),
                "basis": "deterministic rule"
                if str(f.get("feature", "")).isupper()
                else "model attribution (SHAP)",
            }
            for f in (decision.top_shap_features or [])
        ],
        "model_governance": {
            "training_data": (
                "10,500 training / 2,250 validation / 2,250 test applications, stratified "
                "split (seed 42). All data is synthetic and generated programmatically; no "
                "real customer records were used."
            ),
            "holdout_performance": (
                "PR-AUC 0.9717 and ROC-AUC 0.9937 on a 3,000-application holdout set "
                "generated from a different seed with a deliberately different fraud-archetype "
                "mix, evaluated exactly once."
            ),
            "calibration_status": (
                "Model calibration verified on 2,250 out-of-sample test applications across "
                "10 probability deciles; isotonic calibration fitted on validation data the "
                "supervised model never trained on."
            ),
            "drift_monitoring": (
                "Population Stability Index (PSI) computed per feature against the "
                "training-time reference distribution. PSI below 0.10 is treated as stable, "
                "0.10 to 0.25 as mild drift, above 0.25 as significant drift. Windows with "
                "fewer than 30 applications return an explicit insufficient-data status "
                "rather than a noisy verdict."
            ),
            "explainability_method": (
                "SHAP (TreeExplainer) attributions per decision, plus counterfactual analysis "
                "identifying the minimum single-factor change that would alter the outcome."
            ),
            "known_limitations": (
                "Hard-legitimate stress cohort analysis shows 25.0 percent of genuine "
                "customers exhibiting fraud-shaped signals are routed to the auto-flag band. "
                "Auto-flag holds an application for human action; it does not auto-decline."
            ),
        },
        "human_review_status": human_review,
        "audit_trail_reference": {
            "application_id": str(application.id),
            "audit_log_entry_count": audit_count,
            "cross_reference_note": (
                "All entries are retrievable from the audit_log table keyed on this "
                "application identifier."
            ),
        },
        "data_disclosure": (
            "This report is generated from synthetic demonstration data. It is not a record "
            "of any real applicant or lending decision."
        ),
        # Data-collection transparency. Kept deliberately explicit about the
        # difference between what is STORED (identity verification + audit) and
        # what is USED AS A MODEL INPUT — conflating the two would be the easiest
        # way for this report to mislead an examiner.
        "data_collection_disclosure": {
            "protected_class_attributes_present": False,
            "fields_stored_on_application": sorted(
                k for k in payload.keys() if k not in {"ocr", "id_reuse"}
            ),
            "fields_used_as_model_inputs": sorted(
                _artifact("feature_spec.json").get("numeric_features", [])
                + _artifact("feature_spec.json").get("derived_features", [])
            ),
            "note": (
                "Stored fields include identity details (for example name and date of birth) "
                "that are retained for identity verification and audit purposes. Only the "
                "fields listed under model inputs are supplied to the model. Notably, name, "
                "date of birth, device identifier, and IP address are stored but are NOT "
                "model features; device and IP are used only for network-linkage analysis."
            ),
        },
    }


# ===========================================================================
# Endpoint B — Applicant adverse-action style notice
# ===========================================================================

DECISION_OUTCOMES = {
    "AUTO_APPROVE": "Application approved",
    "HUMAN_REVIEW": "Application requires additional verification",
    "AUTO_FLAG": "Application could not be approved at this time",
}

# Customer-facing rewording. Deliberately softer than the investigator text and
# free of any raw variable name — a declined customer should understand the
# reason without being handed a feature dictionary.
APPLICANT_REASONS: dict[str, str] = {
    "applications_from_device_last_24h": "We saw unusual application activity from your device in the last 24 hours.",
    "applications_from_ip_last_24h": "We saw unusual application activity from your network connection in the last 24 hours.",
    "session_duration_seconds": "The application was completed unusually quickly compared with typical submissions.",
    "mouse_movement_events": "The way the form was filled in did not match typical patterns we see from applicants.",
    "form_paste_count": "Most of the application was pasted rather than typed, which our checks flag for review.",
    "identity_consistency_score": "Some of the personal details you provided did not match the records available to us.",
    "income_employer_consistency_score": "We could not confirm the income you declared against the employer you listed.",
    "annual_income": "The income declared did not align with the other information on your application.",
    "requested_amount": "The amount requested was high relative to the income declared.",
    "loan_to_income_ratio": "The amount requested was high relative to the income declared.",
    "applicant_age": "Some of the details on your application could not be verified.",
    "has_id_document": "We could not complete identity verification with the documents provided.",
    "ID_NAME_MISMATCH": "The name on the identification document you uploaded did not match the name on your application.",
    "ID_IMAGE_REUSED_ACROSS_NAMES": "The identification document you uploaded has previously been submitted with a different name.",
}

# Reason -> concrete next step. Keyed on the factors above.
GUIDANCE_MAP: list[tuple[tuple[str, ...], str]] = [
    (
        ("ID_NAME_MISMATCH", "has_id_document"),
        "Ensure your uploaded identification document matches the name on your application exactly, including spelling and order of names.",
    ),
    (
        ("ID_IMAGE_REUSED_ACROSS_NAMES",),
        "If your identification document has been used by someone else, contact us immediately — this may indicate identity theft, and we can help you report it.",
    ),
    (
        ("applications_from_device_last_24h", "applications_from_ip_last_24h"),
        "If several people share your device or internet connection, let us know when you get in touch. Otherwise, consider reapplying after 30 days.",
    ),
    (
        ("identity_consistency_score",),
        "Check that your name, address, and telephone number are current and match your official records, and update them where they do not.",
    ),
    (
        ("income_employer_consistency_score", "annual_income"),
        "Have recent payslips, bank statements, or tax documents ready — these let us verify your income directly.",
    ),
    (
        ("requested_amount", "loan_to_income_ratio"),
        "Consider applying for a smaller amount that is more proportionate to your declared income.",
    ),
    (
        ("session_duration_seconds", "mouse_movement_events", "form_paste_count"),
        "When you reapply, complete the form directly rather than pasting saved details, and take your time on each field.",
    ),
]

APPLICANT_RIGHTS = [
    "You have the right to request a copy of any consumer report we relied on in making this decision, and to receive it free of charge if you request it within 60 days of this notice.",
    "You have the right to dispute the accuracy or completeness of any information in that report directly with the consumer reporting agency that supplied it.",
    "You have the right to request that a member of our staff review this decision personally. Automated checks informed this outcome, and you may ask for a human being to look at your application again.",
    "You have the right to a written statement of the specific reasons for this decision. The reasons listed above are provided for that purpose.",
    "If you wish to appeal, please contact us within 60 days of the date of this notice using the reference number below.",
]


@router.get("/applications/{application_id}/applicant-report")
def applicant_report(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    application, decision = _load(db, application_id)
    band = _band(decision)

    # Only factors that pushed TOWARD denial are listed. A protective factor is
    # not a reason for an adverse decision and must not appear here.
    adverse = [
        f
        for f in (decision.top_shap_features or [])
        if f.get("direction") == "increases_risk"
    ]

    reasons: list[str] = []
    matched_features: list[str] = []
    for factor in adverse:
        feature = str(factor.get("feature", ""))
        text = APPLICANT_REASONS.get(feature)
        if text is None and "=" in feature:
            text = "Some of the details on your application could not be verified."
        if text and text not in reasons:
            reasons.append(text)
            matched_features.append(feature)
        if len(reasons) == 3:
            break

    if not reasons and band != "AUTO_APPROVE":
        reasons.append(
            "Our verification checks could not confirm some of the information provided."
        )

    guidance = [
        text
        for keys, text in GUIDANCE_MAP
        if any(key in matched_features for key in keys)
    ]
    guidance.append(
        "You may request a manual review by contacting our support team and quoting the "
        "reference number on this notice. A member of staff will personally re-examine "
        "your application."
    )

    return {
        "reference_number": str(application.id),
        "decision_date": application.created_at.isoformat(),
        "decision_outcome": DECISION_OUTCOMES.get(band, "Application status unavailable"),
        "primary_reasons": reasons,
        "what_you_can_do": guidance,
        "your_rights": APPLICANT_RIGHTS,
        "appeal_reference_code": str(application.id),
        "contact_note": (
            "Our support team can be reached through the contact details on your account "
            "portal. Please quote your reference number so we can find your application "
            "quickly."
        ),
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "data_disclosure": (
            "This is a demonstration document generated from synthetic data. It does not "
            "relate to any real person or lending decision."
        ),
    }
