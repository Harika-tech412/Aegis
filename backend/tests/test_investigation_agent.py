"""Proof that the LangGraph investigation agent genuinely branches.

These tests assert on the CONTENT of investigation_log — which nodes ran and
what they said — not merely that a response came back. A fixed script wearing
an agent's name would fail Test A (it would run every node on an easy case)
and Test D (its "findings" would not change when live data changes).
"""

import uuid

import pytest
from sqlalchemy import select

from app.models import Application, Decision, InvestigatorFeedback
from app.services import investigation_agent

pytestmark = pytest.mark.usefixtures("seeded_cases")


def _steps(payload: dict) -> list[str]:
    return [entry["step"] for entry in payload["investigation_log"]]


def _descriptions(payload: dict) -> str:
    return " ".join(entry["description"] for entry in payload["investigation_log"]).lower()


@pytest.fixture(scope="module")
def seeded_cases(TestSession):
    """Score a clean no-ring case and a ring-linked case into the test DB.

    Built through the real scoring path so the agent reads genuine decisions,
    not hand-written fixtures.
    """
    from app.ml.scoring_service import get_scoring_service
    from app.routers.applications import persist_scored_application
    from app.services.llm_explainer import template_explanation

    service = get_scoring_service()
    session = TestSession()
    made: dict[str, list[str]] = {"clean": [], "ring": []}
    try:
        base = {
            "applicant_age": 41,
            "annual_income": 72_000.0,
            "employment_type": "salaried",
            "employer_name": "Bray Inc",
            "requested_amount": 9_000.0,
            "loan_purpose": "home_improvement",
            "loan_purpose_text": "Replacing the roof before the winter rains get in.",
            "session_duration_seconds": 240,
            "mouse_movement_events": 180,
            "form_paste_count": 1,
            "id_document_filename": None,
            "applications_from_device_last_24h": 1,
            "applications_from_ip_last_24h": 1,
            "income_employer_consistency_score": 0.88,
            "identity_consistency_score": 0.91,
        }

        # (1) Clean case: brand-new device/IP => AUTO_APPROVE, ring_size 0.
        clean = {**base, "device_id": "agent_clean_dev", "ip_hash": "agent_clean_ip"}
        result = service.score(clean)
        assert result.decision_band == "AUTO_APPROVE" and result.ring_size == 0
        app, _ = persist_scored_application(
            session, clean, result, template_explanation(result), "template",
            requested_by="test", id_document_filename=None,
        )
        made["clean"].append(str(app.id))

        # (2) Ring cases: reuse a historical device with >=3 known members, so
        # ring_context resolves against ring_lookup.json.
        device = next(d for d, apps in service.device_index.items() if len(apps) >= 4)
        for i in range(2):
            ring_payload = {
                **base,
                "device_id": device,
                "ip_hash": f"agent_ring_ip_{i}",
                "applications_from_device_last_24h": 4,
            }
            ring_result = service.score(ring_payload)
            assert ring_result.ring_size > 0
            ring_app, _ = persist_scored_application(
                session, ring_payload, ring_result,
                template_explanation(ring_result), "template",
                requested_by="test", id_document_filename=None,
            )
            made["ring"].append(str(ring_app.id))
        session.commit()
    finally:
        session.close()
    return made


# ---------------------------------------------------------------------------
# Test A — the agent does LESS on an easy case
# ---------------------------------------------------------------------------


