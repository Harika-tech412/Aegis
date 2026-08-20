"""Proof that institutional memory is LIVE memory, not a dressed-up fixture.

The load-bearing test is `test_memory_is_a_live_query`: it runs the agent,
asserts memory found nothing, submits a real verdict through the real endpoint,
re-runs the agent, and asserts the log CHANGED. A static corpus cannot pass
that — the same discipline as the ring-feedback Test D.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models import CaseMemory, Decision
from app.services import case_memory, investigation_agent


def _steps(payload: dict) -> list[str]:
    return [entry["step"] for entry in payload["investigation_log"]]


def _memory_step(payload: dict) -> str:
    for entry in payload["investigation_log"]:
        if entry["step"] == "check_investigator_memory":
            return entry["description"]
    return ""


# A signature is dominated by declared income / employment / loan purpose /
# session behaviour, so two applications built from this same base read as the
# same risk pattern to the embedder while remaining distinct applications.
SHARED_PATTERN = {
    "applicant_age": 29,
    "annual_income": 26_000.0,
    "employment_type": "self_employed",
    "employer_name": "Halvers Trading",
    "requested_amount": 34_000.0,
    "loan_purpose": "business",
    "loan_purpose_text": "Urgent working capital for a new import contract.",
    "session_duration_seconds": 47,
    "mouse_movement_events": 11,
    "form_paste_count": 9,
    "id_document_filename": None,
    "applications_from_device_last_24h": 5,
    "applications_from_ip_last_24h": 5,
    "income_employer_consistency_score": 0.31,
    "identity_consistency_score": 0.28,
}


@pytest.fixture(scope="module")
def memory_pair(TestSession):
    """Two applications with the SAME risk pattern but different devices/IPs.

    Scored through the real pipeline so the agent reads genuine decisions.
    Distinct device/IP values keep them out of each other's ring, which is what
    makes the memory hit attributable to pattern similarity rather than to the
    ring-feedback node.
    """
    from app.ml.scoring_service import get_scoring_service
    from app.routers.applications import persist_scored_application
    from app.services.llm_explainer import template_explanation

    service = get_scoring_service()
    session = TestSession()
    ids = []
    try:
        for tag in ("precedent", "subject"):
            payload = {
                **SHARED_PATTERN,
                "device_id": f"mem_{tag}_device_{uuid.uuid4().hex[:8]}",
                "ip_hash": f"mem_{tag}_ip_{uuid.uuid4().hex[:8]}",
            }
            result = service.score(payload)
            # The memory node lives on the deep branch only, so this pattern
            # must not be triaged away. Asserted here so a scoring shift shows
            # up as an explicit fixture failure, not a confusing test failure.
            assert result.decision_band != "AUTO_APPROVE", (
                f"shared pattern scored {result.decision_band}; it must reach the "
                "deep investigation branch for these tests to mean anything"
            )
            app, _ = persist_scored_application(
                session,
                payload,
                result,
                template_explanation(result),
                "template",
                requested_by="test",
                id_document_filename=None,
            )
            ids.append(str(app.id))
        session.commit()
    finally:
        session.close()
    return {"precedent": ids[0], "subject": ids[1]}


# ---------------------------------------------------------------------------
# 1. A verdict creates a memory with a real embedding
# ---------------------------------------------------------------------------


def test_feedback_writes_a_case_memory_row(client, auth_headers, memory_pair, db):
    app_id = memory_pair["precedent"]

    response = client.post(
        f"/applications/{app_id}/feedback",
        json={"verdict": "CONFIRMED_FRAUD", "notes": "Confirmed during memory test."},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    memory = (
        db.execute(
            select(CaseMemory).where(CaseMemory.application_id == uuid.UUID(app_id))
        )
        .scalars()
        .first()
    )
    assert memory is not None, "submitting a verdict did not create a case_memory row"
    assert memory.source == case_memory.SOURCE_LIVE
    assert memory.feedback_id is not None
    assert (memory.verdict.value if hasattr(memory.verdict, "value") else memory.verdict) == (
        "CONFIRMED_FRAUD"
    )

    # A real 384-dim embedding, not a placeholder.
    vector = list(memory.embedding)
    assert len(vector) == 384
    assert any(abs(float(v)) > 1e-6 for v in vector), "embedding is all zeros"

    # And the signature actually describes the case.
    assert memory.signature_text.strip()
    assert "income" in memory.signature_text.lower()


# ---------------------------------------------------------------------------
# 2. THE PROOF: the memory node queries live data
# ---------------------------------------------------------------------------


def test_memory_is_a_live_query_not_a_fixture(client, auth_headers, memory_pair, db):
    """Same discipline as the ring-feedback Test D: assert the log CHANGED.

    Run the agent on the subject before any comparable verdict exists, then add
    one through the real endpoint, then re-run. A hardcoded step would produce
    identical text both times.
    """
    subject_id = memory_pair["subject"]
    precedent_id = memory_pair["precedent"]

    # Clear every memory so "before" is genuinely empty of comparable precedent.
    for row in db.execute(select(CaseMemory)).scalars().all():
        db.delete(row)
    db.commit()

    before = client.get(
        f"/applications/{subject_id}/investigate?refresh=true", headers=auth_headers
    ).json()
    assert "check_investigator_memory" in _steps(before)
    before_text = _memory_step(before).lower()
    assert "no investigator verdicts have been recorded yet" in before_text, before_text

    # A real investigator verdict on the OTHER application, via the real endpoint.
    posted = client.post(
        f"/applications/{precedent_id}/feedback",
        json={"verdict": "CONFIRMED_FRAUD", "notes": "Confirmed ahead of live-query proof."},
        headers=auth_headers,
    )
    assert posted.status_code == 200, posted.text

    stored = (
        db.execute(
            select(CaseMemory).where(CaseMemory.application_id == uuid.UUID(precedent_id))
        )
        .scalars()
        .all()
    )
    assert len(stored) == 1

    after = client.get(
        f"/applications/{subject_id}/investigate?refresh=true", headers=auth_headers
    ).json()
    after_text = _memory_step(after).lower()

    # The log changed, and it changed because of the row we just created.
    assert after_text != before_text, after_text
    assert "no investigator verdicts have been recorded yet" not in after_text
    assert "1 confirmed fraud" in after_text, after_text
    assert "similar past case" in after_text, after_text


def test_memory_excludes_the_cases_own_prior_verdict(client, auth_headers, memory_pair, db):
    """A case must not recall its own adjudication as independent evidence."""
    app_id = memory_pair["precedent"]

    # Guarantee this application has a memory row (from the tests above, or now).
    own = (
        db.execute(select(CaseMemory).where(CaseMemory.application_id == uuid.UUID(app_id)))
        .scalars()
        .first()
    )
    if own is None:
        client.post(
            f"/applications/{app_id}/feedback",
            json={"verdict": "CONFIRMED_FRAUD", "notes": "self-exclusion check"},
            headers=auth_headers,
        )
        db.commit()

    result = investigation_agent.run_investigation(db, app_id)
    memory_context = result.get("memory_context") or {}
    recalled = {m["application_id"] for m in memory_context.get("matches", [])}
    assert app_id not in recalled, "case recalled its own verdict as precedent"


# ---------------------------------------------------------------------------
# 3. The quick-exit path is UNCHANGED by this addition
# ---------------------------------------------------------------------------


def test_quick_exit_still_exactly_one_step_and_no_llm(
    client, auth_headers, TestSession, monkeypatch
):
    """Regression guard for the existing Test A contract.

    Adding institutional memory must not make an easy case do more work.
    """
    from app.ml.scoring_service import get_scoring_service
    from app.routers.applications import persist_scored_application
    from app.services.llm_explainer import template_explanation

    service = get_scoring_service()
    session = TestSession()
    try:
        payload = {
            "applicant_age": 44,
            "annual_income": 88_000.0,
            "employment_type": "salaried",
            "employer_name": "Corven Systems",
            "requested_amount": 7_500.0,
            "loan_purpose": "home_improvement",
            "loan_purpose_text": "Replacing a failing boiler before winter.",
            "session_duration_seconds": 265,
            "mouse_movement_events": 210,
            "form_paste_count": 0,
            "id_document_filename": None,
            "applications_from_device_last_24h": 1,
            "applications_from_ip_last_24h": 1,
            "income_employer_consistency_score": 0.93,
            "identity_consistency_score": 0.95,
            "device_id": f"mem_quickexit_dev_{uuid.uuid4().hex[:8]}",
            "ip_hash": f"mem_quickexit_ip_{uuid.uuid4().hex[:8]}",
        }
        result = service.score(payload)
        assert result.decision_band == "AUTO_APPROVE" and result.ring_size == 0
        app, _ = persist_scored_application(
            session, payload, result, template_explanation(result), "template",
            requested_by="test", id_document_filename=None,
        )
        session.commit()
        clean_id = str(app.id)
    finally:
        session.close()

    calls = []
    monkeypatch.setattr(
        investigation_agent, "_ask_groq", lambda *a, **k: calls.append(a) or None
    )

    body = client.get(
        f"/applications/{clean_id}/investigate?refresh=true", headers=auth_headers
    ).json()

    assert _steps(body) == ["quick_exit"], _steps(body)
    assert "check_investigator_memory" not in _steps(body)
    assert calls == [], f"quick-exit path called the LLM {len(calls)} time(s)"
    assert body["synthesis_source"] == "quick_exit"


# ---------------------------------------------------------------------------
# 4. PRIVACY: signatures carry patterns, never identifiers
# ---------------------------------------------------------------------------


def test_signatures_contain_no_raw_identifiers(client, auth_headers, memory_pair, db):
    """Same pattern as the network-signal privacy audit, against stored rows."""
    from app.models import Application

    memories = db.execute(select(CaseMemory)).scalars().all()
    assert memories, "no case_memory rows to audit"

    applications = db.execute(select(Application)).scalars().all()
    identifiers: set[str] = set()
    for application in applications:
        for value in (application.device_id, application.ip_hash, application.employer_name):
            if value:
                identifiers.add(str(value))
        payload = application.raw_payload or {}
        for key in ("full_name", "applicant_name", "pan_number", "email", "mobile", "address"):
            value = payload.get(key)
            if value:
                identifiers.add(str(value))

    for memory in memories:
        signature = memory.signature_text
        for identifier in identifiers:
            assert identifier not in signature, (
                f"identifier {identifier!r} leaked into a case_memory signature: {signature}"
            )


def test_memory_stats_distinguishes_live_from_backfilled(db):
    """The honesty column is queryable — live and simulated never conflated."""
    stats = case_memory.memory_stats(db)
    assert set(stats["by_source"]) <= {
        case_memory.SOURCE_LIVE,
        case_memory.SOURCE_BACKFILL,
    }
    assert stats["total"] == sum(stats["by_source"].values())


def test_conflicting_memory_caps_confidence(db, memory_pair):
    """Memory conflict is a real, traceable adjustment, not a cosmetic mention."""
    # Two opposing verdicts on the same pattern => split precedent.
    state = {
        "decision_band": "AUTO_FLAG",
        "risk_score": 0.94,
        "memory_context": {
            "matches": [
                {"verdict": "CONFIRMED_FRAUD", "similarity": 0.9, "application_id": "a"},
                {"verdict": "CONFIRMED_LEGITIMATE", "similarity": 0.8, "application_id": "b"},
            ],
            "counts": {"CONFIRMED_FRAUD": 1, "CONFIRMED_LEGITIMATE": 1},
        },
        "ring_feedback_history": None,
    }
    alignment = investigation_agent._memory_alignment(state)
    assert alignment["stance"] == "conflicts"
    assert alignment["confidence_effect"] == "capped_at_medium"
    assert "conflicting outcomes" in alignment["note"]
    assert investigation_agent._apply_memory_to_confidence("HIGH", alignment) == "MEDIUM"

    # Agreement across several verdicts supports the call instead.
    agreeing = {
        **state,
        "memory_context": {
            "matches": [
                {"verdict": "CONFIRMED_FRAUD", "similarity": 0.9, "application_id": "a"},
                {"verdict": "CONFIRMED_FRAUD", "similarity": 0.8, "application_id": "b"},
            ],
            "counts": {"CONFIRMED_FRAUD": 2},
        },
    }
    supportive = investigation_agent._memory_alignment(agreeing)
    assert supportive["stance"] == "supports"
    assert supportive["note"] is None
    assert investigation_agent._apply_memory_to_confidence("MEDIUM", supportive) == "HIGH"


def test_conflict_does_not_override_direct_ring_evidence(db):
    """Documented exception: a confirmed verdict in this case's OWN ring wins.

    Pattern precedent from unrelated cases is weaker evidence than a confirmed
    fraud verdict on an application sharing this one's device or IP, so the
    confidence cap stands down — but the conflict is still reported.
    """
    state = {
        "decision_band": "AUTO_FLAG",
        "risk_score": 0.97,
        "memory_context": {
            "matches": [
                {"verdict": "CONFIRMED_FRAUD", "similarity": 0.9, "application_id": "a"},
                {"verdict": "CONFIRMED_LEGITIMATE", "similarity": 0.85, "application_id": "b"},
            ],
            "counts": {"CONFIRMED_FRAUD": 1, "CONFIRMED_LEGITIMATE": 1},
        },
        "ring_feedback_history": {"confirmed_fraud": 2},
    }
    alignment = investigation_agent._memory_alignment(state)
    assert alignment["stance"] == "conflicts"
    assert alignment["confidence_effect"] == "none_direct_ring_evidence"
    assert alignment["note"], "the conflict must still be surfaced to the reviewer"
    assert investigation_agent._apply_memory_to_confidence("HIGH", alignment) == "HIGH"
