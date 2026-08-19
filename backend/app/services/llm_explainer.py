"""Natural-language explanations for scoring results.

Provider policy: Groq (openai/gpt-oss-20b) with a 5-second timeout and exactly
one retry, then a deterministic template. Gemini/Cerebras are deliberately
excluded here — they have been unreliable this session, and live scoring
during a demo must NEVER crash and NEVER hang.

The template fallback is a deliberate reliability design choice, not a lesser
feature: the LLM enriches explanations when available, but the system's core
decisioning and explainability (risk score, SHAP factors, ring context,
counterfactuals) never depend on an external API being up. Every field the
template renders comes from the deterministic ML pipeline.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("aegis.llm")

GROQ_TIMEOUT_SECONDS = 5.0
GROQ_MAX_RETRIES = 1  # SDK-level: exactly one retry after the first attempt

_groq_client = None
_groq_disabled = False  # set True on a terminal error (bad key / spent daily quota)


def _get_groq():
    global _groq_client
    if _groq_client is None and settings.GROQ_API_KEY:
        from groq import Groq

        _groq_client = Groq(
            api_key=settings.GROQ_API_KEY,
            timeout=GROQ_TIMEOUT_SECONDS,
            max_retries=GROQ_MAX_RETRIES,
        )
    return _groq_client


def _is_terminal(error: Exception) -> bool:
    msg = str(error).lower()
    return any(m in msg for m in ("tokens per day", "tpd", "401", "403", "invalid api key"))


def _ask_groq(system: str, user: str, max_tokens: int = 260) -> str | None:
    """One guarded Groq call. Returns None on any failure — callers fall back."""
    global _groq_disabled
    if _groq_disabled:
        return None
    client = _get_groq()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL_GROQ,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 - never let the LLM break scoring
        if _is_terminal(exc):
            _groq_disabled = True
            logger.warning("Groq disabled for this process (terminal error): %s", exc)
        else:
            logger.info("Groq unavailable, using template explanation: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Templates (no network, always work)
# ---------------------------------------------------------------------------

_BAND_PHRASES = {
    "AUTO_APPROVE": "cleared for automatic approval",
    "HUMAN_REVIEW": "routed to human review",
    "AUTO_FLAG": "flagged as high risk",
}


def template_explanation(result) -> str:
    """Deterministic explanation built from the scoring result alone."""
    factors = [f["explanation"] for f in result.top_shap_features[:2]]
    parts = [
        f"This application was {_BAND_PHRASES.get(result.decision_band, result.decision_band)} "
        f"with a calibrated risk score of {result.calibrated_risk_score:.3f}."
    ]
    if factors:
        parts.append("Primary factors: " + "; ".join(f.rstrip('.').lower() for f in factors) + ".")
    if result.ring_size > 0:
        parts.append(
            f"This application connects to {result.ring_size - 1} prior application(s) through a "
            f"shared device or IP address, of which {result.ring_risk_score:.0%} were confirmed fraudulent."
        )
    if result.counterfactual:
        actionable = [c for c in result.counterfactual if c.get("required_value") is not None]
        if actionable:
            c = actionable[0]
            parts.append(
                f"The decision would move to a lower-risk band if {c['feature'].replace('_', ' ')} "
                f"were {c['required_value']:g} instead of {c['current_value']:g}."
            )
    return " ".join(parts)


def explain_result(result, application_summary: dict | None = None) -> tuple[str, str]:
    """Return (explanation_text, generated_by) — Groq if available, template otherwise."""
    template = template_explanation(result)

    factors = "\n".join(
        f"- {f['explanation']} (SHAP {f['shap_value']:+.2f})" for f in result.top_shap_features
    )
    ring_line = (
        f"Connected to {result.ring_size - 1} prior applications via shared device/IP; "
        f"{result.ring_risk_score:.0%} of those confirmed fraud."
        if result.ring_size > 0
        else "No device/IP links to prior applications."
    )
    prompt = (
        f"Decision band: {result.decision_band}\n"
        f"Calibrated risk score: {result.calibrated_risk_score:.3f}\n"
        f"Model factors:\n{factors}\n"
        f"Network context: {ring_line}\n\n"
        "Write ONE paragraph (60-90 words) explaining this fraud-screening decision to a "
        "loan operations analyst. Plain professional language, reference the concrete "
        "factors above, no headings, no bullet points, no hedging boilerplate."
    )
    text = _ask_groq(
        "You are the explanation layer of a fraud-detection system for digital lending. "
        "You summarise model outputs faithfully; you never invent factors not provided.",
        prompt,
    )
    if text:
        return text, "groq"
    return template, "template"


def summarize_similar_cases(narratives: list[str]) -> tuple[str, str]:
    """Two-sentence summary of retrieved past-case narratives, template on failure."""
    if not narratives:
        return "No similar past cases found.", "template"

    joined = "\n\n".join(f"Case {i + 1}: {n}" for i, n in enumerate(narratives[:3]))
    text = _ask_groq(
        "You summarise fraud-investigation case notes faithfully and concisely.",
        f"{joined}\n\nSummarise the common pattern across these past cases in exactly "
        "two sentences for an investigator triaging a new, similar application.",
        max_tokens=120,
    )
    if text:
        return text, "groq"

    # Template: lead sentence of each narrative, as a readable listing.
    leads = [n.split(". ")[0].strip().rstrip(".") + "." for n in narratives[:3]]
    return "Similar past cases: " + " ".join(leads), "template"
