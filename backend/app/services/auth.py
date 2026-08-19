"""Authentication: bcrypt password hashing + JWT issuance/validation."""

from __future__ import annotations

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
    if settings.JWT_SECRET == PLACEHOLDER_SECRET or not settings.JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is unset or still the placeholder value. "
            "Set a random secret in .env (e.g. `python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\"`) and restart."
        )


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
