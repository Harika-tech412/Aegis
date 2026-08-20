"""Layer 5 — identity continuity and out-of-band step-up verification.

Two questions no other layer asks:

  1. Does this application look like the SAME identity's own past behaviour?
     Layer 2 asks whether a device is shared by many identities; this asks
     whether one identity has suddenly changed city, device and income at once.
     A single change is life; three at once is worth a second question.

  2. Can the person answer a challenge sent to the contact the institution
     ALREADY holds — not the contact typed on this form? A stolen identity
     usually comes with the attacker's own phone number.

Deliberately small: one hash, one comparison rule, one derived code. Nothing
here is a model.
"""

from __future__ import annotations

import hashlib
import logging
import uuid as uuid_lib

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Application, IdentityHistory, RegisteredContact

logger = logging.getLogger("aegis.identity")

NO_HISTORY = "NO_HISTORY"
CONSISTENT = "CONSISTENT"
INCONSISTENT = "INCONSISTENT"

# A change of this size against the identity's own average is "changed".
INCOME_CHANGE_RATIO = 0.30
# Two or more signals moving together is what makes it worth a challenge.
INCONSISTENT_SIGNAL_COUNT = 2
# How many of the identity's earliest observations define its baseline.
BASELINE_OBSERVATIONS = 3

STEP_UP_CORRECT_DELTA = -0.25
STEP_UP_WRONG_DELTA = 0.40


def identity_key(
    id_number: str | None = None,
    name: str | None = None,
    dob: str | None = None,
    fallback: str | None = None,
) -> str:
    """A stable pseudonymous handle for an identity.

    ID document number when we have one (the strongest identifier), else
    name+DOB. `fallback` (the application id) is used when the payload carries
    no identity fields at all — an investigator /score call, for instance. Such
    a key is unique per application by construction, so those applications
    correctly report NO_HISTORY rather than borrowing someone else's.
    """
    if id_number:
        basis = f"idnum:{id_number.strip().upper()}"
    elif name and dob:
        basis = f"namedob:{name.strip().lower()}|{dob.strip()}"
    else:
        basis = f"appfallback:{fallback or uuid_lib.uuid4().hex}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def key_for_payload(payload: dict, fallback: str | None = None) -> str:
    """Pull the identity fields out of a scoring payload."""
    ocr = payload.get("ocr") or {}
    return identity_key(
        id_number=ocr.get("id_number"),
        name=payload.get("applicant_name"),
        dob=payload.get("date_of_birth"),
        fallback=fallback,
    )


def record_observation(
    db: Session,
    identity_key_value: str,
    application_id,
    *,
    city: str | None,
    device_type: str | None,
    income: float | None,
) -> IdentityHistory:
    """Every scored application leaves one row. Caller commits."""
    row = IdentityHistory(
        identity_key=identity_key_value,
        city=city,
        device_type=device_type,
        income=income,
        application_id=application_id,
    )
    db.add(row)
    db.flush()
    return row


def _mode(values) -> str | None:
    """Most frequent non-empty value, ties broken by first appearance."""
    counts: dict[str, int] = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def check_continuity(
    db: Session,
    identity_key_value: str,
    *,
    city: str | None,
    device_type: str | None,
    income: float | None,
    exclude_application_id=None,
) -> dict:
    """Compare this application against the identity's OWN prior rows."""
    query = select(IdentityHistory).where(
        IdentityHistory.identity_key == identity_key_value
    )
    if exclude_application_id is not None:
        # `application_id != x` is NULL — and therefore false — for the seeded
        # rows, which carry no application. Keep those explicitly.
        query = query.where(
            or_(
                IdentityHistory.application_id.is_(None),
                IdentityHistory.application_id != exclude_application_id,
            )
        )
    all_priors = list(db.execute(query.order_by(IdentityHistory.observed_at)).scalars().all())
    # "Established" means settled, so the baseline is the OLDEST observations.
    # Without this, repeated attempts from a new city would eventually become
    # the majority and the identity's real pattern would be voted out.
    priors = all_priors[:BASELINE_OBSERVATIONS]

    if not priors:
        return {
            "status": NO_HISTORY,
            "prior_observations": 0,
            "changed_signals": [],
            "detail": "No prior application on file for this identity.",
        }

    changed: list[str] = []

    # The established pattern is the MOST COMMON prior value, not "any value
    # ever seen". Comparing against the whole set would let a single previous
    # attempt from a new city permanently normalise that city for this identity
    # — which is exactly what an attacker probing repeatedly would want.
    established_city = _mode(p.city for p in priors)
    if city and established_city and city != established_city:
        changed.append(f"city ({established_city} → {city})")

    established_device = _mode(p.device_type for p in priors)
    if device_type and established_device and device_type != established_device:
        changed.append(f"device type ({established_device} → {device_type})")

    prior_incomes = [p.income for p in priors if p.income]
    if income and prior_incomes:
        # Median, for the same reason: one outlier attempt must not drag the
        # baseline toward itself.
        ordered = sorted(prior_incomes)
        baseline = ordered[len(ordered) // 2]
        if baseline > 0 and abs(income - baseline) / baseline >= INCOME_CHANGE_RATIO:
            changed.append(f"income ({baseline:,.0f} → {income:,.0f})")

    status = INCONSISTENT if len(changed) >= INCONSISTENT_SIGNAL_COUNT else CONSISTENT
    if status == INCONSISTENT:
        detail = (
            f"{len(changed)} signals changed against this identity's own history: "
            + "; ".join(changed)
            + ". Eligible for step-up verification."
        )
    elif changed:
        detail = "Matches this identity's established pattern apart from: " + "; ".join(changed)
    else:
        detail = "Matches this identity's established pattern."

    return {
        "status": status,
        "prior_observations": len(all_priors),
        "baseline_observations": len(priors),
        "changed_signals": changed,
        "detail": detail,
    }


def get_contact(db: Session, identity_key_value: str) -> RegisteredContact | None:
    return (
        db.execute(
            select(RegisteredContact).where(
                RegisteredContact.identity_key == identity_key_value
            )
        )
        .scalars()
        .first()
    )


def expected_code(seed: str, application_id) -> str:
    """The 6-digit code for this (identity, application) pair.

    Derived, not stored: the same inputs always produce the same code, so
    /verify can check an answer without persisting a secret anywhere.
    """
    digest = hashlib.sha256(f"{seed}|{application_id}".encode("utf-8")).hexdigest()
    return f"{int(digest, 16) % 1_000_000:06d}"


def key_for_application(db: Session, application: Application) -> str:
    """Recover the identity key for an already-stored application."""
    return key_for_payload(application.raw_payload or {}, fallback=str(application.id))
