"""OCR extraction, perceptual-hash reuse, and the public multipart intake."""

import json
from pathlib import Path

import pandas as pd
import pytest

from app.routers.demo import DATA_DIR, ID_DOCS_DIR
from app.services.ocr_service import extract_id_fields, names_match

from generate_synthetic_data import id_document_plan  # ml/ is on sys.path


@pytest.fixture(scope="module")
def sample_card() -> dict:
    """A real generated card + the name the generator printed on it."""
    df = pd.read_csv(DATA_DIR / "applications_train.csv")
    row = df[df["id_document_filename"].fillna("").str.len() > 0].iloc[0]
    first, last, _ = id_document_plan(row.application_id, row.fraud_type)
    return {
        "path": ID_DOCS_DIR / row.id_document_filename,
        "printed_name": f"{first} {last}",
    }


def test_ocr_extracts_name_from_real_card(sample_card):
    fields = extract_id_fields(sample_card["path"].read_bytes())
    assert fields["name"] is not None, f"OCR got: {fields['raw_text']!r}"
    assert names_match(fields["name"], sample_card["printed_name"])
    assert fields["id_number"] is not None and fields["id_number"].startswith("SYN-")
    assert fields["dob"] is not None


def test_ocr_handles_unreadable_input():
    fields = extract_id_fields(b"not an image at all")
    assert fields == {"name": None, "dob": None, "id_number": None, "raw_text": ""}


def _apply_payload(name: str, device: str) -> dict:
    return {
        "full_name": name,
        "date_of_birth": "1990-04-12",
        "pan_number": "DEMO12345Z",
        "email": "demo@example.test",
        "mobile": "9999999999",
        "address": "12 Demo Street",
        "city": "Pune",
        "state": "MH",
        "pin_code": "411001",
        "employment_type": "salaried",
        "employer_name": "Sanchez PLC",
        "monthly_income_inr": 90_000,
        "years_in_employment": 4,
        "loan_amount_inr": 400_000,
        "loan_purpose": "home_improvement",
        "purpose_text": "Replacing the roof before the winter rains get in.",
        "device_id": device,
        "ip_hash": device,
        "session_duration_seconds": 220,
        "mouse_movement_events": 160,
        "form_paste_count": 1,
    }


def test_public_apply_with_mismatched_id_flags(client, sample_card, auth_headers):
    """Multipart intake: OCR name != form name must produce the rule signal."""
    image = sample_card["path"].read_bytes()
    response = client.post(
        "/public/apply",
        data={"payload": json.dumps(_apply_payload("Completely Different Person", "ocrtest_dev_1"))},
        files={"id_document": ("card.png", image, "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "received"
    assert body["reference"].startswith("QL-")
    assert names_match(body["id_verification"]["extracted_name"], sample_card["printed_name"])

    # The applicant response leaks no decision - but the investigator sees it.
    app_id = body["reference"].removeprefix("QL-").lower()
    listing = client.get("/applications?limit=5", headers=auth_headers).json()
    match = next(i for i in listing["items"] if i["id"].startswith(app_id))
    assert match["decision_band"] in ("HUMAN_REVIEW", "AUTO_FLAG")

    detail = client.get(f"/applications/{match['id']}", headers=auth_headers).json()
    assert detail["identity_check"]["mismatch"] is True
    assert any(
        f["feature"] == "ID_NAME_MISMATCH" for f in detail["top_shap_features"]
    )


def test_id_reuse_across_names_detected(client, sample_card, auth_headers):
    """Submitting the SAME image under two different names trips the reuse rule."""
    image = sample_card["path"].read_bytes()
    first = client.post(
        "/public/apply",
        data={"payload": json.dumps(_apply_payload("Alex First Identity", "reuse_dev_1"))},
        files={"id_document": ("card.png", image, "image/png")},
    )
    assert first.status_code == 200

    second = client.post(
        "/public/apply",
        data={"payload": json.dumps(_apply_payload("Brand New Person", "reuse_dev_2"))},
        files={"id_document": ("card.png", image, "image/png")},
    )
    assert second.status_code == 200
    app_id = second.json()["reference"].removeprefix("QL-").lower()

    listing = client.get("/applications?limit=10", headers=auth_headers).json()
    match = next(i for i in listing["items"] if i["id"].startswith(app_id))
    detail = client.get(f"/applications/{match['id']}", headers=auth_headers).json()

    assert detail["identity_check"]["reused_across_names"] is True
    assert detail["identity_check"]["prior_uses"] >= 1
    assert any(
        f["feature"] == "ID_IMAGE_REUSED_ACROSS_NAMES" for f in detail["top_shap_features"]
    )


def test_ring_device_endpoint_is_public(client):
    response = client.get("/demo/ring-device")
    assert response.status_code == 200
    body = response.json()
    assert body["known_ring_size"] >= 4
    assert body["known_fraud_fraction"] >= 0.75
