"""ScoringService behaviour on hand-built inputs. No database required."""

from app.ml.scoring_service import ScoringResult, get_scoring_service

LOW_RISK = {
    "applicant_age": 41,
    "annual_income": 72_000.0,
    "employment_type": "salaried",
    "employer_name": "Bray Inc",
    "requested_amount": 9_000.0,
    "loan_purpose": "home_improvement",
    "loan_purpose_text": "Replacing the roof before the winter rains get in.",
    "device_id": "test_device_low",
    "ip_hash": "test_ip_low",
    "session_duration_seconds": 240,
    "mouse_movement_events": 180,
    "form_paste_count": 1,
    "id_document_filename": None,
    "applications_from_device_last_24h": 1,
    "applications_from_ip_last_24h": 1,
    "income_employer_consistency_score": 0.88,
    "identity_consistency_score": 0.91,
}

HIGH_RISK = {
    **LOW_RISK,
    "annual_income": 145_000.0,
    "employment_type": "gig_worker",
    "requested_amount": 45_000.0,
    "loan_purpose_text": "Personal use of funds.",
    "device_id": "test_device_high",
    "ip_hash": "test_ip_high",
    "session_duration_seconds": 25,
    "mouse_movement_events": 2,
    "form_paste_count": 9,
    "applications_from_device_last_24h": 6,
    "applications_from_ip_last_24h": 7,
    "income_employer_consistency_score": 0.11,
    "identity_consistency_score": 0.14,
}


def test_low_risk_application_auto_approves():
    result = get_scoring_service().score(LOW_RISK)
    assert isinstance(result, ScoringResult)
    assert result.decision_band == "AUTO_APPROVE"
    assert result.calibrated_risk_score < 0.01
    assert result.ring_size == 0  # brand-new device/IP cannot be in a ring


def test_high_risk_application_auto_flags():
    result = get_scoring_service().score(HIGH_RISK)
    assert result.decision_band == "AUTO_FLAG"
    assert result.calibrated_risk_score > 0.5
    assert result.counterfactual is not None  # non-best band gets a counterfactual


def test_result_has_all_expected_fields():
    result = get_scoring_service().score(HIGH_RISK)
    assert 0.0 <= result.xgboost_probability <= 1.0
    assert 0.0 <= result.anomaly_score <= 1.0
    assert 0.0 <= result.calibrated_risk_score <= 1.0
    assert result.model_version
    assert result.latency_ms > 0
    assert len(result.top_shap_features) == 5
    for feature in result.top_shap_features:
        assert {"feature", "label", "value", "shap_value", "direction", "explanation"} <= set(feature)


def test_known_ring_device_gets_ring_context():
    service = get_scoring_service()
    device = next(d for d, apps in service.device_index.items() if len(apps) >= 3)
    result = service.score({**LOW_RISK, "device_id": device})
    assert result.ring_size >= 3
    assert len(result.connected_applications) == result.ring_size - 1
