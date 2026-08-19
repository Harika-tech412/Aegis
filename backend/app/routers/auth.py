"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.rate_limit import LOGIN_LIMIT, limiter
from app.schemas import LoginRequest, TokenResponse
from app.services import audit
from app.services.auth import authenticate, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)  # brute-force protection, per client IP
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    investigator = authenticate(db, body.username, body.password)
    if investigator is None:
        # Same message for unknown user and wrong password - no user enumeration.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    audit.log_event(
        db,
        event_type="investigator_login",
        actor=investigator.username,
        target_type="investigator",
        target_id=str(investigator.id),
    )
    db.commit()
    return TokenResponse(access_token=create_access_token(investigator.username))
