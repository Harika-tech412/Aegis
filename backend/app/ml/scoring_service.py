"""Aegis scoring engine: loads trained artifacts once, scores applications.

Reuses the exact feature-building and explanation code from the ml/ package
(ml/features.py, ml/explain.py) rather than duplicating it — training and
serving share one implementation, so they cannot drift apart.

Path contract: the ml/ package sits at <project_root>/ml. Locally that is
resolved relative to this file; in the container, docker-compose mounts
./ml at /ml, which is exactly what the same relative resolution yields.
Override with the AEGIS_ML_DIR env var if the layout ever changes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

# <project_root>/ml — see path contract in the module docstring.
ML_DIR = Path(os.getenv("AEGIS_ML_DIR", Path(__file__).resolve().parents[3] / "ml"))
ARTIFACTS_DIR = ML_DIR / "artifacts"

if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

from explain import (  # noqa: E402 - needs ML_DIR on sys.path first
    counterfactual_explanation,
    explain_application,
    make_explainer,
)
from features import build_feature_matrix, load_spec  # noqa: E402

MODEL_VERSION = "aegis-ensemble-v1"


@dataclass
class ScoringResult:
    model_version: str
    xgboost_probability: float
    anomaly_score: float
    raw_ensemble_score: float
    calibrated_risk_score: float
    decision_band: str
    top_shap_features: list[dict]
    counterfactual: list[dict] | None
    ring_size: int
    ring_risk_score: float
    connected_applications: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


class ScoringService:
    """Loads all artifacts once; every request reuses the same objects."""

    def __init__(self, artifacts_dir: Path = ARTIFACTS_DIR) -> None:
        self.spec = load_spec(artifacts_dir / "feature_spec.json")
        self.feature_names: list[str] = self.spec["feature_names"]
        self.config = json.loads((artifacts_dir / "ensemble_config.json").read_text())

        self.model = XGBClassifier()
        self.model.load_model(str(artifacts_dir / "xgboost_model.json"))
        self.iso = joblib.load(artifacts_dir / "isolation_forest.joblib")
        self.calibrator = joblib.load(artifacts_dir / "calibrator.joblib")
        self.explainer = make_explainer(self.model)

        ring = json.loads((artifacts_dir / "ring_lookup.json").read_text())
        self.device_index: dict[str, list[str]] = ring["device_index"]
        self.ip_index: dict[str, list[str]] = ring["ip_index"]
        self.fraud_flags: dict[str, bool] = ring["application_fraud_flags"]

        bands = self.config["bands"]
        self.lo: float = bands["auto_approve_below"]
        self.hi: float = bands["auto_flag_above"]

    # -- internals -----------------------------------------------------------

    def _anomaly(self, X: pd.DataFrame) -> np.ndarray:
        norm = self.config["anomaly_norm"]
        raw = -self.iso.score_samples(X)
        return np.clip((raw - norm["min"]) / max(norm["max"] - norm["min"], 1e-12), 0.0, 1.0)

    def _pipeline_scores(self, X) -> np.ndarray:
        """Calibrated ensemble score for a feature matrix (used by counterfactuals too)."""
        X = pd.DataFrame(np.asarray(X, dtype=np.float64), columns=self.feature_names)
        raw = (
            self.config["xgb_weight"] * self.model.predict_proba(X)[:, 1]
            + self.config["anomaly_weight"] * self._anomaly(X)
        )
        return self.calibrator.predict(raw)

    def band_of(self, score: float) -> str:
        if score < self.lo:
            return "AUTO_APPROVE"
        if score > self.hi:
            return "AUTO_FLAG"
        return "HUMAN_REVIEW"

    def ring_context(self, device_id: str, ip_hash: str, own_id: str | None = None) -> dict:
        """One-hop ring context from the historical lookup.

        A brand-new device/IP with no matches yields ring_size 0 — a genuinely
        new application cannot be in a ring yet; that is correct behaviour.
        """
        others: set[str] = set()
        others.update(self.device_index.get(device_id, []))
        others.update(self.ip_index.get(ip_hash, []))
        if own_id:
            others.discard(own_id)
        if not others:
            return {"ring_size": 0, "ring_risk_score": 0.0, "connected_applications": []}
        flagged = sum(1 for a in others if self.fraud_flags.get(a, False))
        return {
            "ring_size": len(others) + 1,  # including this application
            "ring_risk_score": flagged / len(others),
            "connected_applications": sorted(others),
        }

    # -- public API ------------------------------------------------------------

    def score(self, application_data: dict, compute_counterfactual: bool = True) -> ScoringResult:
        t0 = time.perf_counter()

        row = dict(application_data)
        row["id_document_filename"] = row.get("id_document_filename") or ""
        X, _, _ = build_feature_matrix(pd.DataFrame([row]), self.spec)

        xgb_p = float(self.model.predict_proba(X)[:, 1][0])
        anom = float(self._anomaly(X)[0])
        raw = self.config["xgb_weight"] * xgb_p + self.config["anomaly_weight"] * anom
        calibrated = float(self.calibrator.predict([raw])[0])
        band = self.band_of(calibrated)

        shap_top = explain_application(X.iloc[0], self.explainer, self.feature_names, top_n=5)

        counterfactual = None
        if compute_counterfactual and band != "AUTO_APPROVE":
            # Boundary into the next better band: FLAG -> below hi, REVIEW -> below lo.
            boundary = self.hi if band == "AUTO_FLAG" else self.lo
            counterfactual = counterfactual_explanation(
                X.iloc[0],
                self.model,
                boundary,
                feature_names=self.feature_names,
                explainer=self.explainer,
                score_fn=self._pipeline_scores,
            )

        ring = self.ring_context(row.get("device_id", ""), row.get("ip_hash", ""))

        return ScoringResult(
            model_version=MODEL_VERSION,
            xgboost_probability=round(xgb_p, 6),
            anomaly_score=round(anom, 6),
            raw_ensemble_score=round(raw, 6),
            calibrated_risk_score=round(calibrated, 6),
            decision_band=band,
            top_shap_features=shap_top,
            counterfactual=counterfactual,
            ring_size=ring["ring_size"],
            ring_risk_score=round(ring["ring_risk_score"], 4),
            connected_applications=ring["connected_applications"],
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )


_service: ScoringService | None = None


def get_scoring_service() -> ScoringService:
    """Process-wide singleton; artifacts load once."""
    global _service
    if _service is None:
        _service = ScoringService()
    return _service
