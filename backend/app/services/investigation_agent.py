"""LangGraph investigation agent — dynamic reasoning over a flagged case.

This is a genuine agent, not a renamed pipeline: the graph BRANCHES on the
evidence it finds, so different cases take materially different paths.

    START
      │
    triage ──(AUTO_APPROVE and no ring signal)──▶ quick_exit ──▶ END
      │                                            (1 step, no LLM call)
      └──(anything else)──▶ check_ring
                              │
                              ├──(ring_size == 0)──▶ check_investigator_memory
                              │                              │
                              └──(ring_size > 0)───▶ check_ring_feedback
                                                             │
                              check_investigator_memory ◀────┘
                                                             │
                                                   check_similar_cases
                                                             │
                                                       check_drift
                                                             │
                                                        synthesize ──▶ END

Two branch points do real work:

* `triage` short-circuits obviously-clean cases. The agent does demonstrably
  LESS on an easy case — one log line, zero tool calls, zero LLM tokens.
* `check_ring` skips the feedback cross-reference entirely when there is no
  ring to cross-reference against.

`check_ring_feedback` is a capability no existing endpoint provides: it asks
whether investigators have ALREADY adjudicated other members of this
application's device/IP cluster, which is exactly the question a human
analyst would ask next and which no single-case view can answer.

`check_investigator_memory` asks a different question: forget this ring — has
this institution ever seen a case that LOOKS like this one, and what did the
human decide then? It runs on the deep branch only (never on quick_exit, which
must stay a single step with zero tool and LLM calls), and its answer can pull
the final confidence down: when past humans reached conflicting verdicts on
this pattern, that tension is surfaced rather than averaged away.

Tool nodes reuse the existing services (ring lookup, similar-cases RAG, drift
monitor, institutional memory) rather than reimplementing them — the agent
orchestrates, it does not duplicate.
"""

from __future__ import annotations

import json
import logging
import operator
import re
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.scoring_service import get_scoring_service
from app.models import Application, Decision, InvestigatorFeedback
from app.services import case_memory
from app.services.drift_service import compute_drift

# Imported as a module-level name on purpose: it carries the llm_explainer
# reliability contract (5s timeout, 1 retry, terminal-error disable) and stays
# patchable so tests can prove the quick-exit path makes no LLM call.
from app.services.llm_explainer import _ask_groq
from app.services.similar_cases import find_similar_cases

logger = logging.getLogger("aegis.agent")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class InvestigationState(TypedDict, total=False):
    application_id: str
    decision_band: str
    risk_score: float
    shap_top_features: list[dict]
    ring_context: dict | None
    ring_feedback_history: dict | None
    memory_context: dict | None
    memory_alignment: dict | None
    similar_cases: list[dict] | None
    drift_context: dict | None
    # Reducer: every node returns its own entries and LangGraph concatenates.
    investigation_log: Annotated[list[dict], operator.add]
    final_recommendation: str | None
    final_confidence: str | None
    reasoning_summary: str | None
    synthesis_source: str | None
    # Routing inputs, resolved once when the initial state is built.
    device_id: str
    ip_hash: str
    base_ring_size: int


