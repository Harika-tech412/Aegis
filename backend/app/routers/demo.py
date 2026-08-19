"""Demo-support endpoints: sample IDs, uploaded-document serving, ring device.

DEMO SECURITY NOTE: these endpoints are deliberately UNAUTHENTICATED. The
public applicant page (/apply) needs sample documents and images without a
JWT, and every byte served here is synthetic demo data. In production none
of these endpoints would exist.
"""

from __future__ import annotations

import random
import re
import threading
from pathlib import Path

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


@router.get("/ring-device")
def ring_device() -> dict:
    """A device/IP pair known to connect to seeded flagged applications.

    Picks a historical ring whose members are mostly confirmed fraud, so the
    'Fraud ring member' preset reliably lights up the ring panel.
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
