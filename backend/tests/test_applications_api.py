"""POST /score and application endpoints against the aegis_test database."""

VALID_PAYLOAD = {
    "applicant_age": 34,
    "annual_income": 61_000,
    "employment_type": "salaried",
    "employer_name": "Sanchez PLC",
    "requested_amount": 12_000,
    "loan_purpose": "debt_consolidation",
    "loan_purpose_text": "Consolidating three credit cards into one fixed monthly payment.",
    "device_id": "api_test_device_1",
    "ip_hash": "api_test_ip_1",
    "session_duration_seconds": 200,
    "mouse_movement_events": 150,
    "form_paste_count": 1,
    "income_employer_consistency_score": 0.85,
    "identity_consistency_score": 0.9,
}


def test_score_valid_payload_returns_full_result(client, auth_headers):
    response = client.post("/score", json=VALID_PAYLOAD, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"]["decision_band"] in ("AUTO_APPROVE", "HUMAN_REVIEW", "AUTO_FLAG")
    assert 0.0 <= body["decision"]["calibrated_risk_score"] <= 1.0
    assert body["decision"]["explanation_text"]
    assert len(body["top_shap_features"]) == 5

    # The scored application is retrievable with full detail.
    detail = client.get(f"/applications/{body['application_id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["decision"]["id"] == body["decision"]["id"]


def test_score_rejects_negative_income(client, auth_headers):
    response = client.post(
        "/score", json={**VALID_PAYLOAD, "annual_income": -5}, headers=auth_headers
    )
    assert response.status_code == 422


def test_score_rejects_underage_applicant(client, auth_headers):
    response = client.post(
        "/score", json={**VALID_PAYLOAD, "applicant_age": 15}, headers=auth_headers
    )
    assert response.status_code == 422


def test_score_rejects_unknown_employment_type(client, auth_headers):
    response = client.post(
        "/score", json={**VALID_PAYLOAD, "employment_type": "astronaut"}, headers=auth_headers
    )
    assert response.status_code == 422


def test_list_applications_and_band_filter(client, auth_headers):
    client.post("/score", json=VALID_PAYLOAD, headers=auth_headers)
    response = client.get("/applications?limit=10", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1

    filtered = client.get("/applications?decision_band=AUTO_FLAG", headers=auth_headers)
    assert filtered.status_code == 200
    assert all(item["decision_band"] == "AUTO_FLAG" for item in filtered.json()["items"])


def test_feedback_roundtrip(client, auth_headers):
    scored = client.post("/score", json=VALID_PAYLOAD, headers=auth_headers).json()
    response = client.post(
        f"/applications/{scored['application_id']}/feedback",
        json={"verdict": "CONFIRMED_LEGITIMATE", "notes": "Verified employment by phone."},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "CONFIRMED_LEGITIMATE"
    assert body["investigator_username"] == "test_investigator"  # from JWT, not payload
