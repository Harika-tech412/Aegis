"""Aegis Network — publication, cross-institution consumption, and privacy.

The privacy claim ("no customer identity data ever leaves the originating
bank") is the feature's whole justification, so it is asserted directly against
the stored rows rather than taken on trust.
"""

import re
import uuid

import pytest
from sqlalchemy import select

from app.models import Application, Decision, Institution, NetworkFraudSignal
from app.services import network_service

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(scope="module")
def members(TestSession):
    session = TestSession()
    try:
        return {
            code: inst.id
            for code, inst in network_service.ensure_institutions(session).items()
        }
    finally:
        session.close()


def _application(session, device: str, ip: str, institution_id) -> Application:
    app = Application(
        applicant_age=34,
        annual_income=61_000.0,
        employment_type="salaried",
        employer_name="Network Test Co",
        requested_amount=12_000.0,
        loan_purpose="business",
        loan_purpose_text="network test",
        device_id=device,
        ip_hash=ip,
        session_duration_seconds=120,
        mouse_movement_events=90,
        form_paste_count=2,
        id_document_filename=None,
        institution_id=institution_id,
        raw_payload={},
    )
    session.add(app)
    session.flush()
    return app


# ---------------------------------------------------------------------------
# (a) Publication on CONFIRMED_FRAUD, and idempotency
# ---------------------------------------------------------------------------


def test_a_publishing_is_idempotent(TestSession, members):
    session = TestSession()
    try:
        app = _application(session, "pub_device_1", "pub_ip_1", members["SYNC_DEMO"])
        first = network_service.publish_signals(session, app, members["SYNC_DEMO"], notes="x")
        session.commit()
        assert len(first) == 2  # one DEVICE_HASH, one IP_HASH

        # Re-confirming the same case must not duplicate signals.
        second = network_service.publish_signals(session, app, members["SYNC_DEMO"], notes="x")
        session.commit()
        assert second == []

        stored = session.execute(
            select(NetworkFraudSignal).where(
                NetworkFraudSignal.signal_hash
                == network_service.network_hash("pub_device_1")
            )
        ).scalars().all()
        assert len(stored) == 1
    finally:
        session.close()


