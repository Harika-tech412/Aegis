"""Backfill institutional memory so the agent has precedent on day one.

    docker compose exec backend python /scripts/backfill_case_memory.py

MUST run inside the backend container. It embeds with the same
sentence-transformers singleton the API uses, and reads the same DATABASE_URL
from the container's environment — running it on the host risks pointing at a
different database entirely.

WHY A SCRIPT AND NOT A STARTUP HOOK
  Embedding a few hundred signatures takes seconds and loads torch. Doing that
  inside the FastAPI lifespan would slow every boot (including test collection
  and container restarts) for work that only ever needs to happen once. The
  startup path instead LOGS the memory count, so an empty memory is visible
  immediately without doing heavy work there — same visibility discipline as
  the Aegis Network salt fingerprint.

TWO SOURCES, KEPT DISTINGUISHABLE
  (a) live_feedback         — investigator_feedback rows already in the database.
                              Real verdicts from real use of this system.
  (b) backfilled_simulation — ml/artifacts/simulated_feedback.json, the 200
                              verdicts generated for the retraining experiment.
                              Real verdict labels against real seeded
                              applications, but SIMULATED adjudication, not a
                              human sitting at the console.

  Both are useful precedent; conflating them would be dishonest, so `source` is
  a column and every report of memory size breaks down by it.

Idempotent: a case_memory row already present for an (application_id, source)
pair is left alone, so re-running adds only what is new.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]
_BACKEND = _ROOT / "backend" if (_ROOT / "backend").exists() else Path("/app")
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    Application,
    CaseMemory,
    Decision,
    InvestigatorFeedback,
)
from app.services import case_memory  # noqa: E402

SIM_FEEDBACK = Path("/ml/artifacts/simulated_feedback.json")
if not SIM_FEEDBACK.exists():
    SIM_FEEDBACK = _ROOT / "ml" / "artifacts" / "simulated_feedback.json"


def _latest_decision(db, application_id):
    return (
        db.execute(
            select(Decision)
            .where(Decision.application_id == application_id)
            .order_by(Decision.created_at.desc())
        )
        .scalars()
        .first()
    )


def backfill_live_feedback(db) -> int:
    """Every existing investigator_feedback row becomes a memory."""
    rows = db.execute(
        select(InvestigatorFeedback, Decision, Application)
        .join(Decision, InvestigatorFeedback.decision_id == Decision.id)
        .join(Application, Decision.application_id == Application.id)
    ).all()

    existing = {
        (app_id, source)
        for app_id, source in db.execute(
            select(CaseMemory.application_id, CaseMemory.source)
        ).all()
    }

    written = 0
    for feedback, decision, application in rows:
        if (application.id, case_memory.SOURCE_LIVE) in existing:
            continue
        verdict = (
            feedback.verdict.value
            if hasattr(feedback.verdict, "value")
            else str(feedback.verdict)
        )
        case_memory.remember_case(
            db,
            application,
            decision,
            verdict,
            feedback=feedback,
            source=case_memory.SOURCE_LIVE,
        )
        existing.add((application.id, case_memory.SOURCE_LIVE))
        written += 1
    db.commit()
    return written


def backfill_simulated(db) -> tuple[int, int]:
    """The retraining experiment's 200 verdicts, tagged as simulated."""
    if not SIM_FEEDBACK.exists():
        print(f"no simulated feedback file at {SIM_FEEDBACK} - skipping")
        return 0, 0

    events = json.loads(SIM_FEEDBACK.read_text(encoding="utf-8"))
    existing = {
        (app_id, source)
        for app_id, source in db.execute(
            select(CaseMemory.application_id, CaseMemory.source)
        ).all()
    }

    written = 0
    missing = 0
    for event in events:
        try:
            app_uuid = __import__("uuid").UUID(str(event["application_id"]))
        except (ValueError, KeyError, TypeError):
            missing += 1
            continue
        if (app_uuid, case_memory.SOURCE_BACKFILL) in existing:
            continue

        application = db.get(Application, app_uuid)
        if application is None:
            # The simulation drew on the training CSV; only rows that were also
            # seeded into this database can become memories.
            missing += 1
            continue
        decision = _latest_decision(db, app_uuid)
        if decision is None:
            missing += 1
            continue

        case_memory.remember_case(
            db,
            application,
            decision,
            event["verdict"],
            feedback=None,
            source=case_memory.SOURCE_BACKFILL,
        )
        existing.add((app_uuid, case_memory.SOURCE_BACKFILL))
        written += 1
        if written % 50 == 0:
            db.commit()
            print(f"  ... {written} simulated verdicts embedded")
    db.commit()
    return written, missing


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        before = case_memory.memory_stats(db)
        print(f"case_memory before: {before['total']} rows {before['by_source']}")

        live = backfill_live_feedback(db)
        print(f"live investigator feedback backfilled: {live}")

        simulated, skipped = backfill_simulated(db)
        print(
            f"simulated verdicts backfilled: {simulated} "
            f"(skipped {skipped} - application or decision not in this database)"
        )

        after = case_memory.memory_stats(db)
        print(f"case_memory after: {after['total']} rows {after['by_source']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
