"""Seed Layer 5: three known identities with history and a contact on file.

    docker compose exec backend python /scripts/seed_identity_history.py

MUST run inside the backend container (same DATABASE_URL as the API).

Each identity gets 2-3 prior observations that agree with each other — a
settled pattern — plus the masked contact the institution already holds. The
/apply demo presets submit against IDENTITIES[0], so its name and DOB must
match the preset exactly or the identity key will not resolve.

Idempotent: re-running skips identities that already have history.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]
_BACKEND = _ROOT / "backend" if (_ROOT / "backend").exists() else Path("/app")
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import IdentityHistory, RegisteredContact  # noqa: E402
from app.services import identity_continuity  # noqa: E402

# name, dob, settled city, settled device, settled income, masked contact, seed
IDENTITIES = [
    (
        "Rohan Mehta",
        "1989-03-14",
        "Pune",
        "android",
        68_000.0,
        "+91-XXXXX4471",
        "seed_rohan_mehta_2026",
    ),
    (
        "Ananya Iyer",
        "1993-07-22",
        "Chennai",
        "ios",
        54_000.0,
        "+91-XXXXX8820",
        "seed_ananya_iyer_2026",
    ),
    (
        "Vikram Rao",
        "1985-11-02",
        "Hyderabad",
        "desktop",
        91_000.0,
        "+91-XXXXX1309",
        "seed_vikram_rao_2026",
    ),
]

PRIOR_COUNT = 3


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        for name, dob, city, device, income, masked, seed in IDENTITIES:
            key = identity_continuity.identity_key(name=name, dob=dob)

            existing = db.execute(
                select(IdentityHistory).where(IdentityHistory.identity_key == key)
            ).scalars().all()
            if existing:
                print(f"{name}: already has {len(existing)} observations - skipping")
            else:
                for i in range(PRIOR_COUNT):
                    db.add(
                        IdentityHistory(
                            identity_key=key,
                            city=city,
                            device_type=device,
                            # Small drift, well inside the 30% change threshold,
                            # so the settled pattern reads as settled.
                            income=round(income * (1 + 0.02 * i), 2),
                            application_id=None,
                            observed_at=datetime.now(timezone.utc)
                            - timedelta(days=180 - 60 * i),
                        )
                    )
                print(f"{name}: seeded {PRIOR_COUNT} prior observations ({city}/{device})")

            contact = db.execute(
                select(RegisteredContact).where(RegisteredContact.identity_key == key)
            ).scalars().first()
            if contact is None:
                db.add(
                    RegisteredContact(
                        identity_key=key, masked_contact=masked, demo_code_seed=seed
                    )
                )
                print(f"{name}: registered contact {masked}")
            else:
                print(f"{name}: contact already on file ({contact.masked_contact})")
        db.commit()

        total_history = len(db.execute(select(IdentityHistory)).scalars().all())
        total_contacts = len(db.execute(select(RegisteredContact)).scalars().all())
        print(
            f"identity_history rows: {total_history} | registered_contacts: {total_contacts}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
