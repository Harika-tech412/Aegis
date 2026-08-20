"""Aegis Network endpoints — member roster, signal feed, and statistics.

Everything here is metadata only. The signal feed deliberately returns a short
hash PREFIX rather than the full digest: the full digest is already one-way,
but there is no reason for a UI to carry it, and a truncated prefix makes
accidental correlation across systems harder still.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Institution, Investigator, NetworkFraudSignal
from app.services.auth import get_current_investigator
from app.services.network_service import network_stats

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/institutions")
def list_institutions(
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    rows = db.execute(select(Institution).order_by(Institution.code)).scalars().all()
    return {
        "institutions": [
            {
                "code": i.code,
                "display_name": i.display_name,
                "joined_network_at": i.joined_network_at.isoformat(),
                "is_active": i.is_active,
            }
            for i in rows
        ]
    }


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    return network_stats(db)


@router.get("/signals")
def list_signals(
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    """Recent network signals as METADATA ONLY.

    No raw identifier exists in this table to leak; only the salted digest is
    stored, and only its first 12 characters are returned here.
    """
    rows = db.execute(
        select(NetworkFraudSignal, Institution)
        .join(Institution, NetworkFraudSignal.reported_by_institution_id == Institution.id)
        .order_by(NetworkFraudSignal.created_at.desc())
        .limit(limit)
    ).all()

    return {
        "privacy_note": (
            "Signals are salted SHA-256 digests. No names, identifiers, or application "
            "content is transmitted or stored. Digests are shown truncated."
        ),
        "signals": [
            {
                "signal_type": s.signal_type.value
                if hasattr(s.signal_type, "value")
                else str(s.signal_type),
                "hash_prefix": s.signal_hash[:12],
                "reported_by": institution.display_name,
                "reported_by_code": institution.code,
                "fraud_confirmed_at": s.fraud_confirmed_at.isoformat(),
                "created_at": s.created_at.isoformat(),
                "notes": s.notes,
            }
            for s, institution in rows
        ],
    }


@router.get("/graph")
def graph(
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    """Institution nodes plus edges weighted by cross-institution signal reuse.

    An edge exists between two institutions when signals published by one have
    matched applications scored by the other. With two members this is a single
    edge — deliberately not overengineered.
    """
    from sqlalchemy import String, cast, func

    from app.models import Application, Decision

    institutions = db.execute(select(Institution).order_by(Institution.code)).scalars().all()
    counts = {
        code: int(count)
        for code, count in db.execute(
            select(Institution.code, func.count(NetworkFraudSignal.id))
            .outerjoin(
                NetworkFraudSignal,
                NetworkFraudSignal.reported_by_institution_id == Institution.id,
            )
            .group_by(Institution.code)
        ).all()
    }

    # Count decisions influenced by a signal from another member.
    edges: dict[tuple[str, str], int] = {}
    rows = db.execute(
        select(Decision.network_hits, Institution.code)
        .join(Application, Decision.application_id == Application.id)
        .join(Institution, Application.institution_id == Institution.id)
        .where(
            Decision.network_hits.isnot(None),
            cast(Decision.network_hits, String).notin_(["null", "[]"]),
        )
    ).all()
    for hits, consumer_code in rows:
        for hit in hits or []:
            source = hit.get("reported_by_code")
            if not source or source == consumer_code:
                continue
            key = (source, consumer_code)
            edges[key] = edges.get(key, 0) + 1

    return {
        "nodes": [
            {
                "id": i.code,
                "label": i.display_name,
                "signals_published": counts.get(i.code, 0),
            }
            for i in institutions
        ],
        "links": [
            {"source": source, "target": target, "shared_signal_hits": count}
            for (source, target), count in edges.items()
        ],
    }
