"""Seed Partner Bank A as a genuine second institution on the Aegis Network.

    docker compose exec backend python /scripts/seed_partner_bank.py

What this creates:
  1. ~200 applications owned by PARTNER_A, each scored through the real
     pipeline (fresh application ids, its own decisions) — Partner Bank A is a
     working institution, not a mock.
  2. ~15 confirmed-fraud cases for PARTNER_A, published to the network as
     salted hashes.
  3. ~10 network signals from SYNC_DEMO's existing confirmed-fraud seed data,
     so the network is not empty at demo launch.

DELIBERATE CROSS-INSTITUTION OVERLAP — the point of the whole feature:
  A handful of PARTNER_A's fraud cases are seeded to REUSE device_id / ip_hash
  values that already appear on SYNC_DEMO fraud applications. This is not
  coincidence and is not cheating: it is exactly the real-world scenario the
  Aegis Network exists to catch — one fraud ring hitting several banks with the
  same infrastructure. Because PARTNER_A confirms those cases and publishes
  their hashes, a later SYNC_DEMO application from the same device matches a
  partner signal and is flagged, with no identity data crossing institutions.

Idempotent: re-running skips work already done.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]
_BACKEND = _ROOT / "backend" if (_ROOT / "backend").exists() else Path("/app")
sys.path.insert(0, str(_BACKEND))

from app.database import SessionLocal, init_db  # noqa: E402
from app.ml.scoring_service import ML_DIR, get_scoring_service  # noqa: E402
from app.models import (  # noqa: E402
    Application,
    Decision,
    InvestigatorFeedback,
    NetworkFraudSignal,
)
from app.routers.applications import persist_scored_application  # noqa: E402
from app.services.llm_explainer import template_explanation  # noqa: E402
from app.services.network_service import (  # noqa: E402
    PARTNER_A,
    SYNC_DEMO,
    ensure_institutions,
    publish_signals,
)

DATA_DIR = ML_DIR.parent / "data" if (ML_DIR.parent / "data").exists() else Path("/data")

PARTNER_ROWS = 200
PARTNER_FRAUD_ROWS = 15
OVERLAP_CASES = 4  # PARTNER_A fraud cases reusing a SYNC_DEMO fraud device/IP
SYNC_SIGNALS_TO_SEED = 10
SAMPLE_SEED = 4242


def _payload(row: dict) -> dict:
    return {
        "applicant_age": int(row["applicant_age"]),
        "annual_income": float(row["annual_income"]),
        "employment_type": row["employment_type"],
        "employer_name": row["employer_name"],
        "requested_amount": float(row["requested_amount"]),
        "loan_purpose": row["loan_purpose"],
        "loan_purpose_text": row["loan_purpose_text"],
        "device_id": row["device_id"],
        "ip_hash": row["ip_hash"],
        "session_duration_seconds": int(row["session_duration_seconds"]),
        "mouse_movement_events": int(row["mouse_movement_events"]),
        "form_paste_count": int(row["form_paste_count"]),
        "id_document_filename": None,
        "applications_from_device_last_24h": int(row["applications_from_device_last_24h"]),
        "applications_from_ip_last_24h": int(row["applications_from_ip_last_24h"]),
        "income_employer_consistency_score": float(row["income_employer_consistency_score"]),
        "identity_consistency_score": float(row["identity_consistency_score"]),
    }


def main() -> None:
    init_db()
    db = SessionLocal()
    service = get_scoring_service()
    try:
        members = ensure_institutions(db)
        sync = members[SYNC_DEMO]
        partner = members[PARTNER_A]

        already = db.query(Application).filter(Application.institution_id == partner.id).count()
        if already:
            print(f"PARTNER_A already has {already} applications - skipping application seed")
        else:
            df = pd.read_csv(DATA_DIR / "applications_train.csv")

            # Devices already used by SYNC_DEMO fraud applications in THIS database.
            # These are the values the overlap cases will deliberately reuse.
            sync_fraud_devices = [
                (a.device_id, a.ip_hash)
                for a in db.query(Application)
                .join(Decision, Decision.application_id == Application.id)
                .filter(
                    Application.institution_id == sync.id,
                    Decision.decision_band == "AUTO_FLAG",
                )
                .limit(OVERLAP_CASES)
                .all()
            ]
            print(f"found {len(sync_fraud_devices)} SYNC_DEMO flagged devices to overlap against")

            legit = df[~df["is_fraud"]].sample(
                PARTNER_ROWS - PARTNER_FRAUD_ROWS, random_state=SAMPLE_SEED
            )
            fraud = df[df["is_fraud"]].sample(PARTNER_FRAUD_ROWS, random_state=SAMPLE_SEED)
            sample = pd.concat([legit, fraud]).sample(frac=1.0, random_state=SAMPLE_SEED)

            fraud_ids = set(fraud["application_id"])
            overlap_assigned = 0
            partner_fraud_apps: list[Application] = []

            for row in sample.to_dict("records"):
                payload = _payload(row)
                is_fraud_row = row["application_id"] in fraud_ids

                # ---- The deliberate overlap ----
                if is_fraud_row and overlap_assigned < len(sync_fraud_devices):
                    device, ip = sync_fraud_devices[overlap_assigned]
                    payload["device_id"] = device
                    payload["ip_hash"] = ip
                    overlap_assigned += 1
                else:
                    # Otherwise namespace the identifiers so PARTNER_A's book is
                    # genuinely its own and does not accidentally collide.
                    payload["device_id"] = f"pa_{row['device_id']}"
                    payload["ip_hash"] = f"pa_{row['ip_hash']}"

                result = service.score(payload, compute_counterfactual=False)
                app, decision = persist_scored_application(
                    db,
                    payload,
                    result,
                    template_explanation(result),
                    "template",
                    requested_by="partner_seed",
                    id_document_filename=None,
                    institution_id=partner.id,
                )
                app.created_at = datetime.now(timezone.utc) - timedelta(
                    hours=int(row["applicant_age"]) % 48
                )
                if is_fraud_row:
                    partner_fraud_apps.append(app)
            db.commit()
            print(
                f"seeded {len(sample)} PARTNER_A applications "
                f"({len(partner_fraud_apps)} fraud, {overlap_assigned} overlapping a "
                "SYNC_DEMO flagged device)"
            )

            # Record PARTNER_A's investigator verdicts. Publication happens
            # below, outside this branch, so it re-runs independently.
            for app in partner_fraud_apps:
                decision = (
                    db.query(Decision)
                    .filter(Decision.application_id == app.id)
                    .order_by(Decision.created_at.desc())
                    .first()
                )
                if decision is None:
                    continue
                db.add(
                    InvestigatorFeedback(
                        decision_id=decision.id,
                        investigator_username="partner_investigator",
                        verdict="CONFIRMED_FRAUD",
                        notes="Confirmed fraud during Partner Bank A ring sweep.",
                    )
                )

            db.commit()

        # ---- PARTNER_A confirms its fraud and publishes to the network ------
        # Deliberately OUTSIDE the application-seed branch. Publication is
        # driven by PARTNER_A's confirmed-fraud rows, so re-running after a
        # salt rotation (which invalidates every prior hash) republishes rather
        # than silently leaving the network unmatchable.
        partner_confirmed = (
            db.query(Application)
            .join(Decision, Decision.application_id == Application.id)
            .join(InvestigatorFeedback, InvestigatorFeedback.decision_id == Decision.id)
            .filter(
                Application.institution_id == partner.id,
                InvestigatorFeedback.verdict == "CONFIRMED_FRAUD",
            )
            .all()
        )
        published = 0
        for app in partner_confirmed:
            published += len(
                publish_signals(
                    db,
                    app,
                    partner.id,
                    notes="device recycling ring - confirmed identity theft",
                    confirmed_at=datetime.now(timezone.utc) - timedelta(hours=18),
                )
            )
        db.commit()
        print(
            f"PARTNER_A published {published} network signals "
            f"from {len(partner_confirmed)} confirmed-fraud cases"
        )

        # ---- Seed SYNC_DEMO signals so the network is populated at launch ----
        sync_signals = (
            db.query(NetworkFraudSignal)
            .filter(NetworkFraudSignal.reported_by_institution_id == sync.id)
            .count()
        )
        if sync_signals:
            print(f"SYNC_DEMO already has {sync_signals} published signals - skipping")
        else:
            flagged = (
                db.query(Application)
                .join(Decision, Decision.application_id == Application.id)
                .filter(
                    Application.institution_id == sync.id,
                    Decision.decision_band == "AUTO_FLAG",
                )
                .limit(SYNC_SIGNALS_TO_SEED)
                .all()
            )
            count = 0
            for app in flagged:
                count += len(
                    publish_signals(
                        db,
                        app,
                        sync.id,
                        notes="confirmed fraud - published at network onboarding",
                        confirmed_at=datetime.now(timezone.utc) - timedelta(hours=30),
                    )
                )
            db.commit()
            print(f"SYNC_DEMO published {count} network signals from existing flagged cases")

        # ---- DEMO SCENARIO STAGING (documented, deliberate) -----------------
        # The fraud-bot "Fraud Ring Attack" preset and the /apply "Fraud ring
        # member" preset both draw their device/IP from /demo/ring-device, which
        # selects a high-fraud device out of ring_lookup.json. For the live demo
        # payoff to land, PARTNER_A must ALREADY have published that device's
        # hash — i.e. "Partner Bank A confirmed this device as fraud yesterday".
        #
        # This is staging, not fakery: the signal is a real row, published by a
        # real second institution, matched by the real hashing path at scoring
        # time. We are choosing WHICH device the partner reported, exactly as
        # the overlap cases above do.
        from app.routers.demo import _pick_ring_device

        ring = _pick_ring_device()
        staged = (
            db.query(NetworkFraudSignal)
            .filter(
                NetworkFraudSignal.reported_by_institution_id == partner.id,
                NetworkFraudSignal.signal_hash == __import__(
                    "app.services.network_service", fromlist=["network_hash"]
                ).network_hash(ring["device_id"]),
            )
            .count()
        )
        if staged:
            print("demo-scenario partner signal already staged - skipping")
        else:
            # Reuse a stand-in from a previous run if one exists: after a salt
            # rotation the signal guard above misses, and we must not accumulate
            # duplicate stub applications in PARTNER_A's book.
            stub = (
                db.query(Application)
                .filter(
                    Application.institution_id == partner.id,
                    Application.device_id == ring["device_id"],
                    Application.employer_name == "Partner Bank A - confirmed ring case",
                )
                .first()
            )
            if stub is None:
                stub = Application(
                    applicant_age=31,
                    annual_income=52_000.0,
                    employment_type="salaried",
                    employer_name="Partner Bank A - confirmed ring case",
                    requested_amount=18_000.0,
                    loan_purpose="business",
                    loan_purpose_text="Confirmed fraud ring case (Partner Bank A).",
                    device_id=ring["device_id"],
                    ip_hash=ring["ip_hash"],
                    session_duration_seconds=41,
                    mouse_movement_events=6,
                    form_paste_count=9,
                    id_document_filename=None,
                    institution_id=partner.id,
                    raw_payload={"note": "partner confirmed ring case, staged for demo"},
                )
                db.add(stub)
                db.flush()
            n = len(
                publish_signals(
                    db,
                    stub,
                    partner.id,
                    notes="device recycling ring - confirmed identity theft",
                    confirmed_at=datetime.now(timezone.utc) - timedelta(hours=22),
                )
            )
            db.commit()
            print(
                f"staged demo scenario: PARTNER_A published {n} signals for the "
                f"ring-preset device {ring['device_id'][:12]}..."
            )

        total = db.query(NetworkFraudSignal).count()
        print(f"network now carries {total} signals across {len(members)} institutions")
    finally:
        db.close()


if __name__ == "__main__":
    main()
