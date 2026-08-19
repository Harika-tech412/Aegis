"""Generate synthetic fraud-investigator case narratives for the Aegis RAG corpus.

This is the ONLY place an LLM touches data generation in Aegis. The tabular
dataset is produced programmatically by `generate_synthetic_data.py`; this
script produces free-text case notes that the retrieval layer will embed and
search over later.

All narratives describe fictional cases. No real investigation, investigator,
customer, or institution is referenced.

Generation falls through three tiers per narrative, so a provider outage or a
spent quota degrades the corpus rather than failing the run:

    1. Groq        openai/gpt-oss-20b
    2. Gemini      gemini-2.5-flash        (on any Groq failure)
    3. Template    deterministic string    (last resort)

A Groq *tokens-per-day* ceiling disables Groq for the remainder of the run -
unlike a per-minute limit, it will not clear before the script finishes, so
retrying it only wastes time. Per-minute limits still get a short backoff.

The script is **resumable**: re-running it keeps every narrative already
produced by Groq or Gemini and retries only the ones that fell through to a
template. Re-run it after quota frees up to fill in the gaps.

Keys are read from a `.env` file at the project root:

    GROQ_API_KEY=gsk_...
    GEMINI_API_KEY=...

Run standalone:

    python ml/generate_narratives.py

Output:
    data/case_narratives.json
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

try:  # groq exports these; fall back gracefully if the SDK layout shifts
    from groq import APIConnectionError, APIStatusError, Groq, RateLimitError
except ImportError:  # pragma: no cover - defensive
    from groq import Groq  # type: ignore

    class RateLimitError(Exception):  # type: ignore
        pass

    class APIStatusError(Exception):  # type: ignore
        pass

    class APIConnectionError(Exception):  # type: ignore
        pass


try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - Gemini fallback simply stays disabled
    genai = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "case_narratives.json"

GROQ_MODEL = "openai/gpt-oss-20b"
GEMINI_MODEL = "gemini-2.5-flash"
SEED = 4242

# 5 archetypes x 22 + 10 false alarms = 120 narratives exactly.
PER_ARCHETYPE = 22
FALSE_ALARM_COUNT = 10

# Per-minute Groq limits clear in seconds, so a short backoff is worth it.
RETRY_BACKOFF_SECONDS = [1, 2, 4]
REQUEST_SPACING_SECONDS = 0.35  # gentle pacing to stay under the free-tier RPM

# Gemini's free-tier ceiling is per-minute too, but with far less headroom, so
# its backoff is measured in tens of seconds rather than single digits.
GEMINI_RETRY_BACKOFF_SECONDS = [4, 10, 20]
# gemini-2.5-flash is a thinking model: reasoning tokens are drawn from the
# same output budget, so a 320-token cap can leave nothing for the answer.
GEMINI_MAX_OUTPUT_TOKENS = 1024

MIN_NARRATIVE_WORDS = 35

# Records already produced by a real LLM are never regenerated - a re-run only
# retries the ones that fell through to the deterministic template.
LLM_SOURCES = ("groq", "gemini")

SYSTEM_PROMPT = (
    "You are a senior fraud investigator at a digital lending institution writing "
    "internal case notes. Write in clipped, factual, first-person-plural "
    "investigator prose. Reference the specific signals and numbers you are given. "
    "State what was observed, what it indicated, and what action was taken. "
    "No preamble, no headings, no bullet points, no closing summary line - just "
    "the case note itself as one or two short paragraphs of 60 to 120 words. "
    "Never invent a real company, bank, or person's name."
)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    fraud_type: str
    signals: dict[str, object]
    outcome: str


# --------------------------------------------------------------------------
# Case construction (varied numbers so narratives do not read as templated)
# --------------------------------------------------------------------------

ARCHETYPE_OUTCOMES = {
    "device_recycling": [
        "Confirmed fraud ring. All linked applications declined and the device fingerprint blocklisted.",
        "Confirmed fraud. Applications declined, device and IP added to the shared-signal watchlist.",
        "Confirmed fraud. Ring escalated to the SAR filing queue.",
    ],
    "velocity_attack": [
        "Confirmed automated attack. Burst declined in full and the source IP rate-limited.",
        "Confirmed fraud. Applications declined and the originating subnet throttled at the edge.",
        "Confirmed fraud. Escalated to the bot-mitigation team for signature capture.",
    ],
    "session_anomaly": [
        "Confirmed scripted submission. Application declined and the session signature added to detection rules.",
        "Confirmed automation. Declined, with the timing fingerprint fed back into the model.",
        "Confirmed bot traffic. Declined and challenged on re-attempt.",
    ],
    "income_mismatch": [
        "Confirmed income misrepresentation. Application declined after employer verification failed.",
        "Confirmed fabricated income. Declined and flagged for repeat-applicant monitoring.",
        "Confirmed misstatement. Declined; applicant invited to reapply with verified documentation.",
    ],
    "identity_inconsistency": [
        "Confirmed synthetic identity. Application declined and the identity cluster escalated.",
        "Confirmed identity fabrication. Declined and referred to the identity-risk team.",
        "Confirmed third-party identity misuse. Declined and the true identity holder notified.",
    ],
    "false_alarm": [
        "Cleared. Legitimate applicant; the flagged signals had an innocent explanation. Application returned to normal processing.",
        "Cleared after verification. No fraud indicators substantiated; approved on standard terms.",
        "Cleared. Review closed as a false positive and the case retained as a tuning example.",
    ],
}

FALSE_ALARM_STORIES = [
    (
        "Three applications from one household device inside 30 hours",
        "shared home computer used by three adult family members applying separately after a joint budgeting conversation; "
        "distinct verified identities, distinct employers, distinct funding needs",
    ),
    (
        "Near-zero pointer movement across the full session",
        "applicant uses switch-access assistive technology, which generates almost no mouse-movement telemetry; "
        "session lasted over eight minutes with entirely manual keyboard entry",
    ),
    (
        "Every form field populated by paste",
        "applicant used a password manager with autofill enabled; pointer movement, dwell time and correction rate all within normal human range",
    ),
    (
        "Address and phone mismatch against bureau records",
        "applicant relocated for work six weeks ago and the bureau file had not yet refreshed; "
        "lease agreement and updated carrier record confirmed the new details",
    ),
    (
        "Declared income implausible for stated employer",
        "applicant recently transitioned from salaried employment to self-employed consulting at a materially higher rate; "
        "two years of filed returns and signed client contracts supported the figure",
    ),
    (
        "Two applications from the same IP within an hour",
        "small shared-office network with a single egress IP; the two applicants are unrelated tenants of the same co-working floor",
    ),
    (
        "Very short session with high completion speed",
        "returning customer whose details were pre-filled from a prior approved application; "
        "the short session reflects a resumed draft, not automation",
    ),
    (
        "Identity consistency score in the bottom decile",
        "applicant recently changed their legal name; the mismatch is between the pre- and post-change records, both of which were verified",
    ),
    (
        "Device seen on a prior declined application",
        "applicant borrowed a relative's laptop after their own device failed; the earlier decline was unrelated and credit-driven",
    ),
    (
        "Burst of three submissions from one account in twenty minutes",
        "applicant submitted, spotted a typo in the requested amount, and resubmitted twice; "
        "identical verified identity on all three, only the amount field differed",
    ),
]


def _build_case_specs(rng: np.random.Generator) -> list[CaseSpec]:
    specs: list[CaseSpec] = []
    counter = 0

    for archetype in [
        "device_recycling",
        "velocity_attack",
        "session_anomaly",
        "income_mismatch",
        "identity_inconsistency",
    ]:
        for _ in range(PER_ARCHETYPE):
            counter += 1
            specs.append(
                CaseSpec(
                    case_id=f"AEG-CASE-{counter:04d}",
                    fraud_type=archetype,
                    signals=_signals_for(archetype, rng),
                    outcome=str(rng.choice(ARCHETYPE_OUTCOMES[archetype])),
                )
            )

    order = rng.permutation(len(FALSE_ALARM_STORIES))[:FALSE_ALARM_COUNT]
    for pos in order:
        counter += 1
        trigger, explanation = FALSE_ALARM_STORIES[int(pos)]
        specs.append(
            CaseSpec(
                case_id=f"AEG-CASE-{counter:04d}",
                fraud_type="false_alarm",
                signals={
                    "initial_trigger": trigger,
                    "verification_finding": explanation,
                    "review_duration_minutes": int(rng.integers(12, 95)),
                    "risk_score_at_flag": round(float(rng.uniform(0.52, 0.81)), 2),
                },
                outcome=str(rng.choice(ARCHETYPE_OUTCOMES["false_alarm"])),
            )
        )

    return specs


def _signals_for(archetype: str, rng: np.random.Generator) -> dict[str, object]:
    """Draw plausible, varied signal values so no two case notes share numbers."""
    risk = round(float(rng.uniform(0.78, 0.98)), 2)

    if archetype == "device_recycling":
        return {
            "linked_applications": int(rng.integers(3, 9)),
            "window_hours": int(rng.integers(24, 49)),
            "shared_device_fingerprint": True,
            "shared_ip": bool(rng.random() < 0.8),
            "distinct_declared_identities": int(rng.integers(3, 9)),
            "mean_session_seconds": int(rng.integers(60, 140)),
            "total_requested_amount": int(rng.integers(18, 210)) * 1_000,
            "risk_score": risk,
        }
    if archetype == "velocity_attack":
        return {
            "applications_in_burst": int(rng.integers(4, 10)),
            "burst_duration_minutes": int(rng.integers(45, 185)),
            "shared_ip": True,
            "rotating_device_fingerprints": int(rng.integers(4, 10)),
            "employer_declared_identically": True,
            "income_variance_pct": round(float(rng.uniform(1.0, 6.0)), 1),
            "risk_score": risk,
        }
    if archetype == "session_anomaly":
        return {
            "mouse_movement_events": int(rng.integers(0, 9)),
            "form_paste_count": int(rng.integers(5, 12)),
            "session_duration_seconds": int(rng.integers(14, 59)),
            "keystroke_cadence": "uniform, sub-human interval variance",
            "matching_sessions_same_week": int(rng.integers(2, 15)),
            "risk_score": risk,
        }
    if archetype == "income_mismatch":
        return {
            "declared_income": int(rng.integers(95, 240)) * 1_000,
            "employer_band_midpoint": int(rng.integers(32, 68)) * 1_000,
            "income_employer_consistency_score": round(float(rng.uniform(0.03, 0.28)), 2),
            "employment_type": str(rng.choice(["gig_worker", "self_employed", "salaried"])),
            "requested_amount": int(rng.integers(15, 50)) * 1_000,
            "verification_outcome": "employer could not confirm stated role or compensation",
            "risk_score": risk,
        }
    if archetype == "identity_inconsistency":
        return {
            "identity_consistency_score": round(float(rng.uniform(0.03, 0.29)), 2),
            "mismatched_fields": list(
                rng.choice(
                    ["surname spelling", "street address", "phone carrier record", "date of birth", "email tenure"],
                    size=int(rng.integers(2, 4)),
                    replace=False,
                )
            ),
            "bureau_file_age_days": int(rng.integers(4, 70)),
            "prior_applications_same_ssn_pattern": int(rng.integers(0, 5)),
            "risk_score": risk,
        }
    raise ValueError(f"unknown archetype: {archetype}")


# --------------------------------------------------------------------------
# Prompting
# --------------------------------------------------------------------------


def _user_prompt(spec: CaseSpec) -> str:
    signal_lines = "\n".join(f"- {k}: {v}" for k, v in spec.signals.items())
    if spec.fraud_type == "false_alarm":
        framing = (
            "This case was flagged for manual review and, after investigation, confirmed "
            "LEGITIMATE. Write the note so it is clear the flag was reasonable but the "
            "applicant did nothing wrong. Do not imply residual suspicion."
        )
    else:
        framing = (
            f"This case was confirmed fraud of type: {spec.fraud_type.replace('_', ' ')}. "
            "Write the note so the reasoning from signals to conclusion is explicit."
        )

    return (
        f"Case reference: {spec.case_id}\n"
        f"{framing}\n\n"
        f"Signals on file:\n{signal_lines}\n\n"
        f"Disposition: {spec.outcome}\n\n"
        "Write the investigator case note now. 60-120 words. Weave in the specific "
        "numbers above rather than describing them generically."
    )


def _clean(text: str) -> str:
    text = text.strip()
    for prefix in ("Case note:", "Case Note:", "Investigator note:", "Note:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text


# --------------------------------------------------------------------------
# Fallback
# --------------------------------------------------------------------------


def _template_narrative(spec: CaseSpec) -> str:
    """Deterministic narrative used when Groq is unavailable, so the run never fails."""
    detail = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in spec.signals.items())

    if spec.fraud_type == "false_alarm":
        return (
            f"Case {spec.case_id} entered the review queue on an automated flag. "
            f"Recorded signals: {detail}. On review, each flagged signal had a documented, "
            "innocent explanation, and supporting evidence was obtained directly from the "
            "applicant and third-party records. No indicators of misrepresentation, "
            "automation, or identity misuse were substantiated. "
            f"{spec.outcome} Retained as a tuning reference for threshold calibration."
        )

    readable = spec.fraud_type.replace("_", " ")
    return (
        f"Case {spec.case_id} was escalated on a {readable} pattern. "
        f"Recorded signals: {detail}. Taken together these are inconsistent with "
        "genuine applicant behaviour and align with the established "
        f"{readable} typology. Corroborating checks against linked applications and "
        f"third-party records supported the assessment. {spec.outcome}"
    )


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def _is_tpd_error(error: object) -> bool:
    """True for a Groq tokens-per-DAY ceiling, as opposed to a per-minute one.

    The distinction matters: a per-minute limit clears in seconds and is worth
    retrying, while a daily token ceiling does not clear until rollover. Once
    we see one, retrying Groq for the rest of the run is pure waste.
    """
    message = str(error).lower()
    return "tokens per day" in message or "tpd" in message


def _is_rate_limit(error: object) -> bool:
    message = str(error).lower()
    return (
        isinstance(error, RateLimitError)
        or "rate_limit" in message
        or "rate limit" in message
        or "429" in message
        or "resource_exhausted" in message
        or "quota" in message
    )


class Providers:
    """Groq -> Gemini -> template, with Groq disabled for the run on a TPD wall."""

    def __init__(self, groq_client, gemini_model) -> None:
        self.groq = groq_client
        self.gemini = gemini_model
        self.groq_disabled_reason: str | None = None
        self.counts = {"groq": 0, "gemini": 0, "template_fallback": 0}

    # -- Groq ----------------------------------------------------------------

    def _try_groq(self, spec: CaseSpec) -> tuple[str | None, object]:
        last_error: object = "groq not configured"
        if self.groq is None or self.groq_disabled_reason:
            return None, self.groq_disabled_reason or last_error

        for attempt, backoff in enumerate([*RETRY_BACKOFF_SECONDS, None]):
            try:
                response = self.groq.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _user_prompt(spec)},
                    ],
                    temperature=0.95,
                    top_p=0.95,
                    max_tokens=320,
                )
                text = _clean(response.choices[0].message.content or "")
                if len(text.split()) >= MIN_NARRATIVE_WORDS:
                    return text, None
                last_error = ValueError(f"response too short ({len(text.split())} words)")
            except Exception as exc:  # noqa: BLE001 - one bad case must not kill the run
                last_error = exc

            # A daily token ceiling will not clear during this run. Stop asking
            # Groq entirely and let Gemini carry the rest.
            if _is_tpd_error(last_error):
                self.groq_disabled_reason = str(last_error)
                print(
                    f"  [groq disabled] {spec.case_id}: daily token ceiling reached; "
                    "switching to Gemini for the remainder of this run"
                )
                return None, last_error

            # Only per-minute limits are worth waiting out. Anything else -
            # connection error, timeout, bad response - goes straight to Gemini.
            if backoff is None or not _is_rate_limit(last_error):
                break
            print(
                f"  [groq retry {attempt + 1}/{len(RETRY_BACKOFF_SECONDS)}] "
                f"{spec.case_id}: {last_error}"
            )
            time.sleep(backoff)

        return None, last_error

    # -- Gemini --------------------------------------------------------------

    def _try_gemini(self, spec: CaseSpec) -> tuple[str | None, object]:
        last_error: object = "gemini not configured"
        if self.gemini is None:
            return None, last_error

        for attempt, backoff in enumerate([*GEMINI_RETRY_BACKOFF_SECONDS, None]):
            try:
                response = self.gemini.generate_content(
                    _user_prompt(spec),
                    generation_config={
                        "temperature": 0.95,
                        "top_p": 0.95,
                        "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
                    },
                )
                text = ""
                try:
                    text = _clean(response.text or "")
                except (ValueError, AttributeError):
                    # .text raises when the candidate carries no usable parts.
                    finish = None
                    try:
                        finish = response.candidates[0].finish_reason
                    except (AttributeError, IndexError):
                        pass
                    raise ValueError(f"no text in Gemini response (finish_reason={finish})")

                if len(text.split()) >= MIN_NARRATIVE_WORDS:
                    return text, None
                last_error = ValueError(f"response too short ({len(text.split())} words)")
            except Exception as exc:  # noqa: BLE001
                last_error = exc

            if backoff is None or not _is_rate_limit(last_error):
                break
            print(
                f"  [gemini retry {attempt + 1}/{len(GEMINI_RETRY_BACKOFF_SECONDS)}] "
                f"{spec.case_id}: {last_error}"
            )
            time.sleep(backoff)

        return None, last_error

    # -- Chain ---------------------------------------------------------------

    def generate(self, spec: CaseSpec) -> tuple[str, str]:
        """Return (narrative_text, generated_by), never raising."""
        text, groq_error = self._try_groq(spec)
        if text is not None:
            self.counts["groq"] += 1
            time.sleep(REQUEST_SPACING_SECONDS)
            return text, "groq"

        text, gemini_error = self._try_gemini(spec)
        if text is not None:
            self.counts["gemini"] += 1
            print(f"  [gemini] {spec.case_id}: recovered after Groq failed ({groq_error})")
            return text, "gemini"

        self.counts["template_fallback"] += 1
        print(f"  [template] {spec.case_id}: groq={groq_error} | gemini={gemini_error}")
        return _template_narrative(spec), "template_fallback"


# --------------------------------------------------------------------------
# Resume support
# --------------------------------------------------------------------------


def _load_existing() -> dict[str, dict]:
    """Existing narratives worth keeping, keyed by case_id.

    Only records produced by a real LLM survive. Template fallbacks are dropped
    so this run can try to replace them.
    """
    if not OUTPUT_PATH.exists():
        return {}
    try:
        records = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not read {OUTPUT_PATH.name} ({exc}); starting fresh.")
        return {}

    keep = {
        r["case_id"]: r
        for r in records
        if isinstance(r, dict) and r.get("generated_by") in LLM_SOURCES and r.get("narrative_text")
    }
    dropped = len(records) - len(keep)
    print(
        f"Resuming from {OUTPUT_PATH.name}: keeping {len(keep)} existing LLM narratives, "
        f"retrying {dropped} template fallback(s)."
    )
    return keep


def _build_clients() -> tuple[object | None, object | None]:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    groq_client = None
    if groq_key:
        try:
            groq_client = Groq(api_key=groq_key)
        except Exception as exc:  # noqa: BLE001
            print(f"Groq client unavailable ({exc}); skipping Groq.")
    else:
        print("GROQ_API_KEY not set - skipping Groq.")

    gemini_model = None
    if gemini_key and genai is not None:
        try:
            genai.configure(api_key=gemini_key)
            gemini_model = genai.GenerativeModel(
                GEMINI_MODEL, system_instruction=SYSTEM_PROMPT
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Gemini client unavailable ({exc}); skipping Gemini.")
    elif not gemini_key:
        print("GEMINI_API_KEY not set - skipping the Gemini fallback tier.")
    elif genai is None:
        print("google-generativeai not installed - skipping the Gemini fallback tier.")

    return groq_client, gemini_model


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    rng = np.random.default_rng(SEED)
    specs = _build_case_specs(rng)
    existing = _load_existing()

    groq_client, gemini_model = _build_clients()
    providers = Providers(groq_client, gemini_model)

    todo = [s for s in specs if s.case_id not in existing]
    if not todo:
        print("Every narrative already has real LLM output - nothing to regenerate.")
    else:
        print(
            f"Generating {len(todo)} of {len(specs)} narratives "
            f"(Groq {GROQ_MODEL} -> Gemini {GEMINI_MODEL} -> template)..."
        )

    records: list[dict] = []
    done = 0
    for spec in specs:
        cached = existing.get(spec.case_id)
        if cached is not None:
            records.append(
                {
                    "case_id": spec.case_id,
                    "fraud_type": spec.fraud_type,
                    "narrative_text": cached["narrative_text"],
                    "generated_by": cached["generated_by"],
                }
            )
            continue

        text, source = providers.generate(spec)
        records.append(
            {
                "case_id": spec.case_id,
                "fraud_type": spec.fraud_type,
                "narrative_text": text,
                "generated_by": source,
            }
        )
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(todo)} generated this run")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in records:
        by_source[r["generated_by"]] = by_source.get(r["generated_by"], 0) + 1
        by_type[r["fraud_type"]] = by_type.get(r["fraud_type"], 0) + 1

    print()
    print("=" * 70)
    print(f"Wrote {len(records)} narratives to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print("=" * 70)
    print(f"  from Groq ({GROQ_MODEL}):     {by_source.get('groq', 0)}")
    print(f"  from Gemini ({GEMINI_MODEL}):    {by_source.get('gemini', 0)}")
    print(f"  from template fallback:            {by_source.get('template_fallback', 0)}")
    print(
        f"  reused from previous run: {len(existing)} | generated this run: {done} "
        f"(groq {providers.counts['groq']}, gemini {providers.counts['gemini']}, "
        f"template {providers.counts['template_fallback']})"
    )
    if providers.groq_disabled_reason:
        print("  note: Groq was disabled mid-run on a tokens-per-day ceiling")

    fallbacks = [r["case_id"] for r in records if r["generated_by"] == "template_fallback"]
    if fallbacks:
        preview = ", ".join(fallbacks[:10])
        more = f" (+{len(fallbacks) - 10} more)" if len(fallbacks) > 10 else ""
        print(f"  fallback case ids: {preview}{more}")
        print("  re-run this script to retry just those once quota frees up")

    print("  by fraud_type:")
    for fraud_type, count in by_type.items():
        print(f"    {fraud_type:<24} {count:>4}")

    print("  by fraud_type x source:")
    for fraud_type in sorted(by_type):
        parts = []
        for source in (*LLM_SOURCES, "template_fallback"):
            c = sum(
                1
                for r in records
                if r["fraud_type"] == fraud_type and r["generated_by"] == source
            )
            parts.append(f"{source} {c}")
        print(f"    {fraud_type:<24} {' | '.join(parts)}")

    words = [len(r["narrative_text"].split()) for r in records]
    print(f"  word count: min {min(words)} / mean {sum(words) / len(words):.0f} / max {max(words)}")


if __name__ == "__main__":
    main()
