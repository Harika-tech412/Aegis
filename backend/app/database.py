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


def init_db() -> None:
    """Create the pgvector extension and all tables. Idempotent."""
    from app import models  # noqa: F401 - register mappings before create_all

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
