"""Model input-drift monitoring via Population Stability Index (PSI).

PSI is the standard drift metric used in real banking model-risk monitoring —
chosen here deliberately over anything exotic, because it is what an actual
model-governance team at a lender would recognise and already have thresholds
for. Conventional interpretation, applied as-is:

    PSI < 0.10        stable
    0.10 – 0.25       mild drift, watch
    > 0.25            significant drift, investigate / consider retraining

Reference distributions (training-time decile bins per numeric feature) come
from ml/artifacts/reference_distribution.json, emitted by ml/train.py and
loaded once at startup — never recomputed per request.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.scoring_service import ARTIFACTS_DIR
from app.models import Application

MIN_SAMPLE = 30  # below this, PSI is noise — report INSUFFICIENT_DATA instead
PSI_MILD = 0.10
PSI_SIGNIFICANT = 0.25
_EPS = 1e-4

_reference: dict | None = None


def load_reference() -> dict:
    """Load reference distributions once (called at startup, cached)."""
    global _reference
    if _reference is None:
        _reference = json.loads((ARTIFACTS_DIR / "reference_distribution.json").read_text())
    return _reference


def _psi(ref_props: np.ndarray, recent_props: np.ndarray) -> float:
    ref = np.clip(ref_props, _EPS, None)
    recent = np.clip(recent_props, _EPS, None)
    return float(np.sum((recent - ref) * np.log(recent / ref)))


def _status(psi: float) -> str:
    if psi > PSI_SIGNIFICANT:
        return "SIGNIFICANT_DRIFT"
    if psi > PSI_MILD:
        return "MILD_DRIFT"
    return "STABLE"


def compute_drift(db: Session, window_hours: int) -> dict:
    reference = load_reference()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    computed_at = datetime.now(timezone.utc).isoformat()

    # raw_payload holds every scored field, including the signal fields that
    # are not first-class columns — so drift covers all 10 numeric features.
    payloads = [
        row[0]
        for row in db.execute(
            select(Application.raw_payload).where(Application.created_at >= cutoff)
        ).all()
    ]

    if len(payloads) < MIN_SAMPLE:
        return {
            "overall_drift_status": "INSUFFICIENT_DATA",
            "recent_applications": len(payloads),
            "window_hours": window_hours,
            "computed_at": computed_at,
            "features": [],
            "summary": (
                f"Only {len(payloads)} application(s) scored in the last {window_hours}h — "
                f"at least {MIN_SAMPLE} are needed for a statistically meaningful PSI. "
                "No drift verdict is issued on small samples."
            ),
        }

    features = []
    worst = 0.0
    for name, ref in reference["features"].items():
        values = np.array(
            [float(p[name]) for p in payloads if p.get(name) is not None], dtype=float
        )
        if len(values) < MIN_SAMPLE:
            continue
        edges = np.array(ref["bin_edges"], dtype=float)
        edges[0], edges[-1] = -np.inf, np.inf  # recent values may exceed training range
        counts, _ = np.histogram(values, bins=edges)
        psi = _psi(np.array(ref["bin_props"]), counts / counts.sum())
        worst = max(worst, psi)
        features.append(
            {
                "feature": name,
                "psi": round(psi, 4),
                "status": _status(psi),
                "reference_mean": round(ref["mean"], 3),
                "recent_mean": round(float(values.mean()), 3),
            }
        )
    features.sort(key=lambda f: -f["psi"])

    overall = _status(worst)
    drifted = [f["feature"] for f in features if f["status"] != "STABLE"]
    if overall == "STABLE":
        summary = (
            f"Input distributions over the last {window_hours}h ({len(payloads)} applications) "
            f"are consistent with training data — worst-feature PSI {worst:.3f}, "
            f"below the {PSI_MILD} stability threshold."
        )
    else:
        summary = (
            f"{'Significant' if overall == 'SIGNIFICANT_DRIFT' else 'Mild'} drift detected over "
            f"the last {window_hours}h ({len(payloads)} applications): "
            f"{', '.join(drifted[:4])} shifted from the training distribution "
            f"(worst PSI {worst:.3f}). "
            + (
                "Investigate the traffic source; scores in drifted regions are less reliable."
                if overall == "SIGNIFICANT_DRIFT"
                else "Worth watching; no action required yet."
            )
        )

    return {
        "overall_drift_status": overall,
        "recent_applications": len(payloads),
        "window_hours": window_hours,
        "computed_at": computed_at,
        "features": features,
        "summary": summary,
    }
