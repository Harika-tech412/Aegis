"""Aegis Network — cross-institution fraud signal sharing.

PRIVACY MODEL, stated precisely because the whole feature rests on it:

    signal_hash = SHA-256( NETWORK_HASH_SALT || raw_value )

Only that digest is ever written to `network_fraud_signals` or transmitted
between institutions. The raw device fingerprint / IP / document hash is never
stored in the network table and cannot be recovered from the digest. A partner
institution can answer exactly one question — "have I been told this precise
value is fraudulent?" — and can never answer "what is the value?" or "whose
was it?".

The salt is the network membership key: identical across members, secret from
outsiders. Two institutions holding the salt compute identical hashes for the
same device and can therefore match on it. An attacker without the salt cannot
brute-force the space, and rotating the salt invalidates every prior signal.

What deliberately does NOT cross the boundary: names, dates of birth, emails,
addresses, incomes, application contents, risk scores, or SHAP attributions.
Only the digest, the signal type, the reporting institution, and a short
free-text note written by the reporting investigator.
"""

from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Application,
    Decision,
    Institution,
    NetworkFraudSignal,
    SignalType,
)

SYNC_DEMO = "SYNC_DEMO"
PARTNER_A = "PARTNER_A"

INSTITUTION_SEED = [
    (SYNC_DEMO, "Synchrony (Demo)"),
    (PARTNER_A, "Partner Bank A"),
]


def network_hash(raw_value: str) -> str:
    """One-way digest of a raw identifier, scoped to network membership.

    Salt is prepended, not appended, and the digest is hex SHA-256. This is the
    only function that ever sees a raw identifier on its way to the network.
    """
    salted = f"{settings.NETWORK_HASH_SALT}{raw_value}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


# ---------------------------------------------------------------------------
# Institution bootstrap (idempotent, runs at startup)
# ---------------------------------------------------------------------------


def ensure_institutions(db: Session) -> dict[str, Institution]:
    """Seed the two member institutions and backfill legacy applications.

    Create-on-startup replaces Alembic in this project, so the "migration" is
    this: if the institutions table is empty, populate it and assign every
    pre-existing application to SYNC_DEMO. Guarded so re-running is a no-op.
    """
    existing = {i.code: i for i in db.execute(select(Institution)).scalars().all()}
    created = False
    for code, display_name in INSTITUTION_SEED:
        if code not in existing:
            institution = Institution(code=code, display_name=display_name)
            db.add(institution)
            existing[code] = institution
            created = True
    if created:
        db.flush()

    # Backfill: any application without an institution predates this feature.
    sync_demo = existing[SYNC_DEMO]
    orphans = db.execute(
        select(func.count()).select_from(Application).where(Application.institution_id.is_(None))
    ).scalar()
    if orphans:
        db.query(Application).filter(Application.institution_id.is_(None)).update(
            {"institution_id": sync_demo.id}, synchronize_session=False
        )
    if created or orphans:
        db.commit()
    return existing


def get_institution(db: Session, code: str) -> Institution | None:
    return db.execute(select(Institution).where(Institution.code == code)).scalars().first()


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


def publish_signals(
    db: Session,
    application: Application,
    institution_id: uuid_lib.UUID,
    notes: str | None = None,
    confirmed_at: datetime | None = None,
) -> list[NetworkFraudSignal]:
    """Publish this application's device/IP digests to the network.

    Idempotent per (signal_type, signal_hash, institution): re-confirming the
    same case does not duplicate signals.
    """
    published: list[NetworkFraudSignal] = []
    candidates: list[tuple[SignalType, str | None]] = [
        (SignalType.DEVICE_HASH, application.device_id),
        (SignalType.IP_HASH, application.ip_hash),
    ]

    for signal_type, raw in candidates:
        if not raw:
            continue
        digest = network_hash(raw)
        already = (
            db.execute(
                select(NetworkFraudSignal).where(
                    NetworkFraudSignal.signal_type == signal_type,
                    NetworkFraudSignal.signal_hash == digest,
                    NetworkFraudSignal.reported_by_institution_id == institution_id,
                )
            )
            .scalars()
            .first()
        )
        if already is not None:
            continue

        signal = NetworkFraudSignal(
            signal_type=signal_type,
            signal_hash=digest,
            reported_by_institution_id=institution_id,
            original_application_id=application.id,
            fraud_confirmed_at=confirmed_at or datetime.now(timezone.utc),
            notes=notes,
        )
        db.add(signal)
        published.append(signal)

    if published:
        db.flush()
    return published


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------


