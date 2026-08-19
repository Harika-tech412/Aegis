"""Sample-ID endpoints and the rule-based ID-name mismatch signal."""

from tests.test_applications_api import VALID_PAYLOAD


def test_sample_id_requires_auth(client):
    assert client.get("/demo/sample-id").status_code == 401


def test_sample_id_matched_and_mismatched(client, auth_headers):
    matched = client.get("/demo/sample-id?mismatch=false", headers=auth_headers).json()
    assert matched["mismatch"] is False
    assert matched["applicant_name"].strip().lower() == matched["id_name"].strip().lower()

    mismatched = client.get("/demo/sample-id?mismatch=true", headers=auth_headers).json()
    assert mismatched["mismatch"] is True
    assert mismatched["applicant_name"].strip().lower() != mismatched["id_name"].strip().lower()

    # The referenced image is servable.
    image = client.get(f"/demo/id-image/{mismatched['filename']}", headers=auth_headers)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def test_id_image_blocks_path_traversal(client, auth_headers):
    assert client.get("/demo/id-image/..%2F..%2Fetc%2Fpasswd", headers=auth_headers).status_code == 404
    assert client.get("/demo/id-image/notreal.png", headers=auth_headers).status_code == 404


def test_score_with_id_name_mismatch_boosts_risk(client, auth_headers):
    base = client.post(
        "/score",
        json={**VALID_PAYLOAD, "device_id": "idcheck_base", "ip_hash": "idcheck_base"},
        headers=auth_headers,
    ).json()

    boosted = client.post(
        "/score",
        json={
            **VALID_PAYLOAD,
            "device_id": "idcheck_boost",
            "ip_hash": "idcheck_boost",
            "applicant_name": "Jordan Avery",
            "id_document_uploaded_name": "Casey Morgan",
        },
        headers=auth_headers,
    ).json()

    assert (
        boosted["decision"]["calibrated_risk_score"]
        >= base["decision"]["calibrated_risk_score"] + 0.29
    )
    rule = boosted["top_shap_features"][0]
    assert rule["feature"] == "id_name_mismatch"
    assert "does not match" in rule["explanation"]

    # Detail endpoint surfaces the identity check for the UI panel.
    detail = client.get(
        f"/applications/{boosted['application_id']}", headers=auth_headers
    ).json()
    assert detail["identity_check"]["mismatch"] is True
    assert detail["identity_check"]["applicant_name"] == "Jordan Avery"


def test_score_with_matching_id_name_adds_no_boost(client, auth_headers):
    result = client.post(
        "/score",
        json={
            **VALID_PAYLOAD,
            "device_id": "idcheck_match",
            "ip_hash": "idcheck_match",
            "applicant_name": "Jordan Avery",
            "id_document_uploaded_name": "jordan avery",  # case-insensitive match
        },
        headers=auth_headers,
    ).json()
    assert all(f["feature"] != "id_name_mismatch" for f in result["top_shap_features"])
