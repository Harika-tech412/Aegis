"""Tiny helper for writing audit-log entries alongside business writes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_event(
    db: Session,
    *,
    event_type: str,
    actor: str,
    target_type: str,
    target_id: str,
    details: dict | None = None,
) -> None:
    """Adds an audit row to the session; committed with the caller's transaction."""
    db.add(
        AuditLog(
            event_type=event_type,
            actor=actor,
            target_type=target_type,
            target_id=str(target_id),
            details=details or {},
        )
    )
