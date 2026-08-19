"""Shared test fixtures.

Test database choice: a separate `aegis_test` database on the SAME dockerized
Postgres instance, not SQLite — the case_narratives table has a pgvector
Vector(384) column that SQLite cannot represent, so an in-memory SQLite double
would silently diverge from the real schema. Creating a sibling database on
the already-running pg16 container is the fastest option that stays faithful.

These tests therefore run where Postgres is reachable — inside the backend
container (`docker compose exec backend python -m pytest tests -v`).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Investigator
from app.services.auth import hash_password

TEST_DB_NAME = "aegis_test"
TEST_USERNAME = "test_investigator"
TEST_PASSWORD = "test_password_123"


def _test_url() -> str:
    base, _, _ = settings.DATABASE_URL.rpartition("/")
    return f"{base}/{TEST_DB_NAME}"


@pytest.fixture(scope="session")
def test_engine():
    # Create the test database if missing (CREATE DATABASE needs autocommit).
    admin = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    engine = create_engine(_test_url())
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def TestSession(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(TestSession):
    session = TestSession()
    yield session
    session.close()


@pytest.fixture(scope="session")
def client(test_engine, TestSession):
    """TestClient with the DB dependency pointed at aegis_test."""
    from fastapi.testclient import TestClient

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:  # runs lifespan: artifacts load once
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def investigator_token(client, TestSession) -> str:
    session = TestSession()
    try:
        if not session.query(Investigator).filter_by(username=TEST_USERNAME).first():
            session.add(
                Investigator(username=TEST_USERNAME, password_hash=hash_password(TEST_PASSWORD))
            )
            session.commit()
    finally:
        session.close()

    response = client.post(
        "/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture()
def auth_headers(investigator_token) -> dict:
    return {"Authorization": f"Bearer {investigator_token}"}
