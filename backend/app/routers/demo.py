"""Demo-support endpoints: sample IDs, uploaded-document serving, ring device.

DEMO SECURITY NOTE: these endpoints are deliberately UNAUTHENTICATED. The
public applicant page (/apply) needs sample documents and images without a
JWT, and every byte served here is synthetic demo data. In production none
of these endpoints would exist.
"""

from __future__ import annotations

import random
import re
import string
import threading
import uuid
from pathlib import Path

from faker import Faker
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.ml.scoring_service import ML_DIR, get_scoring_service

from generate_synthetic_data import applicant_name_for, id_document_plan  # noqa: E402

router = APIRouter(prefix="/demo", tags=["demo"])

DATA_DIR = ML_DIR.parent / "data" if (ML_DIR.parent / "data" / "applications_train.csv").exists() else Path("/data")
ID_DOCS_DIR = DATA_DIR / "id_documents"
UPLOADS_DIR = DATA_DIR / "uploads"  # applicant-submitted documents land here

_SAMPLE_RE = re.compile(r"^id_[0-9a-f]{12}\.png$")
_UPLOAD_RE = re.compile(r"^upload_[0-9a-f]{12}\.(png|jpg)$")

_samples: dict[str, list[dict]] | None = None
_lock = threading.Lock()


def _load_samples() -> dict[str, list[dict]]:
    global _samples
    if _samples is None:
        with _lock:
            if _samples is None:
                import pandas as pd

                df = pd.read_csv(DATA_DIR / "applications_train.csv")
                with_id = df[df["id_document_filename"].fillna("").str.len() > 0]
                matched: list[dict] = []
                mismatched: list[dict] = []
                for row in with_id.itertuples(index=False):
                    first, last = applicant_name_for(row.application_id)
                    id_first, id_last, is_mismatch = id_document_plan(
                        row.application_id, row.fraud_type
                    )
                    entry = {
                        "filename": row.id_document_filename,
                        "applicant_name": f"{first} {last}",
                        "id_name": f"{id_first} {id_last}",
                        "mismatch": bool(is_mismatch),
                    }
                    (mismatched if is_mismatch else matched).append(entry)
                _samples = {"matched": matched, "mismatched": mismatched}
    return _samples


@router.get("/sample-id")
def sample_id(
    mismatch: bool = Query(default=False),
    scenario: str | None = Query(default=None, pattern="^(matching|mismatching)$"),
) -> dict:
    """A random sample ID card. `scenario=matching|mismatching` or `mismatch=bool`."""
    want_mismatch = scenario == "mismatching" if scenario else mismatch
    pool = _load_samples()["mismatched" if want_mismatch else "matched"]
    if not pool:
        raise HTTPException(status_code=404, detail="No sample ID documents available")
    entry = random.choice(pool)
    return {**entry, "image_url": f"/demo/id-image/{entry['filename']}"}


@router.get("/id-image/{filename}")
def id_image(filename: str) -> FileResponse:
    """Serve a synthetic sample card or an applicant-uploaded document image."""
    if _SAMPLE_RE.match(filename):
        path = ID_DOCS_DIR / filename
    elif _UPLOAD_RE.match(filename):
        path = UPLOADS_DIR / filename
    else:
        raise HTTPException(status_code=404, detail="Unknown document")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document image not found")
    media = "image/jpeg" if filename.endswith(".jpg") else "image/png"
    return FileResponse(path, media_type=media)


def _pick_ring_device() -> dict:
    """A device/IP pair known to connect to seeded flagged applications.

    Picks a historical ring whose members are mostly confirmed fraud, so the
    ring presets reliably light up the ring panel.
    """
    service = get_scoring_service()
    best: tuple[float, int, str, list[str]] | None = None
    for device, apps in service.device_index.items():
        if len(apps) < 4:
            continue
        fraud_fraction = sum(service.fraud_flags.get(a, False) for a in apps) / len(apps)
        candidate = (fraud_fraction, len(apps), device, apps)
        if fraud_fraction >= 0.75 and (best is None or candidate > best):
            best = candidate
    if best is None:
        raise HTTPException(status_code=404, detail="No suitable ring found")

    fraud_fraction, size, device, apps = best
    # Reuse an IP that historically served the same ring, if one exists.
    ip_hash = next(
        (ip for ip, ip_apps in service.ip_index.items() if set(ip_apps) & set(apps)),
        f"ring_ip_{device[:8]}",
    )
    return {
        "device_id": device,
        "ip_hash": ip_hash,
        "known_ring_size": size,
        "known_fraud_fraction": round(fraud_fraction, 2),
    }


@router.get("/ring-device")
def ring_device() -> dict:
    return _pick_ring_device()


# ---------------------------------------------------------------------------
# Fraud-bot profiles (live-demo attack simulation)
#
# SCOPE, STATED PLAINLY: these are DETERMINISTIC SCRIPTED profiles, not an AI
# agent. This endpoint fabricates a realistic-looking application exhibiting a
# chosen attack pattern. Everything downstream of submission - OCR, scoring,
# ring detection, explanation, the LangGraph investigation agent - is the real
# pipeline, unmocked. The only thing automated here is the form-filling a
# human fraudster would otherwise do by hand.
# ---------------------------------------------------------------------------

