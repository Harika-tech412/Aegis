"""Authentication: bcrypt password hashing + JWT issuance/validation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Investigator

PLACEHOLDER_SECRET = "change_me_to_a_random_string"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def assert_jwt_secret_configured() -> None:
    """Fail startup loudly if the JWT secret is still the scaffold placeholder.

    This is a security-relevant setting: a known secret means anyone can mint
    valid tokens. Refusing to start beats running silently insecure.
    """
    problems = check_runtime_config()
    if problems:
        raise RuntimeError(
            "Startup configuration is incomplete:\n  - " + "\n  - ".join(problems)
        )


def check_runtime_config() -> list[str]:
    """Every misconfigured setting at once, rather than one per restart.

    Reporting these together matters on a hosted platform: each redeploy costs
    minutes, and discovering JWT_SECRET, then DATABASE_URL, then the next one on
    separate cycles is the slowest possible way to find out.
    """
    problems: list[str] = []

    # Render sets both of these on every service; they are how we tell a hosted
    # deployment from a laptop without guessing.
    hosted = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"))
    where = (
        "the service's Environment settings"
        if hosted
        else "your .env file"
    )

    if not settings.JWT_SECRET or settings.JWT_SECRET == PLACEHOLDER_SECRET:
        problems.append(
            f"JWT_SECRET is unset or still the placeholder. Set it in {where} to a "
            'random string, e.g. `python -c "import secrets; '
            'print(secrets.token_urlsafe(48))"`. A known signing key lets anyone '
            "mint valid tokens, so the app will not start without it."
        )

    # The default DATABASE_URL points at docker-compose's `db` service, which
    # cannot resolve anywhere else. Only flagged when we know we are hosted, so
    # local compose runs are unaffected.
    if hosted and "@db:" in settings.DATABASE_URL:
        problems.append(
            "DATABASE_URL is still the docker-compose default (host `db`), which "
            f"does not resolve here. Set it in {where} to the managed Postgres "
            "connection string."
        )

    return problems


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(username: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRY_MINUTES)
    payload = {"sub": username, "exp": expires}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def authenticate(db: Session, username: str, password: str) -> Investigator | None:
    investigator = db.query(Investigator).filter(Investigator.username == username).first()
    if investigator is None or not verify_password(password, investigator.password_hash):
        return None
    return investigator


def get_current_investigator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Investigator:
    """FastAPI dependency: validates the bearer JWT, returns the investigator."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        username = payload.get("sub")
    except JWTError:
        raise unauthorized
    if not username:
        raise unauthorized

    investigator = db.query(Investigator).filter(Investigator.username == username).first()
    if investigator is None:
        raise unauthorized
    return investigator