def _step(node: str, description: str) -> dict:
    return {
        "step": node,
        "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def _triage(state: InvestigationState) -> dict:
    """Pure routing decision — deliberately writes no log entry.

    The branch it selects is what gets logged (quick_exit states its own
    reasoning), so an easy case produces exactly one step rather than a
    misleading trail of ceremony.
    """
    return {}


def _route_after_triage(state: InvestigationState) -> str:
    if state["decision_band"] == "AUTO_APPROVE" and state.get("base_ring_size", 0) == 0:
        return "quick_exit"
    return "check_ring"


def _quick_exit(state: InvestigationState) -> dict:
    """Terminal node for obviously-clean cases. No tools, no LLM call.

    Spending an LLM round-trip to say "this is fine" on a case the model
    already cleared with no network signal is waste; skipping it is a
    deliberate efficiency decision, not an omission.
    """
    return {
        "investigation_log": [
            _step(
                "quick_exit",
                f"Low-risk case (band AUTO_APPROVE, risk {state['risk_score']:.3f}) with no "
                "device or IP links to prior applications — deep investigation not warranted.",
            )
        ],
        "final_recommendation": "No further action needed",
        "final_confidence": "HIGH",
        "reasoning_summary": (
            "The model cleared this application and it shares no device fingerprint or IP "
            "address with any prior application, so no additional investigation was performed."
        ),
        "synthesis_source": "quick_exit",
    }


def _check_ring(state: InvestigationState, config) -> dict:
    service = get_scoring_service()
    ring = service.ring_context(
        state["device_id"], state["ip_hash"], own_id=state["application_id"]
    )
    size = ring["ring_size"]
    if size == 0:
        description = (
            "Checked the device/IP graph — this application shares no device fingerprint or "
            "IP address with any other application on file."
        )
    else:
        description = (
            f"Checked the device/IP graph — this application is linked to {size - 1} other "
            f"application(s) through a shared device or IP; {ring['ring_risk_score']:.0%} of "
            "those are already confirmed fraudulent."
        )
    return {"ring_context": ring, "investigation_log": [_step("check_ring", description)]}


def _route_after_ring(state: InvestigationState) -> str:
    ring = state.get("ring_context") or {}
    return (
        "check_ring_feedback"
        if ring.get("ring_size", 0) > 0
        else "check_investigator_memory"
    )


def _check_ring_feedback(state: InvestigationState, config) -> dict:
    """Have investigators already adjudicated other members of this ring?

    New capability: no existing endpoint joins ring membership to the
    investigator_feedback table. A confirmed verdict on a sibling application
    is the strongest available evidence about this one.
    """
    db: Session = config["configurable"]["db"]
    members = (state.get("ring_context") or {}).get("connected_applications", [])

    member_uuids = []
    for member in members:
        try:
            member_uuids.append(uuid_lib.UUID(str(member)))
        except (ValueError, AttributeError, TypeError):
            continue  # historical ids not present as DB rows

    rows = []
    if member_uuids:
        rows = db.execute(
            select(
                InvestigatorFeedback.verdict,
                InvestigatorFeedback.investigator_username,
                InvestigatorFeedback.notes,
                Decision.application_id,
            )
            .join(Decision, InvestigatorFeedback.decision_id == Decision.id)
            .where(Decision.application_id.in_(member_uuids))
        ).all()

    counts: dict[str, int] = {}
    verdicts = []
    for verdict, username, notes, app_id in rows:
        key = verdict.value if hasattr(verdict, "value") else str(verdict)
        counts[key] = counts.get(key, 0) + 1
        verdicts.append(
            {
                "application_id": str(app_id),
                "verdict": key,
                "investigator": username,
                "notes": notes,
            }
        )

    history = {
        "ring_members_checked": len(members),
        "feedback_found": len(verdicts),
        "counts": counts,
        "verdicts": verdicts,
        "confirmed_fraud": counts.get("CONFIRMED_FRAUD", 0),
        "confirmed_legitimate": counts.get("CONFIRMED_LEGITIMATE", 0),
    }

    if not verdicts:
        description = (
            f"Checked investigator feedback history across {len(members)} ring member(s) — "
            "no prior investigator feedback found on this ring."
        )
    else:
        breakdown = ", ".join(f"{n} x {verdict}" for verdict, n in sorted(counts.items()))
        description = (
            f"Checked investigator feedback history across {len(members)} ring member(s) — "
            f"found {len(verdicts)} prior verdict(s): {breakdown}."
        )

    return {
        "ring_feedback_history": history,
        "investigation_log": [_step("check_ring_feedback", description)],
    }


def _check_investigator_memory(state: InvestigationState, config) -> dict:
    """What did humans decide, last time this institution saw a case like this?

    This is episodic memory, not a static corpus: every investigator verdict
    submitted through the feedback endpoint lands in case_memory, so the pool
    this node queries is larger today than it was yesterday. It runs only on
    the deep branch — an obviously-clean case exits at triage and never asks.

    The current case's OWN memory rows are excluded. A case recalling its own
    prior adjudication and reporting it as corroboration would be the system
    agreeing with itself and calling that evidence.
    """
    db: Session = config["configurable"]["db"]
    app_uuid = uuid_lib.UUID(state["application_id"])
    application = db.get(Application, app_uuid)
    decision = (
        db.execute(
            select(Decision)
            .where(Decision.application_id == app_uuid)
            .order_by(Decision.created_at.desc())
        )
        .scalars()
        .first()
    )

    try:
        recall = case_memory.recall_similar_verdicts(
            db, application, decision, limit=3, exclude_application_id=app_uuid
        )
    except Exception as exc:  # noqa: BLE001 - retrieval must not kill the run
        logger.info("institutional memory unavailable: %s", exc)
        return {
            "memory_context": None,
            "investigation_log": [
                _step(
                    "check_investigator_memory",
                    "Checked institutional memory — the memory store was unavailable for "
                    "this run, so no past investigator verdicts were consulted.",
                )
            ],
        }

    floor_pct = f"{recall['similarity_floor']:.0%}"
    matches = recall["matches"]

    if recall["memory_size"] == 0:
        # Absence stated plainly, same discipline as the ring-feedback node.
        description = (
            "Checked institutional memory — no investigator verdicts have been recorded "
            "yet, so there is no institutional precedent to draw on for this case."
        )
    elif not matches:
        best = recall.get("best_similarity")
        best_text = f" Closest was {best:.0%}." if best is not None else ""
        description = (
            f"Checked institutional memory — {recall['memory_size']} past verdict(s) on "
            f"file, but none resemble this case's risk pattern above the {floor_pct} "
            f"similarity floor.{best_text} No precedent applied."
        )
    else:
        # "2 confirmed fraud (avg 87% pattern similarity), 1 confirmed legitimate (71%)"
        grouped: dict[str, list[float]] = {}
        for match in matches:
            grouped.setdefault(match["verdict"], []).append(match["similarity"])
        parts = []
        for verdict, sims in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            label = verdict.replace("CONFIRMED_", "confirmed ").replace("_", " ").lower()
            avg = sum(sims) / len(sims)
            qualifier = "avg " if len(sims) > 1 else ""
            parts.append(f"{len(sims)} {label} ({qualifier}{avg:.0%} pattern similarity)")
        description = (
            f"Checked institutional memory ({recall['memory_size']} recorded verdicts) — "
            f"{len(matches)} similar past case(s) found: {', '.join(parts)}."
        )

    return {
        "memory_context": recall,
        "investigation_log": [_step("check_investigator_memory", description)],
    }


def _check_similar_cases(state: InvestigationState, config) -> dict:
    db: Session = config["configurable"]["db"]
    application = db.get(Application, uuid_lib.UUID(state["application_id"]))
    decision = (
        db.execute(
            select(Decision)
            .where(Decision.application_id == application.id)
            .order_by(Decision.created_at.desc())
        )
        .scalars()
        .first()
    )
    try:
        result = find_similar_cases(db, application, decision)
        matches = result["matches"]
    except Exception as exc:  # noqa: BLE001 - retrieval must not kill the run
        logger.info("similar-case retrieval unavailable: %s", exc)
        return {
            "similar_cases": [],
            "investigation_log": [
                _step(
                    "check_similar_cases",
                    "Searched the historical case corpus — retrieval unavailable for this run.",
                )
            ],
        }

    if not matches:
        description = "Searched the historical case corpus — no comparable past cases found."
    else:
        top = matches[0]
        types = ", ".join(sorted({m["fraud_type"] for m in matches}))
        description = (
            f"Retrieved {len(matches)} semantically similar past case(s) — closest is "
            f"{top['case_id']} ({top['fraud_type'].replace('_', ' ')}, "
            f"{top['similarity_score']:.0%} match). Pattern types present: {types}."
        )
    return {
        "similar_cases": matches,
        "investigation_log": [_step("check_similar_cases", description)],
    }


def _check_drift(state: InvestigationState, config) -> dict:
    db: Session = config["configurable"]["db"]
    try:
        drift = compute_drift(db, window_hours=24)
    except Exception as exc:  # noqa: BLE001
        logger.info("drift check unavailable: %s", exc)
        return {
            "drift_context": None,
            "investigation_log": [
                _step("check_drift", "Checked model drift — monitor unavailable for this run.")
            ],
        }

    status = drift["overall_drift_status"]
    if status == "INSUFFICIENT_DATA":
        description = (
            f"Checked model drift — only {drift['recent_applications']} application(s) in the "
            "last 24h, too few for a reliable PSI verdict; scoring reliability neither "
            "confirmed nor questioned."
        )
    else:
        drifted = {f["feature"] for f in drift["features"] if f["status"] != "STABLE"}
        case_features = {f.get("feature") for f in state.get("shap_top_features") or []}
        overlap = sorted(drifted & case_features)
        if status == "STABLE":
            description = (
                "Checked model drift — input distributions are stable against training data, "
                "so this case's score carries normal reliability."
            )
        elif overlap:
            description = (
                f"Checked model drift — {status.replace('_', ' ').lower()} detected, and this "
                f"case's own drivers ({', '.join(o.replace('_', ' ') for o in overlap)}) sit in "
                "drifted regions; treat the score with extra caution."
            )
        else:
            description = (
                f"Checked model drift — {status.replace('_', ' ').lower()} detected overall, but "
                "none of this case's top drivers are in the drifted features."
            )

    return {
        "drift_context": {
            "status": status,
            "recent_applications": drift["recent_applications"],
            "summary": drift["summary"],
        },
        "investigation_log": [_step("check_drift", description)],
    }


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def _memory_alignment(state: InvestigationState) -> dict:
    """Does institutional memory agree with where this case is heading?

    Returns a traceable verdict — the counts it was computed from travel with
    it, so the adjustment can be audited rather than taken on faith.

    Agreement raises confidence; disagreement or split precedent lowers it and
    says so. One documented exception to the cap: when a sibling application in
    this case's OWN device/IP ring already carries a CONFIRMED_FRAUD verdict,
    that is direct evidence about this specific cluster and outranks
    pattern-similarity precedent from unrelated cases, so the cap does not fire
    (the conflict note is still surfaced).
    """
    memory = state.get("memory_context") or {}
    matches = memory.get("matches") or []
    counts = memory.get("counts") or {}
    fraud = int(counts.get("CONFIRMED_FRAUD", 0))
    legit = int(counts.get("CONFIRMED_LEGITIMATE", 0))
    band = state.get("decision_band")

    if band == "AUTO_FLAG":
        leaning = "fraud"
    elif band == "AUTO_APPROVE":
        leaning = "legitimate"
    else:
        leaning = "unclear"

    alignment = {
        "stance": "neutral",
        "matched": len(matches),
        "confirmed_fraud": fraud,
        "confirmed_legitimate": legit,
        "case_leaning": leaning,
        "note": None,
        "confidence_effect": "none",
    }
    if not matches:
        return alignment

    split = fraud > 0 and legit > 0
    disagrees = (leaning == "fraud" and legit > fraud) or (
        leaning == "legitimate" and fraud > legit
    )

    if split or disagrees:
        alignment["stance"] = "conflicts"
        if split:
            alignment["note"] = (
                f"Institutional memory shows conflicting outcomes for this pattern "
                f"({fraud} confirmed fraud, {legit} confirmed legitimate); recommend "
                "particularly careful human review."
            )
        else:
            alignment["note"] = (
                f"Institutional memory disagrees with the model here: similar past cases "
                f"were mostly confirmed "
                f"{'legitimate' if leaning == 'fraud' else 'fraudulent'} "
                f"({fraud} fraud vs {legit} legitimate); recommend particularly careful "
                "human review."
            )
        ring_confirmed = int((state.get("ring_feedback_history") or {}).get(
            "confirmed_fraud", 0
        ))
        alignment["confidence_effect"] = (
            "none_direct_ring_evidence" if ring_confirmed > 0 else "capped_at_medium"
        )
        return alignment

    if (leaning == "fraud" and fraud > 0) or (leaning == "legitimate" and legit > 0):
        alignment["stance"] = "supports"
    elif leaning == "unclear" and (fraud > 0 or legit > 0):
        # An ambiguous case with one-sided precedent: memory is what resolves it.
        alignment["stance"] = "supports"
    if alignment["stance"] == "supports":
        alignment["confidence_effect"] = "raised" if len(matches) >= 2 else "none"
    return alignment


def _apply_memory_to_confidence(confidence: str, alignment: dict) -> str:
    """The single place memory is allowed to move confidence."""
    if alignment.get("confidence_effect") == "capped_at_medium" and confidence == "HIGH":
        return "MEDIUM"
    if alignment.get("confidence_effect") == "raised" and confidence == "MEDIUM":
        return "HIGH"
    return confidence


def _heuristic_recommendation(state: InvestigationState) -> tuple[str, str]:
    """Deterministic recommendation used by the template fallback."""
    band = state.get("decision_band")
    ring = state.get("ring_context") or {}
    feedback = state.get("ring_feedback_history") or {}
    ring_size = ring.get("ring_size", 0)

    if feedback.get("confirmed_fraud", 0) > 0:
        return (
            "Decline and escalate to the linked fraud-ring investigation",
            "HIGH",
        )
    if band == "AUTO_FLAG":
        if ring_size > 0:
            return (
                "Decline pending manual verification — application is linked to a known cluster",
                "HIGH",
            )
        return ("Hold and decline pending manual identity verification", "HIGH")
    if band == "HUMAN_REVIEW":
        if ring_size >= 3:
            return (
                "Escalate to enhanced review — application sits inside a multi-member "
                "device/IP cluster",
                "MEDIUM",
            )
        return ("Route to standard manual review", "MEDIUM")
    if ring_size > 0:
        return ("Approve with monitoring — cleared by the model but network-linked", "MEDIUM")
    return ("Approve — no material fraud indicators", "LOW")


def _template_synthesis(state: InvestigationState, alignment: dict | None = None) -> dict:
    """Readable summary built from the investigation log. Never fails."""
    action, confidence = _heuristic_recommendation(state)
    alignment = alignment if alignment is not None else _memory_alignment(state)
    confidence = _apply_memory_to_confidence(confidence, alignment)
    trail = " ".join(entry["description"] for entry in state.get("investigation_log", []))
    summary = (
        f"Investigation of a {state.get('decision_band')} case scored "
        f"{state.get('risk_score', 0):.3f}. {trail}"
    )
    if alignment.get("note"):
        summary = f"{summary} Note: {alignment['note']}"
    return {
        "final_recommendation": action,
        "final_confidence": confidence,
        "reasoning_summary": summary,
        "synthesis_source": "template",
        "memory_alignment": alignment,
    }


def _memory_synthesis_note(alignment: dict) -> str:
    """One clause in the synthesis step stating what memory did to the verdict."""
    effect = alignment.get("confidence_effect")
    if effect == "capped_at_medium":
        return (
            " Institutional memory conflicts with this case's direction, so confidence "
            "was held at MEDIUM rather than HIGH."
        )
    if effect == "none_direct_ring_evidence":
        return (
            " Institutional memory shows conflicting precedent, but a confirmed fraud "
            "verdict already exists inside this application's own device/IP ring, which is "
            "direct evidence about this cluster and outranks pattern precedent — confidence "
            "was not reduced, and the conflict is flagged for the reviewer."
        )
    if effect == "raised":
        return (
            f" Institutional memory agrees with this case's direction across "
            f"{alignment.get('matched', 0)} past verdict(s), raising confidence."
        )
    if alignment.get("stance") == "supports":
        return " Institutional memory is consistent with this case's direction."
    return ""


def _parse_llm_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "recommended_action" not in data:
        return None
    return data


def _synthesize(state: InvestigationState, config) -> dict:
    log_text = "\n".join(
        f"{i + 1}. {entry['description']}"
        for i, entry in enumerate(state.get("investigation_log", []))
    )
    drivers = ", ".join(
        f.get("explanation", f.get("feature", ""))
        for f in (state.get("shap_top_features") or [])[:3]
    )
    fallback_action, fallback_confidence = _heuristic_recommendation(state)
    alignment = _memory_alignment(state)

    prompt = (
        f"Model decision: {state.get('decision_band')} at calibrated risk "
        f"{state.get('risk_score', 0):.3f}\n"
        f"Top model drivers: {drivers}\n\n"
        f"Investigation steps actually performed:\n{log_text}\n\n"
        "You are advising a fraud investigator on what to do with this application. "
        "Base your answer ONLY on the investigation steps above — do not invent evidence. "
        'Reply with strict JSON: {"recommended_action": "<one concrete action>", '
        '"confidence": "HIGH"|"MEDIUM"|"LOW", "reasoning_summary": "<2-3 sentences '
        'citing the specific findings above>"}'
    )

    text = _ask_groq(
        "You are the investigation-synthesis layer of a fraud-detection system. You summarise "
        "only what the investigation found and never invent evidence.",
        prompt,
        max_tokens=400,
    )
    parsed = _parse_llm_json(text) if text else None
    if not parsed:
        return {
            "investigation_log": [
                _step(
                    "synthesize",
                    "Synthesised the findings into a recommendation using the deterministic "
                    "summariser (language model unavailable)."
                    + _memory_synthesis_note(alignment),
                )
            ],
            **_template_synthesis(state, alignment),
        }

    confidence = str(parsed.get("confidence", fallback_confidence)).upper()
    if confidence not in {"HIGH", "MEDIUM", "LOW"}:
        confidence = fallback_confidence
    # Memory adjusts the confidence the LLM proposed. Deterministic and
    # traceable: the counts behind the adjustment ship in memory_alignment.
    confidence = _apply_memory_to_confidence(confidence, alignment)

    summary = str(parsed.get("reasoning_summary", "")).strip() or _template_synthesis(
        state, alignment
    )["reasoning_summary"]
    if alignment.get("note") and "institutional memory" not in summary.lower():
        summary = f"{summary} Note: {alignment['note']}"

    return {
        "investigation_log": [
            _step(
                "synthesize",
                "Synthesised all findings into a final recommendation."
                + _memory_synthesis_note(alignment),
            )
        ],
        "final_recommendation": str(parsed.get("recommended_action", fallback_action)),
        "final_confidence": confidence,
        "reasoning_summary": summary,
        "synthesis_source": "groq",
        "memory_alignment": alignment,
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

_graph = None


def build_graph():
    """Compile the investigation graph (cached per process)."""
    global _graph
    if _graph is None:
        builder = StateGraph(InvestigationState)
        builder.add_node("triage", _triage)
        builder.add_node("quick_exit", _quick_exit)
        builder.add_node("check_ring", _check_ring)
        builder.add_node("check_ring_feedback", _check_ring_feedback)
        builder.add_node("check_investigator_memory", _check_investigator_memory)
        builder.add_node("check_similar_cases", _check_similar_cases)
        builder.add_node("check_drift", _check_drift)
        builder.add_node("synthesize", _synthesize)

        builder.add_edge(START, "triage")
        builder.add_conditional_edges(
            "triage",
            _route_after_triage,
            {"quick_exit": "quick_exit", "check_ring": "check_ring"},
        )
        builder.add_edge("quick_exit", END)
        builder.add_conditional_edges(
            "check_ring",
            _route_after_ring,
            {
                "check_ring_feedback": "check_ring_feedback",
                # No ring to cross-reference: skip straight to memory. The two
                # ring branches converge here, so institutional memory is
                # consulted on every deep investigation and on no quick exit.
                "check_investigator_memory": "check_investigator_memory",
            },
        )
        builder.add_edge("check_ring_feedback", "check_investigator_memory")
        builder.add_edge("check_investigator_memory", "check_similar_cases")
        builder.add_edge("check_similar_cases", "check_drift")
        builder.add_edge("check_drift", "synthesize")
        builder.add_edge("synthesize", END)
        _graph = builder.compile()
    return _graph


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_investigation(db: Session, application_id: str) -> dict:
    """Build the initial state from the DB and run the agent graph."""
    app_uuid = uuid_lib.UUID(str(application_id))
    application = db.get(Application, app_uuid)
    if application is None:
        raise ValueError(f"Application {application_id} not found")

    decision = (
        db.execute(
            select(Decision)
            .where(Decision.application_id == app_uuid)
            .order_by(Decision.created_at.desc())
        )
        .scalars()
        .first()
    )
    if decision is None:
        raise ValueError(f"Application {application_id} has no decision to investigate")

    band = (
        decision.decision_band.value
        if hasattr(decision.decision_band, "value")
        else str(decision.decision_band)
    )

    initial: InvestigationState = {
        "application_id": str(application.id),
        "decision_band": band,
        "risk_score": float(decision.calibrated_risk_score),
        "shap_top_features": decision.top_shap_features or [],
        "ring_context": None,
        "ring_feedback_history": None,
        "memory_context": None,
        "memory_alignment": None,
        "similar_cases": None,
        "drift_context": None,
        "investigation_log": [],
        "final_recommendation": None,
        "final_confidence": None,
        "reasoning_summary": None,
        "synthesis_source": None,
        "device_id": application.device_id,
        "ip_hash": application.ip_hash,
        "base_ring_size": int(decision.ring_size or 0),
    }

    final = build_graph().invoke(initial, config={"configurable": {"db": db}})

    return {
        "application_id": str(application.id),
        "investigation_log": final.get("investigation_log", []),
        "recommended_action": final.get("final_recommendation") or "No recommendation produced",
        "confidence": final.get("final_confidence") or "LOW",
        "reasoning_summary": final.get("reasoning_summary") or "",
        "synthesis_source": final.get("synthesis_source") or "template",
        "ring_context": final.get("ring_context"),
        "ring_feedback_history": final.get("ring_feedback_history"),
        "memory_context": final.get("memory_context"),
        "memory_alignment": final.get("memory_alignment"),
        "drift_context": final.get("drift_context"),
        "similar_cases": final.get("similar_cases"),
    }
