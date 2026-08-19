"""Model monitoring endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Investigator
from app.services.auth import get_current_investigator
from app.services.drift_service import compute_drift

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/drift")
def drift(
    window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    _: Investigator = Depends(get_current_investigator),
) -> dict:
    return compute_drift(db, window_hours)