def check_network(
    db: Session,
    device_id: str | None,
    ip_hash_value: str | None,
    own_institution_id: uuid_lib.UUID | None,
) -> list[dict]:
    """Look up incoming identifiers against signals from OTHER institutions.

    Self-published signals are excluded on purpose: an institution learns
    nothing from being told about a case it already confirmed itself. The
    entire value of the network is cross-institution.
    """
    lookups: list[tuple[SignalType, str]] = []
    if device_id:
        lookups.append((SignalType.DEVICE_HASH, network_hash(device_id)))
    if ip_hash_value:
        lookups.append((SignalType.IP_HASH, network_hash(ip_hash_value)))
    if not lookups:
        return []

    hits: list[dict] = []
    for signal_type, digest in lookups:
        query = (
            select(NetworkFraudSignal, Institution)
            .join(Institution, NetworkFraudSignal.reported_by_institution_id == Institution.id)
            .where(
                NetworkFraudSignal.signal_type == signal_type,
                NetworkFraudSignal.signal_hash == digest,
            )
        )
        if own_institution_id is not None:
            query = query.where(
                NetworkFraudSignal.reported_by_institution_id != own_institution_id
            )
        for signal, institution in db.execute(query).all():
            hits.append(
                {
                    "signal_type": signal.signal_type.value
                    if hasattr(signal.signal_type, "value")
                    else str(signal.signal_type),
                    # The matched digest is safe to surface — it is already a
                    # one-way hash and carries no recoverable identifier.
                    "matched_hash_prefix": signal.signal_hash[:12],
                    "reported_by_code": institution.code,
                    "reported_by": institution.display_name,
                    "fraud_confirmed_at": signal.fraud_confirmed_at.isoformat(),
                    "notes": signal.notes,
                }
            )
    return hits


# ---------------------------------------------------------------------------
# Network statistics (for the /network page)
# ---------------------------------------------------------------------------


def network_stats(db: Session) -> dict:
    member_count = int(
        db.scalar(select(func.count()).select_from(Institution).where(Institution.is_active))
        or 0
    )
    total_signals = int(db.scalar(select(func.count()).select_from(NetworkFraudSignal)) or 0)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_signals = int(
        db.scalar(
            select(func.count())
            .select_from(NetworkFraudSignal)
            .where(NetworkFraudSignal.created_at >= cutoff)
        )
        or 0
    )
    # A "prevented attack" is a persisted decision whose network_hits array is
    # genuinely non-empty — i.e. a cross-institution signal actually influenced
    # it. The text-cast guard matters: a JSON column can hold SQL NULL *or* the
    # JSON value `null`, and `IS NOT NULL` matches the latter. Without this the
    # metric silently counted every decision that merely had the column set,
    # which inflated it to the full application count.
    prevented = int(
        db.scalar(
            select(func.count())
            .select_from(Decision)
            .where(
                Decision.network_hits.isnot(None),
                cast(Decision.network_hits, String).notin_(["null", "[]"]),
            )
        )
        or 0
    )

    by_institution = [
        {"code": code, "display_name": name, "signals_published": int(count)}
        for code, name, count in db.execute(
            select(
                Institution.code,
                Institution.display_name,
                func.count(NetworkFraudSignal.id),
            )
            .outerjoin(
                NetworkFraudSignal,
                NetworkFraudSignal.reported_by_institution_id == Institution.id,
            )
            .group_by(Institution.code, Institution.display_name)
        ).all()
    ]

    return {
        "member_institutions": member_count,
        "total_signals": total_signals,
        "signals_last_24h": recent_signals,
        "prevented_attacks": prevented,
        "by_institution": by_institution,
    }
