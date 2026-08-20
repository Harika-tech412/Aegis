"""Semantic retrieval of similar past cases from the narrative corpus.

Query text is composed from the decision's SHAP explanations plus the
application's fraud-relevant fields — investigator-style prose, not a dump of
raw numbers — then embedded with the same all-MiniLM-L6-v2 model that embedded
the corpus, and matched via pgvector cosine distance.

The embedding model is loaded once per process on first use and reused for
every request (module-level singleton).
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session

from app.models import Application, CaseNarrative, Decision
from app.services.llm_explainer import summarize_similar_cases

logger = logging.getLogger("aegis.similar")

_model = None
_model_lock = threading.Lock()


def _get_model():
    """all-MiniLM-L6-v2, loaded once per process (lazily - torch import is heavy)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("loading sentence-transformers all-MiniLM-L6-v2 (one-time)")
                _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_embedding_model():
    """The shared all-MiniLM-L6-v2 instance.

    Public accessor so other services (institutional memory) embed with the
    SAME loaded model rather than paying for a second copy in the process.
    """
    return _get_model()


def build_query_text(application: Application, decision: Decision | None) -> str:
    """Investigator-style description of the case, for semantic matching."""
    parts: list[str] = []
    if decision is not None:
        # SHAP explanations are already plain-English signal descriptions -
        # exactly the vocabulary the narrative corpus is written in.
        risk_factors = [
            f["explanation"]
            for f in (decision.top_shap_features or [])
            if f.get("direction") == "increases_risk"
        ][:4]
        parts.extend(risk_factors)
        band = (
            decision.decision_band.value
            if hasattr(decision.decision_band, "value")
            else decision.decision_band
        )
        parts.append(f"Application was {band.replace('_', ' ').lower()} by the model.")
        if decision.ring_size > 0:
            parts.append(
                f"Linked to {decision.ring_size - 1} other applications through a shared "
                f"device fingerprint or IP address."
            )

    payload = application.raw_payload or {}
    parts.append(
        f"Applicant declared ${application.annual_income:,.0f} income as "
        f"{application.employment_type.replace('_', ' ')}, requesting "
        f"${application.requested_amount:,.0f} for {application.loan_purpose.replace('_', ' ')}."
    )
    parts.append(
        f"Session lasted {application.session_duration_seconds} seconds with "
        f"{application.mouse_movement_events} mouse events and "
        f"{application.form_paste_count} pasted fields."
    )
    if payload.get("applications_from_device_last_24h", 1) > 1:
        parts.append(
            f"{payload['applications_from_device_last_24h']} applications from the same "
            f"device in the last 24 hours."
        )
    return " ".join(parts)


def find_similar_cases(db: Session, application: Application, decision: Decision | None) -> dict:
    """Top-3 nearest narratives by cosine distance, plus an LLM/template summary."""
    query_text = build_query_text(application, decision)
    embedding = _get_model().encode([query_text])[0].tolist()

    distance = CaseNarrative.embedding.cosine_distance(embedding)
    rows = (
        db.query(CaseNarrative, distance.label("distance"))
        .order_by(distance)
        .limit(3)
        .all()
    )

    matches = [
        {
            "case_id": narrative.case_id,
            "fraud_type": narrative.fraud_type,
            "narrative_text": narrative.narrative_text,
            "similarity_score": round(1.0 - float(dist), 4),
        }
        for narrative, dist in rows
    ]

    if matches:
        summary, summary_source = summarize_similar_cases(
            [m["narrative_text"] for m in matches]
        )
    else:
        summary, summary_source = (
            "No past case narratives are available for comparison.",
            "template",
        )

    return {
        "query_text": query_text,
        "matches": matches,
        "summary": summary,
        "summary_source": summary_source,
    }
