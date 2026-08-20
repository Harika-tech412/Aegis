"""Seed the Aegis database with historical applications, decisions, and narratives.

Prerequisite: the dockerized Postgres must be up (`docker compose up -d db`).
This script is designed to run INSIDE the backend container, where the `db`
hostname resolves and all ML dependencies are installed:

    docker compose exec backend python /app/scripts/seed_database.py

Idempotent-ish: if the applications table already has rows, seeding is skipped
(same for narratives and the investigator user), so re-running is safe.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import timezone
from pathlib import Path

import pandas as pd

# Resolve project layout both inside the container (/app, /ml, /data, /scripts)
# and locally (repo checkout).
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]
_BACKEND = _ROOT / "backend" if (_ROOT / "backend").exists() else Path("/app")
sys.path.insert(0, str(_BACKEND))

from app.database import SessionLocal, init_db  # noqa: E402
from app.ml.scoring_service import ML_DIR, get_scoring_service  # noqa: E402
from app.models import Application, CaseNarrative, Decision, Investigator  # noqa: E402
from app.services.auth import hash_password  # noqa: E402
from app.services.llm_explainer import template_explanation  # noqa: E402

DATA_DIR = ML_DIR.parent / "data" if (ML_DIR.parent / "data").exists() else Path("/data")

SEED_SAMPLE_SIZE = 1_200
SAMPLE_SEED = 7


def seed_applications(db) -> None:
    existing = db.query(Application).count()
    if existing > 0:
        print(f"applications table already has {existing} rows - skipping application seed")
        return

    df = pd.read_csv(DATA_DIR / "applications_train.csv")

    # Stratified sample: keep the full dataset's fraud rate in the demo data.
    frac = SEED_SAMPLE_SIZE / len(df)
    sample = (
        df.groupby("is_fraud", group_keys=False)
        .apply(lambda g: g.sample(frac=frac, random_state=SAMPLE_SEED))
        .sort_values("timestamp")
    )
    print(f"seeding {len(sample)} applications ({sample['is_fraud'].mean():.1%} fraud in sample)")

    service = get_scoring_service()
    t0 = time.time()
    n_bands = {"AUTO_APPROVE": 0, "HUMAN_REVIEW": 0, "AUTO_FLAG": 0}

    for i, row in enumerate(sample.to_dict("records"), 1):
        payload = {
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
            "id_document_filename": row["id_document_filename"]
            if isinstance(row["id_document_filename"], str) and row["id_document_filename"]
            else None,
            "applications_from_device_last_24h": int(row["applications_from_device_last_24h"]),
            "applications_from_ip_last_24h": int(row["applications_from_ip_last_24h"]),
            "income_employer_consistency_score": float(row["income_employer_consistency_score"]),
            "identity_consistency_score": float(row["identity_consistency_score"]),
        }

        # Counterfactuals are skipped for bulk seeding (they are a live-scoring
        # feature; computing ~600 binary searches would slow the seed 10x).
        result = service.score(
            {**payload, "application_id": row["application_id"]}, compute_counterfactual=False
        )

        application = Application(
            id=row["application_id"],
            created_at=pd.Timestamp(row["timestamp"]).to_pydatetime().replace(tzinfo=timezone.utc),
            **{k: v for k, v in payload.items() if k not in (
                "applications_from_device_last_24h",
                "applications_from_ip_last_24h",
                "income_employer_consistency_score",
                "identity_consistency_score",
            )},
            raw_payload=payload,
        )
        db.add(application)
        db.add(
            Decision(
                application_id=application.id,
                model_version=result.model_version,
                xgboost_probability=result.xgboost_probability,
                anomaly_score=result.anomaly_score,
                calibrated_risk_score=result.calibrated_risk_score,
                decision_band=result.decision_band,
                top_shap_features=result.top_shap_features,
                # Template explanations for bulk seed: 1,200 LLM calls would
                # blow the daily quota for zero demo value.
                explanation_text=template_explanation(result),
                counterfactual=None,
                ring_size=result.ring_size,
                ring_risk_score=result.ring_risk_score,
                latency_ms=result.latency_ms,
            )
        )
        n_bands[result.decision_band] += 1
        if i % 200 == 0:
            db.flush()
            print(f"  {i}/{len(sample)} scored ({time.time() - t0:.0f}s)")

    db.commit()
    print(
        f"seeded {len(sample)} applications in {time.time() - t0:.0f}s - bands: "
        f"AUTO_APPROVE {n_bands['AUTO_APPROVE']}, HUMAN_REVIEW {n_bands['HUMAN_REVIEW']}, "
        f"AUTO_FLAG {n_bands['AUTO_FLAG']}"
    )


def seed_narratives(db) -> None:
    existing = db.query(CaseNarrative).count()
    if existing > 0:
        print(f"case_narratives already has {existing} rows - skipping narrative seed")
        return

    path = DATA_DIR / "case_narratives.json"
    if not path.exists():
        print(f"WARNING: {path} not found - skipping narrative seed")
        return
    records = json.loads(path.read_text(encoding="utf-8"))

    print(f"embedding {len(records)} narratives with all-MiniLM-L6-v2 (first run downloads the model)...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode([r["narrative_text"] for r in records], show_progress_bar=False)

    for record, embedding in zip(records, embeddings):
        db.add(
            CaseNarrative(
                case_id=record["case_id"],
                fraud_type=record["fraud_type"],
                narrative_text=record["narrative_text"],
                generated_by=record["generated_by"],
                embedding=embedding.tolist(),
            )
        )
    db.commit()
    print(f"seeded {len(records)} case narratives with embeddings")


def seed_investigator(db) -> None:
    if db.query(Investigator).filter(Investigator.username == "investigator").first():
        print("investigator user already exists - skipping")
        return
    # DEMO CREDENTIAL ONLY. A real deployment would never seed a fixed
    # password from source code - this exists so judges can log in.
    db.add(Investigator(username="investigator", password_hash=hash_password("aegis_demo_2026")))
    db.commit()
    print('seeded investigator user "investigator"')


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_investigator(db)
        seed_applications(db)
        seed_narratives(db)
    finally:
        db.close()
    print("seed complete")


if __name__ == "__main__":
    main()
