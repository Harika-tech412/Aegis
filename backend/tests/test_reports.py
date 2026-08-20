"""Regulator and applicant report endpoints.

These endpoints re-present an existing decision; they must add no new data and,
critically, the customer-facing notice must never leak a raw model variable
name or any protected-class attribute.
"""

import json

import pytest

from app.ml.scoring_service import ARTIFACTS_DIR

# Categories the fair-lending attestation claims are excluded. Neither payload
# may carry these as data fields.
PROTECTED = [
    "race",
    "ethnicity",
    "religion",
    "national_origin",
    "sex",
    "gender",
    "marital_status",
    "disability",
]

REGULATOR_SECTIONS = [
    "decision_summary",
    "fair_lending_disclosure",
    "decision_provenance",
    "top_contributing_factors",
    "model_governance",
    "human_review_status",
    "audit_trail_reference",
    "report_generated_at",
    "report_version",
]

APPLICANT_SECTIONS = [
    "reference_number",
    "decision_date",
    "decision_outcome",
    "primary_reasons",
    "what_you_can_do",
    "your_rights",
    "appeal_reference_code",
    "report_generated_at",
]


@pytest.fixture(scope="module")
def flagged_application(TestSession):
    """Score a genuinely AUTO_FLAG application through the real pipeline."""
    from app.ml.scoring_service import get_scoring_service
    from app.routers.applications import persist_scored_application
    from app.services.llm_explainer import template_explanation

    service = get_scoring_service()
    payload = {
        "applicant_age": 29,
        "annual_income": 145_000.0,
        "employment_type": "gig_worker",
        "employer_name": "Reports Test Co",
        "requested_amount": 45_000.0,
        "loan_purpose": "business",
        "loan_purpose_text": "Personal use of funds.",
        "device_id": "reports_test_device",
        "ip_hash": "reports_test_ip",
        "session_duration_seconds": 24,
        "mouse_movement_events": 2,
        "form_paste_count": 9,
        "id_document_filename": None,
        "applications_from_device_last_24h": 6,
        "applications_from_ip_last_24h": 7,
        "income_employer_consistency_score": 0.09,
        "identity_consistency_score": 0.12,
    }
    result = service.score(payload)
    assert result.decision_band == "AUTO_FLAG", result.decision_band

    session = TestSession()
    try:
        app, _decision = persist_scored_application(
            session,
            payload,
            result,
            template_explanation(result),
            "template",
            requested_by="test",
            id_document_filename=None,
        )
        session.commit()
        return str(app.id)
    finally:
        session.close()


def test_both_reports_return_200(client, auth_headers, flagged_application):
    for path in ("regulator-report", "applicant-report"):
        response = client.get(
            f"/applications/{flagged_application}/{path}", headers=auth_headers
        )
        assert response.status_code == 200, f"{path}: {response.text}"


def test_reports_require_auth(client, flagged_application):
    for path in ("regulator-report", "applicant-report"):
        assert client.get(f"/applications/{flagged_application}/{path}").status_code == 401


def test_regulator_report_contains_all_sections(client, auth_headers, flagged_application):
    body = client.get(
        f"/applications/{flagged_application}/regulator-report", headers=auth_headers
    ).json()

    for section in REGULATOR_SECTIONS:
        assert section in body, f"missing section: {section}"

    # Fair-lending disclosure names every prohibited basis and attests inputs.
    disclosure = body["fair_lending_disclosure"]
    assert len(disclosure["prohibited_bases_excluded"]) >= 7
    assert "No protected-class attributes are used as inputs" in disclosure["attestation"]

    # Provenance is an ordered, complete pipeline walk ending in band assignment.
    steps = body["decision_provenance"]
    assert [s["step"] for s in steps] == list(range(1, len(steps) + 1))
    assert "Feature extraction" in steps[0]["stage"]
    assert "Decision band assignment" in steps[-1]["stage"]
    stages = " ".join(s["stage"] for s in steps).lower()
    for expected in ("xgboost", "isolation forest", "ensemble", "calibration"):
        assert expected in stages, f"provenance missing {expected}"

    assert body["decision_summary"]["decision_band"] == "AUTO_FLAG"
    assert body["top_contributing_factors"]
    assert body["audit_trail_reference"]["audit_log_entry_count"] >= 0
    # No human review was recorded for this case - say so explicitly.
    assert body["human_review_status"]["reviewed"] is False
    assert "No human review recorded" in body["human_review_status"]["status"]


def test_applicant_report_leaks_no_raw_feature_names(client, auth_headers, flagged_application):
    """The customer-facing notice must contain no technical variable names."""
    body = client.get(
        f"/applications/{flagged_application}/applicant-report", headers=auth_headers
    ).json()

    for section in APPLICANT_SECTIONS:
        assert section in body, f"missing section: {section}"

    # Audit every customer-visible string against the real feature spec.
    spec = json.loads((ARTIFACTS_DIR / "feature_spec.json").read_text())
    raw_names = set(spec["numeric_features"]) | set(spec["derived_features"])
    raw_names |= set(spec["feature_names"])
    raw_names |= {"ID_NAME_MISMATCH", "ID_IMAGE_REUSED_ACROSS_NAMES", "SHAP", "shap"}

    customer_text = " ".join(
        [
            body["decision_outcome"],
            *body["primary_reasons"],
            *body["what_you_can_do"],
            *body["your_rights"],
            body["contact_note"],
        ]
    )
    for name in raw_names:
        assert name not in customer_text, f"leaked raw feature name: {name}"

    # And no ML jargon.
    for jargon in ("xgboost", "isolation forest", "calibrat", "risk_score", "auto_flag"):
        assert jargon not in customer_text.lower(), f"leaked jargon: {jargon}"

    assert body["decision_outcome"] == "Application could not be approved at this time"
    assert 1 <= len(body["primary_reasons"]) <= 3
    assert any("manual review" in g for g in body["what_you_can_do"])


def test_applicant_report_lists_only_adverse_reasons(client, auth_headers, flagged_application):
    """Protective (risk-reducing) factors are not reasons for an adverse decision."""
    detail = client.get(
        f"/applications/{flagged_application}", headers=auth_headers
    ).json()
    protective = [
        f for f in detail["top_shap_features"] if f["direction"] == "decreases_risk"
    ]
    body = client.get(
        f"/applications/{flagged_application}/applicant-report", headers=auth_headers
    ).json()

    assert len(body["primary_reasons"]) >= 1
    joined = " ".join(body["primary_reasons"])
    for factor in protective:
        assert factor["label"] not in joined


def test_neither_report_exposes_protected_attributes(client, auth_headers, flagged_application):
    for path in ("regulator-report", "applicant-report"):
        response = client.get(
            f"/applications/{flagged_application}/{path}", headers=auth_headers
        )
        body = response.json()
        if path == "applicant-report":
            # No protected attribute may appear even as a JSON key.
            raw = response.text.lower()
            for attribute in PROTECTED:
                assert f'"{attribute}"' not in raw, f"{path} exposes {attribute}"
        else:
            assert (
                body["data_collection_disclosure"]["protected_class_attributes_present"] is False
            )
            recorded = body["data_collection_disclosure"]["fields_stored_on_application"]
            for attribute in PROTECTED:
                assert attribute not in recorded, f"payload records {attribute}"
