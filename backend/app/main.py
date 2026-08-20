"""Aegis API — FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.database import init_db
from app.ml.scoring_service import get_scoring_service
from app.rate_limit import limiter
from app.routers import applications, auth, demo, monitoring, network, public, reports
from app.services.auth import assert_jwt_secret_configured
from app.services.drift_service import load_reference

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aegis")


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_jwt_secret_configured()  # refuse to run with the placeholder secret
    init_db()
    get_scoring_service()  # load ML artifacts once, fail fast if missing
    load_reference()  # drift reference distributions, loaded once

    # Aegis Network bootstrap: seed member institutions and backfill legacy
    # applications to SYNC_DEMO. Idempotent; replaces an Alembic migration.
    try:
        from app.database import SessionLocal
        from app.services.network_service import ensure_institutions

        _session = SessionLocal()
        try:
            _members = ensure_institutions(_session)
            # Log a fingerprint of the hashing salt, never the salt itself.
            # Signals published under a different salt can never match, so a
            # mismatch between seeding and serving must be visible, not silent.
            import hashlib

            from sqlalchemy import func, select

            from app.config import settings as _settings
            from app.models import NetworkFraudSignal as _Signal

            _fingerprint = hashlib.sha256(
                _settings.NETWORK_HASH_SALT.encode("utf-8")
            ).hexdigest()[:8]
            _stored = int(_session.scalar(select(func.count()).select_from(_Signal)) or 0)
            logger.info(
                "Aegis Network: %d member institutions active, %d signals stored, "
                "salt fingerprint %s",
                len(_members),
                _stored,
                _fingerprint,
            )
        finally:
            _session.close()
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        logger.warning("Aegis Network bootstrap skipped: %s", exc)

    # Institutional memory: report size and composition, never silently empty.
    # Deliberately a report and not a backfill — embedding hundreds of
    # signatures belongs in scripts/backfill_case_memory.py, not in every boot.
    try:
        from app.database import SessionLocal
        from app.services.case_memory import memory_stats

        _session = SessionLocal()
        try:
            _stats = memory_stats(_session)
            if _stats["total"] == 0:
                logger.warning(
                    "Institutional memory is EMPTY — run "
                    "scripts/backfill_case_memory.py inside this container"
                )
            else:
                logger.info(
                    "Institutional memory: %d recorded verdicts %s",
                    _stats["total"],
                    _stats["by_source"],
                )
        finally:
            _session.close()
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        logger.warning("Institutional memory check skipped: %s", exc)

    # Prove the EasyOCR weights are cached in the image: download_enabled is
    # False, so this raises if anything is missing rather than reaching for
    # the network mid-demo.
    try:
        from app.services.ocr_service import get_easyocr_reader

        get_easyocr_reader()
        logger.info("EasyOCR reader initialised from cached weights (no network access)")
    except Exception as exc:  # noqa: BLE001 - degrade to Tesseract, never block startup
        logger.warning("EasyOCR unavailable (%s) - generalized OCR falls back to Tesseract", exc)

    logger.info("Aegis API ready: database initialised, scoring artifacts loaded")
    yield


app = FastAPI(title="Aegis API", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Clean JSON 429 instead of slowapi's default response."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Rate limit exceeded: {exc.detail}. Retry shortly.",
        },
    )

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(applications.router)
app.include_router(monitoring.router)
app.include_router(demo.router)
app.include_router(public.router)
app.include_router(reports.router)
app.include_router(network.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aegis"}
