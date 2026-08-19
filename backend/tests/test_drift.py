"""Drift endpoint detects a skewed traffic window."""

import uuid

from app.models import Application

# Values deliberately far from the training distribution: income pinned at the
# ceiling, bot-like sessions, heavy pasting.
SKEWED_PAYLOAD = {
    "applicant_age": 22,
    "annual_income": 245_000.0,
    "requested_amount": 49_500.0,
    "session_duration_seconds": 15,
    "mouse_movement_events": 1,
    "form_paste_count": 11,
    "applications_from_device_last_24h": 8,
    "applications_from_ip_last_24h": 9,
    "income_employer_consistency_score": 0.05,
    "identity_consistency_score": 0.06,
}


def _seed_skewed_applications(db, n: int = 40) -> None:
    for i in range(n):
        db.add(
            Application(
                applicant_age=SKEWED_PAYLOAD["applicant_age"],
                annual_income=SKEWED_PAYLOAD["annual_income"],
                employment_type="gig_worker",
                employer_name="Drift Test Co",
                requested_amount=SKEWED_PAYLOAD["requested_amount"],
                loan_purpose="business",
                loan_purpose_text="drift test",
                device_id=f"drift_device_{uuid.uuid4().hex[:8]}",
                ip_hash=f"drift_ip_{uuid.uuid4().hex[:8]}",
                session_duration_seconds=SKEWED_PAYLOAD["session_duration_seconds"],
                mouse_movement_events=SKEWED_PAYLOAD["mouse_movement_events"],
                form_paste_count=SKEWED_PAYLOAD["form_paste_count"],
                id_document_filename=None,
                raw_payload=SKEWED_PAYLOAD,
            )
        )
    db.commit()


def test_drift_endpoint_requires_auth(client):
    assert client.get("/monitoring/drift").status_code == 401


def test_drift_detected_on_skewed_window(client, auth_headers, db):
    _seed_skewed_applications(db, n=40)

    response = client.get("/monitoring/drift?window_hours=24", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["recent_applications"] >= 40
    assert body["overall_drift_status"] in ("MILD_DRIFT", "SIGNIFICANT_DRIFT")
    assert body["summary"]

    by_feature = {f["feature"]: f for f in body["features"]}
    # Income pinned at the ceiling must register as significant drift.
    assert by_feature["annual_income"]["psi"] > 0.25
    assert by_feature["form_paste_count"]["psi"] > 0.25


def test_drift_window_param_validated(client, auth_headers):
    assert client.get("/monitoring/drift?window_hours=0", headers=auth_headers).status_code == 422
    assert client.get("/monitoring/drift?window_hours=999", headers=auth_headers).status_code == 422