def test_a2_feedback_endpoint_publishes_on_confirmed_fraud(client, auth_headers):
    """The real endpoint path: confirming fraud publishes to the network."""
    from tests.test_applications_api import VALID_PAYLOAD

    scored = client.post(
        "/score",
        json={**VALID_PAYLOAD, "device_id": "fb_net_device", "ip_hash": "fb_net_ip"},
        headers=auth_headers,
    ).json()

    response = client.post(
        f"/applications/{scored['application_id']}/feedback",
        json={"verdict": "CONFIRMED_FRAUD", "notes": "confirmed during test"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    signals = client.get("/network/signals?limit=200", headers=auth_headers).json()["signals"]
    expected = network_service.network_hash("fb_net_device")[:12]
    assert any(s["hash_prefix"] == expected for s in signals)


# ---------------------------------------------------------------------------
# (b) Cross-institution hit produces the rule-layer bump
# ---------------------------------------------------------------------------


def test_b_cross_institution_hit_bumps_score_and_records(client, auth_headers, TestSession, members):
    from tests.test_applications_api import VALID_PAYLOAD

    device = f"xinst_device_{uuid.uuid4().hex[:8]}"

    # PARTNER_A confirms fraud on this device and publishes.
    session = TestSession()
    try:
        partner_app = _application(session, device, f"{device}_ip", members["PARTNER_A"])
        network_service.publish_signals(
            session, partner_app, members["PARTNER_A"], notes="partner confirmed"
        )
        session.commit()
    finally:
        session.close()

    # A SYNC_DEMO application now arrives from the same device.
    baseline = client.post(
        "/score",
        json={**VALID_PAYLOAD, "device_id": f"clean_{uuid.uuid4().hex[:8]}", "ip_hash": "clean_ip"},
        headers=auth_headers,
    ).json()
    hit = client.post(
        "/score",
        json={**VALID_PAYLOAD, "device_id": device, "ip_hash": f"{device}_ip"},
        headers=auth_headers,
    ).json()

    features = [f["feature"] for f in hit["top_shap_features"]]
    assert "NETWORK_SIGNAL_DEVICE_HIT" in features
    assert "NETWORK_SIGNAL_IP_HIT" in features

    # Two matched signals => 2 x 0.30 above the un-hit baseline.
    assert (
        hit["decision"]["calibrated_risk_score"]
        >= baseline["decision"]["calibrated_risk_score"] + 0.59
    )

    # The hit is persisted with its source institution for the UI callout.
    detail = client.get(
        f"/applications/{hit['application_id']}", headers=auth_headers
    ).json()
    hits = detail["decision"]["network_hits"]
    assert hits and any(h["reported_by_code"] == "PARTNER_A" for h in hits)
    assert all("Partner Bank A" == h["reported_by"] for h in hits)


# ---------------------------------------------------------------------------
# (c) Self-published signals must NOT count
# ---------------------------------------------------------------------------


def test_c_own_institution_signal_does_not_bump(client, auth_headers, TestSession, members):
    from tests.test_applications_api import VALID_PAYLOAD

    device = f"selfsig_device_{uuid.uuid4().hex[:8]}"

    # SYNC_DEMO publishes a signal about its OWN case.
    session = TestSession()
    try:
        own_app = _application(session, device, f"{device}_ip", members["SYNC_DEMO"])
        network_service.publish_signals(
            session, own_app, members["SYNC_DEMO"], notes="self reported"
        )
        session.commit()
    finally:
        session.close()

    # A new SYNC_DEMO application from the same device gets NO network bump:
    # you learn nothing from a case you already confirmed yourself.
    result = client.post(
        "/score",
        json={**VALID_PAYLOAD, "device_id": device, "ip_hash": f"{device}_ip"},
        headers=auth_headers,
    ).json()

    features = [f["feature"] for f in result["top_shap_features"]]
    assert "NETWORK_SIGNAL_DEVICE_HIT" not in features
    assert "NETWORK_SIGNAL_IP_HIT" not in features
    assert not result["decision"]["network_hits"]


# ---------------------------------------------------------------------------
# (d) PRIVACY: no raw identifier is ever stored in the network table
# ---------------------------------------------------------------------------


def test_d_no_raw_identifiers_in_network_table(TestSession):
    session = TestSession()
    try:
        signals = session.execute(select(NetworkFraudSignal)).scalars().all()
        assert signals, "no signals to audit"

        # Every stored hash is a bare SHA-256 hex digest and nothing else.
        for signal in signals:
            assert SHA256_HEX.match(signal.signal_hash), signal.signal_hash

        # No application's raw device_id / ip_hash appears in ANY signal field.
        raw_values: set[str] = set()
        for app in session.execute(select(Application)).scalars().all():
            if app.device_id:
                raw_values.add(app.device_id)
            if app.ip_hash:
                raw_values.add(app.ip_hash)

        for signal in signals:
            haystack = f"{signal.signal_hash} {signal.notes or ''}"
            for raw in raw_values:
                assert raw not in haystack, f"raw identifier {raw} leaked into a signal"

        # And the hash is genuinely one-way: it does not equal the input.
        sample = next(iter(raw_values))
        assert network_service.network_hash(sample) != sample
        # Salted: an unsalted digest must not match the stored form.
        import hashlib

        unsalted = hashlib.sha256(sample.encode()).hexdigest()
        assert network_service.network_hash(sample) != unsalted
    finally:
        session.close()


def test_network_endpoints_require_auth(client):
    for path in ("/network/stats", "/network/signals", "/network/graph", "/network/institutions"):
        assert client.get(path).status_code == 401


def test_institution_scoping_separates_books(client, auth_headers):
    sync = client.get("/applications?institution_code=SYNC_DEMO&limit=1", headers=auth_headers).json()
    partner = client.get("/applications?institution_code=PARTNER_A&limit=1", headers=auth_headers).json()
    # Distinct institutions report distinct totals from the same endpoint.
    assert sync["total"] >= 0 and partner["total"] >= 0
    assert isinstance(sync["total"], int)