_faker = Faker("en_IN")

# Text/number inputs on the public form (dropdowns are selected, not pasted).
_PASTEABLE_FIELD_COUNT = 14

_EMPLOYERS = [
    "Trantow-Torphy Group", "Sanchez PLC", "Bray Inc", "Nova Systems Pvt Ltd",
    "Harbour Analytics", "Lakeside Traders",
]


def _pan_number() -> str:
    letters = "".join(random.choice(string.ascii_uppercase) for _ in range(5))
    digits = "".join(random.choice(string.digits) for _ in range(4))
    return f"{letters}{digits}{random.choice(string.ascii_uppercase)}"


def _base_identity() -> dict:
    """Realistic-looking applicant fields shared by every scenario."""
    birth = _faker.date_of_birth(minimum_age=23, maximum_age=58)
    return {
        "full_name": _faker.name(),
        "date_of_birth": birth.isoformat(),
        "pan_number": _pan_number(),
        "email": _faker.free_email(),
        "mobile": _faker.msisdn()[:10],
        "address": _faker.street_address(),
        "city": _faker.city(),
        "state": _faker.state(),
        "pin_code": _faker.postcode(),
        "employment_type": "salaried",
        "employer_name": random.choice(_EMPLOYERS),
        "monthly_income_inr": random.randrange(60_000, 160_000, 5_000),
        "years_in_employment": round(random.uniform(1.0, 9.0), 1),
        "loan_amount_inr": random.randrange(300_000, 1_800_000, 50_000),
        "loan_purpose": random.choice(
            ["home_improvement", "debt_consolidation", "business", "medical"]
        ),
        "purpose_text": "Consolidating existing obligations into a single monthly payment.",
    }


def _fresh_device() -> dict:
    token = uuid.uuid4().hex[:10]
    return {"device_id": f"bot_device_{token}", "ip_hash": f"bot_ip_{token}"}


@router.get("/bot-profile")
def bot_profile(
    scenario: str = Query(..., pattern="^(bot_filler|identity_theft|ring_operator)$"),
) -> dict:
    """A ready-to-submit application exhibiting the requested attack pattern."""
    payload = _base_identity()
    id_document = None

    if scenario == "bot_filler":
        # The tell is behavioural: no human fills a loan form in five seconds
        # with no pointer movement and every field pasted.
        payload.update(_fresh_device())
        payload.update(
            {
                "session_duration_seconds": random.randint(3, 8),
                "mouse_movement_events": random.randint(0, 5),
                "form_paste_count": _PASTEABLE_FIELD_COUNT,
                "income_employer_consistency_score": round(random.uniform(0.62, 0.78), 2),
                "identity_consistency_score": round(random.uniform(0.60, 0.76), 2),
            }
        )
        label = "Automated bot session"
        description = (
            "Automated bot session - near-zero mouse activity, every field pasted, "
            "form completed in seconds"
        )

    elif scenario == "identity_theft":
        # A patient attacker: behaviour looks human. The tell is that the
        # uploaded document belongs to somebody else.
        sample = random.choice(_load_samples()["mismatched"])
        payload.update(_fresh_device())
        payload.update(
            {
                "full_name": sample["applicant_name"],  # the identity being claimed
                "session_duration_seconds": random.randint(180, 320),
                "mouse_movement_events": random.randint(120, 220),
                "form_paste_count": random.randint(0, 2),
                "income_employer_consistency_score": round(random.uniform(0.78, 0.90), 2),
                "identity_consistency_score": round(random.uniform(0.76, 0.88), 2),
            }
        )
        id_document = {
            "filename": sample["filename"],
            "id_name": sample["id_name"],  # the name actually printed on the card
            "claimed_name": sample["applicant_name"],
            "image_url": f"/demo/id-image/{sample['filename']}",
        }
        label = "Stolen identity document"
        description = (
            f"Patient human attacker - normal browsing behaviour, but the uploaded ID is "
            f"printed for {sample['id_name']} while the form claims {sample['applicant_name']}"
        )

    else:  # ring_operator
        ring = _pick_ring_device()
        payload.update({"device_id": ring["device_id"], "ip_hash": ring["ip_hash"]})
        velocity = max(2, min(9, ring["known_ring_size"]))
        payload.update(
            {
                "session_duration_seconds": random.randint(90, 170),
                "mouse_movement_events": random.randint(60, 130),
                "form_paste_count": random.randint(2, 5),
                "applications_from_device_last_24h": velocity,
                "applications_from_ip_last_24h": velocity,
                "income_employer_consistency_score": round(random.uniform(0.60, 0.80), 2),
                "identity_consistency_score": round(random.uniform(0.58, 0.78), 2),
            }
        )
        label = "Fraud ring operator"
        description = (
            f"Ring operator - new identity submitted from a device already linked to "
            f"{ring['known_ring_size']} applications, "
            f"{ring['known_fraud_fraction']:.0%} of them confirmed fraudulent"
        )

    return {
        **payload,
        "scenario": scenario,
        "scenario_label": label,
        "scenario_description": description,
        "id_document": id_document,
    }