def test_a_clean_case_short_circuits_without_llm(client, auth_headers, seeded_cases, monkeypatch):
    """AUTO_APPROVE + no ring must take the quick_exit branch only."""
    calls = []

    def _spy(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(investigation_agent, "_ask_groq", _spy)

    app_id = seeded_cases["clean"][0]
    response = client.get(f"/applications/{app_id}/investigate?refresh=true", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    # EXACTLY one step, and it is quick_exit — ring/similar/drift never ran.
    assert _steps(body) == ["quick_exit"], _steps(body)
    for skipped in ("check_ring", "check_ring_feedback", "check_similar_cases",
                    "check_drift", "synthesize"):
        assert skipped not in _steps(body)

    # No LLM call was made for synthesis.
    assert calls == [], f"quick-exit path called the LLM {len(calls)} time(s)"
    assert body["synthesis_source"] == "quick_exit"
    assert body["recommended_action"] == "No further action needed"


# ---------------------------------------------------------------------------
# Test B — a ring case takes the deep path
# ---------------------------------------------------------------------------


def test_b_ring_case_runs_ring_and_feedback_nodes(client, auth_headers, seeded_cases):
    app_id = seeded_cases["ring"][0]
    response = client.get(f"/applications/{app_id}/investigate?refresh=true", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    steps = _steps(body)

    assert "check_ring" in steps
    assert "check_ring_feedback" in steps  # the ring-only branch fired
    assert "check_similar_cases" in steps
    assert "check_drift" in steps
    assert "synthesize" in steps
    assert "quick_exit" not in steps
    assert steps.index("check_ring") < steps.index("check_ring_feedback")

    assert body["confidence"] in {"HIGH", "MEDIUM", "LOW"}
    assert body["reasoning_summary"]
    # ring_context is asserted directly against the graph's final state below.


def test_b2_ring_context_is_populated_in_final_state(db, seeded_cases):
    """Direct graph invocation: ring_context must be non-null on a ring case."""
    result = investigation_agent.run_investigation(db, seeded_cases["ring"][0])
    assert result["ring_context"] is not None
    assert result["ring_context"]["ring_size"] > 0
    assert result["ring_feedback_history"] is not None


# ---------------------------------------------------------------------------
# Test C — absence of feedback is stated explicitly, not skipped silently
# ---------------------------------------------------------------------------


def test_c_ring_without_feedback_says_so_explicitly(client, auth_headers, seeded_cases, db):
    app_id = seeded_cases["ring"][0]

    # Guarantee a clean slate: remove any feedback on this ring's members.
    result = investigation_agent.run_investigation(db, app_id)
    members = result["ring_context"]["connected_applications"]
    member_uuids = []
    for m in members:
        try:
            member_uuids.append(uuid.UUID(str(m)))
        except ValueError:
            continue
    if member_uuids:
        rows = db.execute(
            select(InvestigatorFeedback)
            .join(Decision, InvestigatorFeedback.decision_id == Decision.id)
            .where(Decision.application_id.in_(member_uuids))
        ).scalars().all()
        for row in rows:
            db.delete(row)
        db.commit()

    response = client.get(f"/applications/{app_id}/investigate?refresh=true", headers=auth_headers)
    body = response.json()

    assert "check_ring_feedback" in _steps(body)
    text = _descriptions(body)
    assert "no prior investigator feedback found" in text, text
    # And it reports how many members it actually looked at.
    assert "ring member" in text


# ---------------------------------------------------------------------------
# Test D — the node queries LIVE data, not a fixture
# ---------------------------------------------------------------------------


def test_d_agent_picks_up_feedback_added_to_a_ring_sibling(
    client, auth_headers, seeded_cases, db
):
    """Adjudicate ONE member of the ring, then investigate a DIFFERENT member.

    Ring membership resolves against the historical ring_lookup index, so the
    sibling has to be one of the real linked applications — mirroring the
    seeded production DB, where those historical ids exist as rows.
    """
    subject_id = seeded_cases["ring"][0]
    subject_ring = investigation_agent.run_investigation(db, subject_id)["ring_context"]
    sibling_id = subject_ring["connected_applications"][0]

    # Materialise that ring member as a real application+decision, exactly as
    # scripts/seed_database.py does (it reuses the historical UUID as the PK).
    if db.get(Application, uuid.UUID(sibling_id)) is None:
        sibling = Application(
            id=uuid.UUID(sibling_id),
            applicant_age=37,
            annual_income=64_000.0,
            employment_type="salaried",
            employer_name="Bray Inc",
            requested_amount=11_000.0,
            loan_purpose="business",
            loan_purpose_text="Working capital.",
            device_id="ring_sibling_device",
            ip_hash="ring_sibling_ip",
            session_duration_seconds=110,
            mouse_movement_events=70,
            form_paste_count=3,
            id_document_filename=None,
            raw_payload={},
        )
        db.add(sibling)
        db.flush()
        db.add(
            Decision(
                application_id=sibling.id,
                model_version="test",
                xgboost_probability=0.9,
                anomaly_score=0.5,
                calibrated_risk_score=0.9,
                decision_band="AUTO_FLAG",
                top_shap_features=[],
                explanation_text="seeded ring sibling",
                ring_size=4,
                ring_risk_score=1.0,
                latency_ms=1.0,
            )
        )
        db.commit()

    # Baseline: the subject's investigation reports no prior feedback.
    before = client.get(
        f"/applications/{subject_id}/investigate?refresh=true", headers=auth_headers
    ).json()
    assert "no prior investigator feedback found" in _descriptions(before)

    # An investigator adjudicates the SIBLING application (a real ring member).
    sibling_decision = (
        db.execute(
            select(Decision)
            .where(Decision.application_id == uuid.UUID(sibling_id))
            .order_by(Decision.created_at.desc())
        )
        .scalars()
        .first()
    )
    db.add(
        InvestigatorFeedback(
            decision_id=sibling_decision.id,
            investigator_username="test_investigator",
            verdict="CONFIRMED_FRAUD",
            notes="Confirmed during ring sweep.",
        )
    )
    db.commit()

    # Re-run the subject's investigation — the agent must now see it.
    after = client.get(
        f"/applications/{subject_id}/investigate?refresh=true", headers=auth_headers
    ).json()
    text = _descriptions(after)

    assert "no prior investigator feedback found" not in text, text
    assert "confirmed_fraud" in text, text
    assert "1 prior verdict" in text, text

    # The live finding propagates into the recommendation.
    assert after["confidence"] == "HIGH"
    assert "escalate" in after["recommended_action"].lower()


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


def test_investigation_is_cached_until_refresh(client, auth_headers, seeded_cases):
    app_id = seeded_cases["clean"][0]
    client.get(f"/applications/{app_id}/investigate?refresh=true", headers=auth_headers)

    cached = client.get(f"/applications/{app_id}/investigate", headers=auth_headers).json()
    assert cached["cached"] is True

    fresh = client.get(
        f"/applications/{app_id}/investigate?refresh=true", headers=auth_headers
    ).json()
    assert fresh["cached"] is False


def test_investigate_requires_auth(client, seeded_cases):
    app_id = seeded_cases["clean"][0]
    assert client.get(f"/applications/{app_id}/investigate").status_code == 401
