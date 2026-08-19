"""Aegis API — FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.ml.scoring_service import get_scoring_service
from app.routers import applications, auth
from app.services.auth import assert_jwt_secret_configured

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aegis")


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_jwt_secret_configured()  # refuse to run with the placeholder secret
    init_db()
    get_scoring_service()  # load ML artifacts once, fail fast if missing
    logger.info("Aegis API ready: database initialised, scoring artifacts loaded")
    yield


app = FastAPI(title="Aegis API", lifespan=lifespan)

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aegis"}
