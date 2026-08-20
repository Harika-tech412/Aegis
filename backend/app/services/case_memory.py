"""Institutional memory — what this institution's investigators have decided before.

Every confirmed verdict leaves a trace: the case's risk SIGNATURE paired with
the human's conclusion. Those traces accumulate into a corpus that grows with
use, and the investigation agent recalls the closest ones when a new case
arrives. Unlike the static narrative corpus behind similar-cases RAG, this
memory is written by the people using the system.

Two deliberate constraints:

* PRIVACY. The signature reuses similar_cases.build_query_text() verbatim, so
  it contains only risk-pattern descriptors — SHAP explanations, declared
  income/employment/loan context, session behaviour, device velocity counts.
  It carries NO applicant name, NO raw device_id, NO raw ip_hash, and no other
  direct identifier. Same discipline as network_fraud_signals: we remember
  patterns, never people.

* ONE MODEL. Embedding goes through similar_cases.get_embedding_model(), the
  process-wide all-MiniLM-L6-v2 singleton that already serves similar-cases
  retrieval. A second instance would double the memory cost for nothing.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, CaseMemory, Decision, InvestigatorFeedback
from app.services.similar_cases import build_query_text, get_embedding_model

logger = logging.getLogger("aegis.memory")

# Cosine similarity floor for a recalled verdict to count as evidence.
#
# 0.50 on all-MiniLM-L6-v2 over this signature vocabulary: signatures share a
# lot of boilerplate phrasing ("Applicant declared ... income as ..."), so
# unrelated cases already sit around 0.4-0.6, and everything above 0.5 shares
# at least the band and one risk driver. Set higher and the memory almost
# never speaks; set lower and it speaks about cases that merely share a
# sentence template. Recorded here so the number is arguable, not magic.
SIMILARITY_FLOOR = 0.50

SOURCE_LIVE = "live_feedback"
SOURCE_BACKFILL = "backfilled_simulation"


def build_signature_text(application: Application, decision: Decision | None) -> str:
    """The case's risk signature, in plain English.

    Deliberately delegates to the similar-cases query builder rather than
    composing its own text: the two must describe a case identically, or a
    signature embedded today would not match one embedded by a later version.
    That shared builder is also what guarantees the privacy property — it never
    reads applicant name, device_id, or ip_hash.
    """
    return build_query_text(application, decision)


def embed_signature(signature_text: str) -> list[float]:
    """Embed with the shared singleton (never a second model instance)."""
    return get_embedding_model().encode([signature_text])[0].tolist()


def remember_case(
    db: Session,
    application: Application,
    decision: Decision,
    verdict: str,
    *,
    feedback: InvestigatorFeedback | None = None,
    source: str = SOURCE_LIVE,
) -> CaseMemory:
    """Record one adjudicated case in institutional memory.

    Caller commits. Raises on failure so the caller can decide whether a memory
    write is allowed to fail the surrounding operation (for investigator
    feedback, it is not — see the feedback endpoint).
    """
    signature = build_signature_text(application, decision)
    band = (
        decision.decision_band.value
        if hasattr(decision.decision_band, "value")
        else str(decision.decision_band)
    )
    memory = CaseMemory(
        application_id=application.id,
        feedback_id=feedback.id if feedback is not None else None,
        decision_band=band,
        calibrated_risk_score=float(decision.calibrated_risk_score),
        signature_text=signature,
        verdict=verdict,
        embedding=embed_signature(signature),
        source=source,
    )
    db.add(memory)
    db.flush()
    return memory


def recall_similar_verdicts(
    db: Session,
    application: Application,
    decision: Decision | None,
    *,
    limit: int = 3,
    exclude_application_id: uuid_lib.UUID | None = None,
) -> dict:
    """Top-N past human verdicts on cases whose risk signature resembles this one.

    `exclude_application_id` keeps a case from recalling its OWN prior
    adjudication and presenting it as independent corroboration — that would be
    the system agreeing with itself and calling it evidence.
    """
    total = int(db.scalar(select(func.count()).select_from(CaseMemory)) or 0)
    if total == 0:
        return {
            "memory_size": 0,
            "matches": [],
            "considered": 0,
            "below_floor": 0,
            "counts": {},
            "similarity_floor": SIMILARITY_FLOOR,
        }

    signature = build_signature_text(application, decision)
    embedding = embed_signature(signature)
    distance = CaseMemory.embedding.cosine_distance(embedding)

    query = db.query(CaseMemory, distance.label("distance"))
    if exclude_application_id is not None:
        query = query.filter(CaseMemory.application_id != exclude_application_id)
    # Over-fetch: rows below the floor are dropped after scoring, and we still
    # want to report how many were considered.
    rows = query.order_by(distance).limit(limit * 3).all()

    scored = [
        {
            "memory_id": str(row.id),
            "application_id": str(row.application_id),
            "verdict": row.verdict.value if hasattr(row.verdict, "value") else str(row.verdict),
            "decision_band": row.decision_band,
            "risk_score": float(row.calibrated_risk_score),
            "source": row.source,
            "similarity": round(1.0 - float(dist), 4),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row, dist in rows
    ]
    matches = [m for m in scored if m["similarity"] >= SIMILARITY_FLOOR][:limit]

    counts: dict[str, int] = {}
    for match in matches:
        counts[match["verdict"]] = counts.get(match["verdict"], 0) + 1

    return {
        "memory_size": total,
        "matches": matches,
        "considered": len(scored),
        "below_floor": len(scored) - len([m for m in scored if m["similarity"] >= SIMILARITY_FLOOR]),
        "counts": counts,
        "similarity_floor": SIMILARITY_FLOOR,
        "best_similarity": scored[0]["similarity"] if scored else None,
    }


def memory_stats(db: Session) -> dict:
    """Row counts by source — live investigator verdicts vs backfilled history."""
    rows = db.execute(
        select(CaseMemory.source, func.count(CaseMemory.id)).group_by(CaseMemory.source)
    ).all()
    by_source = {source: int(count) for source, count in rows}
    return {"total": sum(by_source.values()), "by_source": by_source}
