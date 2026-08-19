"""Feature engineering for the Aegis tabular fraud model.

`build_feature_matrix(df)` turns the raw application dataframe into the numeric
matrix XGBoost / IsolationForest consume. The fitted specification (feature
order, categorical vocabularies) is saved to `ml/artifacts/feature_spec.json`
so the backend can rebuild the *exact* same matrix at scoring time — column
order and one-hot vocabularies are part of the model contract.

Deliberately excluded from the tabular model:

- `application_id`, `timestamp`            identifiers, not behaviour
- `employer_name`                          high-cardinality string; the signal
                                           it carries is already distilled into
                                           income_employer_consistency_score
- `device_id`, `ip_hash`                   consumed by the graph module
                                           (ml/graph_fraud.py) instead — as raw
                                           features the model would memorise
                                           specific ID strings from the
                                           training rings and generalise badly
- `loan_purpose_text`                      free text, handled by the embedding
                                           layer, not the tabular model
- `id_document_filename`                   only its presence is a feature
                                           (has_id_document); the filename is a
                                           pointer, and the name-match check is
                                           a separate service
- `is_fraud`, `fraud_type`                 labels
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
FEATURE_SPEC_PATH = ARTIFACTS_DIR / "feature_spec.json"

NUMERIC_FEATURES = [
    "applicant_age",
    "annual_income",
    "requested_amount",
    "session_duration_seconds",
    "mouse_movement_events",
    "form_paste_count",
    "applications_from_device_last_24h",
    "applications_from_ip_last_24h",
    "income_employer_consistency_score",
    "identity_consistency_score",
]

CATEGORICAL_FEATURES = ["employment_type", "loan_purpose"]

DERIVED_FEATURES = ["loan_to_income_ratio", "has_id_document"]


def fit_spec(df: pd.DataFrame) -> dict:
    """Derive the feature specification (vocabularies + column order) from data."""
    categories = {
        col: sorted(df[col].dropna().unique().tolist()) for col in CATEGORICAL_FEATURES
    }
    feature_names = list(NUMERIC_FEATURES) + DERIVED_FEATURES + [
        f"{col}={value}" for col in CATEGORICAL_FEATURES for value in categories[col]
    ]
    return {
        "numeric_features": NUMERIC_FEATURES,
        "derived_features": DERIVED_FEATURES,
        "categorical_features": categories,
        "feature_names": feature_names,
    }


def build_feature_matrix(
    df: pd.DataFrame, spec: dict | None = None
) -> tuple[pd.DataFrame, list[str], dict]:
    """Return (X, feature_names, spec) for the given raw application dataframe.

    Pass the saved spec at scoring time; omit it at training time to fit one.
    """
    if spec is None:
        spec = fit_spec(df)

    X = pd.DataFrame(index=df.index)

    for col in spec["numeric_features"]:
        X[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float64)

    # Derived: loan-to-income ratio (income is floored at 15k in generation,
    # but guard the division anyway for scoring-time inputs).
    income = pd.to_numeric(df["annual_income"], errors="coerce").astype(np.float64)
    requested = pd.to_numeric(df["requested_amount"], errors="coerce").astype(np.float64)
    X["loan_to_income_ratio"] = requested / income.clip(lower=1.0)

    # Derived: did the applicant attach an ID document at all.
    X["has_id_document"] = (
        df["id_document_filename"].fillna("").astype(str).str.len() > 0
    ).astype(np.float64)

    # One-hot categoricals against the frozen training vocabulary. Unseen
    # values at scoring time encode as all-zeros rather than erroring.
    for col, vocabulary in spec["categorical_features"].items():
        values = df[col].astype(str)
        for category in vocabulary:
            X[f"{col}={category}"] = (values == category).astype(np.float64)

    X = X[spec["feature_names"]]
    return X, spec["feature_names"], spec


def save_spec(spec: dict, path: Path = FEATURE_SPEC_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")


def load_spec(path: Path = FEATURE_SPEC_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
