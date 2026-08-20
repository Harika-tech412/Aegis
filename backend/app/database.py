"""Database engine, session factory, and startup initialisation.

Schema management: tables are created on startup via `Base.metadata.create_all`.
Alembic is deliberately skipped — for a hackathon timeline with a single
developer and a throwaway database, create-on-startup is the right trade; a
production deployment would use migrations.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Additive column migrations.
#
# `create_all` creates missing TABLES but never alters existing ones, so a new
# column on a table that already exists is invisible to it. Since this project
# deliberately runs create-on-startup instead of Alembic, additive columns are
# applied here explicitly. Every statement is guarded with IF NOT EXISTS, so
# this is safe to run on every boot and on a fresh database alike.
#
# Keep this list append-only and additive. Anything requiring a backfill,
# rename, or type change needs a real migration tool, not this.
_ADDITIVE_COLUMNS = [
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS institution_id UUID "
    "REFERENCES institutions(id)",
    "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS network_hits JSON",
    "ALTER TABLE agent_investigations ADD COLUMN IF NOT EXISTS memory_alignment JSON",
    "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS identity_continuity JSON",
    "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS step_up_result JSON",
]


def init_db() -> None:
    """Create the pgvector extension, all tables, and additive columns. Idempotent."""
    from app import models  # noqa: F401 - register mappings before create_all

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        for statement in _ADDITIVE_COLUMNS:
            conn.execute(text(statement))
        conn.commit()
