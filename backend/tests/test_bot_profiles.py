"""Fraud-bot profile generator (demo-only scripted attack payloads)."""

import json

import pytest

from app.routers.public import PublicApplyRequest

SCENARIOS = ["bot_filler", "identity_theft", "ring_operator"]

# Keys the endpoint adds on top of the submittable payload.
META_KEYS = {"scenario", "scenario_label", "scenario_description", "id_document"}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_bot_profile_is_a_valid_submittable_payload(client, scenario):
    response = client.get(f"/demo/bot-profile?scenario={scenario}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["scenario"] == scenario
    assert body["scenario_label"]
    assert body["scenario_description"]

    # Stripping the metadata must leave something /public/apply accepts.
    payload = {k: v for k, v in body.items() if k not in META_KEYS}
    validated = PublicApplyRequest(**payload)
    assert validated.full_name and validated.employer_name
    assert validated.monthly_income_inr > 0 and validated.loan_amount_inr > 0


def test_bot_filler_has_bot_like_behaviour(client):
    body = client.get("/demo/bot-profile?scenario=bot_filler").json()
    assert body["session_duration_seconds"] <= 8
    assert body["mouse_movement_events"] <= 5
    assert body["form_paste_count"] >= 12  # every text field pasted
    assert body["id_document"] is None


def test_identity_theft_carries_a_mismatched_document(client):
    body = client.get("/demo/bot-profile?scenario=identity_theft").json()
    doc = body["id_document"]
    assert doc is not None
    assert doc["filename"].startswith("id_")
    # The form claims one identity; the document is printed for another.
    assert doc["claimed_name"] == body["full_name"]
    assert doc["id_name"] != doc["claimed_name"]
    # Behaviour is deliberately human-looking - the tell is the document.
    assert body["session_duration_seconds"] >= 180
    assert body["mouse_movement_events"] >= 120


def test_ring_operator_uses_a_known_ring_device(client):
    body = client.get("/demo/bot-profile?scenario=ring_operator").json()
    known = client.get("/demo/ring-device").json()
    assert body["device_id"] == known["device_id"]
    assert body["applications_from_device_last_24h"] >= 2


def test_unknown_scenario_rejected(client):
    assert client.get("/demo/bot-profile?scenario=nonsense").status_code == 422
