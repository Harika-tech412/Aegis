"""Similar-cases retrieval over pgvector cosine distance."""

import pytest

from app.models import CaseNarrative
from app.services.similar_cases import _get_model
from tests.test_applications_api import VALID_PAYLOAD

NARRATIVES = [
    ("AEG-TEST-0001", "device_recycling",
     "Linked six applications within a 30-hour window, all from a single device fingerprint "
     "and IP address, with distinct declared identities and short sessions. Confirmed fraud "
     "ring; all applications declined and the device blocklisted."),
    ("AEG-TEST-0002", "session_anomaly",
     "Session lasted 22 seconds with zero mouse movement and nine pasted fields. Keystroke "
     "cadence showed sub-human uniformity. Confirmed scripted submission; declined."),
    ("AEG-TEST-0003", "income_mismatch",
     "Applicant declared $180,000 income against an employer band midpoint of $45,000. "
     "Employer could not confirm the stated role. Confirmed income misrepresentation; declined."),
    ("AEG-TEST-0004", "false_alarm",
     "Three family members applied from one household computer within two days. Distinct "
     "verified identities and employers. Cleared as legitimate after verification."),
]


@pytest.fixture(scope="module")
def seeded_narratives(TestSession):
    session = TestSession()
    try:
        if session.query(CaseNarrative).count() == 0:
            model = _get_model()
            embeddings = model.encode([text for _, _, text in NARRATIVES])
            for (case_id, fraud_type, text), emb in zip(NARRATIVES, embeddings):
                session.add(
                    CaseNarrative(
                        case_id=case_id,
                        fraud_type=fraud_type,
                        narrative_text=text,
                        generated_by="test",
                        embedding=emb.tolist(),
                    )
                )
            session.commit()
    finally:
        session.close()


def test_similar_cases_returns_ranked_matches(client, auth_headers, seeded_narratives):
    # Score a bot-like application: near-zero mouse, heavy pasting, short session.
    scored = client.post(
        "/score",
        json={
            **VALID_PAYLOAD,
            "device_id": "similar_test_device",
            "ip_hash": "similar_test_ip",
            "session_duration_seconds": 20,
            "mouse_movement_events": 1,
            "form_paste_count": 10,
            "identity_consistency_score": 0.3,
        },
        headers=auth_headers,
    ).json()

    response = client.get(
        f"/applications/{scored['application_id']}/similar-cases", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["matches"]) == 3
    scores = [m["similarity_score"] for m in body["matches"]]
    assert scores == sorted(scores, reverse=True)  # ordered by similarity
    for match in body["matches"]:
        assert match["case_id"] and match["fraud_type"] and match["narrative_text"]

    assert body["summary"].strip()
    # The bot-like query should surface the session-anomaly narrative first.
    assert body["matches"][0]["fraud_type"] == "session_anomaly"


def test_similar_cases_requires_auth(client, seeded_narratives):
    response = client.get(
        "/applications/00000000-0000-0000-0000-000000000000/similar-cases"
    )
    assert response.status_code == 401
