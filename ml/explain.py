"""Explainability for the Aegis fraud model: SHAP attributions + counterfactuals.

`explain_application` turns a scored application's SHAP values into the top-5
plain-English reasons an investigator actually reads. `counterfactual_explanation`
answers the follow-up question - "what would need to be different for this to
clear?" - by perturbing one feature at a time until the decision band flips.

Both are consumed by the backend at case-review time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shap

# ---------------------------------------------------------------------------
# Plain-English templates - one per feature in the feature spec.
#
# {value} is the feature's value on this application. "direction" phrases are
# chosen by SHAP sign: positive SHAP pushes toward fraud, negative toward
# legitimate.
# ---------------------------------------------------------------------------

FEATURE_TEMPLATES: dict[str, dict[str, str]] = {
    "applicant_age": {
        "label": "Applicant age",
        "toward_fraud": "The applicant's age ({value:.0f}) is atypical for this application profile",
        "toward_legit": "The applicant's age ({value:.0f}) is typical for this application profile",
    },
    "annual_income": {
        "label": "Declared annual income",
        "toward_fraud": "The declared income (${value:,.0f}) is unusual relative to similar applications",
        "toward_legit": "The declared income (${value:,.0f}) is in a normal range",
    },
    "requested_amount": {
        "label": "Requested loan amount",
        "toward_fraud": "The requested amount (${value:,.0f}) is elevated for this profile",
        "toward_legit": "The requested amount (${value:,.0f}) is proportionate for this profile",
    },
    "session_duration_seconds": {
        "label": "Session duration",
        "toward_fraud": "The application was completed in {value:.0f} seconds - unusually fast",
        "toward_legit": "The session length ({value:.0f} seconds) is consistent with a person filling the form",
    },
    "mouse_movement_events": {
        "label": "Mouse movement",
        "toward_fraud": "Only {value:.0f} mouse-movement events were recorded - little sign of a human at the controls",
        "toward_legit": "Mouse activity ({value:.0f} events) is consistent with normal human interaction",
    },
    "form_paste_count": {
        "label": "Pasted form fields",
        "toward_fraud": "{value:.0f} form fields were filled by paste rather than typed",
        "toward_legit": "Form fields were mostly typed ({value:.0f} pasted), as a typical applicant would",
    },
    "applications_from_device_last_24h": {
        "label": "Device velocity (24h)",
        "toward_fraud": "This device submitted {value:.0f} applications in the last 24 hours",
        "toward_legit": "This device shows no unusual application volume ({value:.0f} in 24 hours)",
    },
    "applications_from_ip_last_24h": {
        "label": "IP velocity (24h)",
        "toward_fraud": "This IP address originated {value:.0f} applications in the last 24 hours",
        "toward_legit": "This IP address shows no unusual application volume ({value:.0f} in 24 hours)",
    },
    "income_employer_consistency_score": {
        "label": "Income-employer consistency",
        "toward_fraud": "The declared income is a poor fit for the stated employer (consistency {value:.2f})",
        "toward_legit": "The declared income is plausible for the stated employer (consistency {value:.2f})",
    },
    "identity_consistency_score": {
        "label": "Identity consistency",
        "toward_fraud": "Name, address, and phone records do not line up cleanly (consistency {value:.2f})",
        "toward_legit": "Name, address, and phone records agree (consistency {value:.2f})",
    },
    "loan_to_income_ratio": {
        "label": "Loan-to-income ratio",
        "toward_fraud": "The requested amount is {value:.0%} of declared income - an aggressive ask",
        "toward_legit": "The requested amount is a modest {value:.0%} of declared income",
    },
    "has_id_document": {
        "label": "ID document uploaded",
        "toward_fraud": "An ID document was {value_phrase} - unusual in the context of this profile",
        "toward_legit": "An ID document was {value_phrase}",
    },
    "employment_type=salaried": {
        "label": "Employment: salaried",
        "toward_fraud": "Salaried employment is atypical in the context of this application's other signals",
        "toward_legit": "Salaried employment supports the application's plausibility",
    },
    "employment_type=self_employed": {
        "label": "Employment: self-employed",
        "toward_fraud": "Self-employment adds risk in combination with this application's other signals",
        "toward_legit": "Self-employment is consistent with the rest of the application",
    },
    "employment_type=gig_worker": {
        "label": "Employment: gig worker",
        "toward_fraud": "Gig-economy employment adds risk in combination with this application's other signals",
        "toward_legit": "Gig-economy employment is consistent with the rest of the application",
    },
    "employment_type=unemployed": {
        "label": "Employment: unemployed",
        "toward_fraud": "Unemployed status raises risk given the declared income and requested amount",
        "toward_legit": "Employment status is consistent with the rest of the application",
    },
    "loan_purpose=debt_consolidation": {
        "label": "Purpose: debt consolidation",
        "toward_fraud": "The stated purpose (debt consolidation) is atypical for this risk profile",
        "toward_legit": "The stated purpose (debt consolidation) fits the application profile",
    },
    "loan_purpose=home_improvement": {
        "label": "Purpose: home improvement",
        "toward_fraud": "The stated purpose (home improvement) is atypical for this risk profile",
        "toward_legit": "The stated purpose (home improvement) fits the application profile",
    },
    "loan_purpose=medical": {
        "label": "Purpose: medical",
        "toward_fraud": "The stated purpose (medical) is atypical for this risk profile",
        "toward_legit": "The stated purpose (medical) fits the application profile",
    },
    "loan_purpose=education": {
        "label": "Purpose: education",
        "toward_fraud": "The stated purpose (education) is atypical for this risk profile",
        "toward_legit": "The stated purpose (education) fits the application profile",
    },
    "loan_purpose=business": {
        "label": "Purpose: business",
        "toward_fraud": "The stated purpose (business) is atypical for this risk profile",
        "toward_legit": "The stated purpose (business) fits the application profile",
    },
    "loan_purpose=other": {
        "label": "Purpose: other",
        "toward_fraud": "The stated purpose (other) is atypical for this risk profile",
        "toward_legit": "The stated purpose (other) fits the application profile",
    },
}


def make_explainer(model) -> shap.TreeExplainer:
    return shap.TreeExplainer(model)


def _render_template(feature: str, value: float, shap_value: float) -> str:
    template = FEATURE_TEMPLATES.get(feature)
    if template is None:  # future-proofing: never crash the review screen
        direction = "raises" if shap_value > 0 else "lowers"
        return f"{feature} = {value:.3g} {direction} the risk estimate"

    key = "toward_fraud" if shap_value > 0 else "toward_legit"
    text = template[key]
    if feature == "has_id_document":
        return text.format(value_phrase="uploaded" if value >= 0.5 else "not uploaded")
    return text.format(value=value)


def explain_application(
    feature_row: pd.Series | np.ndarray,
    explainer: shap.TreeExplainer,
    feature_names: list[str],
    top_n: int = 5,
) -> list[dict]:
    """Top contributing features for one application, in plain English.

    Returns a list of {feature, label, value, shap_value, direction, explanation},
    ordered by |SHAP| descending.
    """
    values = np.asarray(feature_row, dtype=np.float64).reshape(1, -1)
    shap_values = np.asarray(explainer.shap_values(values)).reshape(-1)

    order = np.argsort(-np.abs(shap_values))[:top_n]
    results = []
    for idx in order:
        feature = feature_names[idx]
        value = float(values[0, idx])
        sv = float(shap_values[idx])
        results.append(
            {
                "feature": feature,
                "label": FEATURE_TEMPLATES.get(feature, {}).get("label", feature),
                "value": value,
                "shap_value": round(sv, 4),
                "direction": "increases_risk" if sv > 0 else "decreases_risk",
                "explanation": _render_template(feature, value, sv),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Counterfactuals
# ---------------------------------------------------------------------------

# Features an applicant or investigator could meaningfully imagine changing,
# with the plausible range to search over. One-hot columns and derived flags
# are excluded - "be a different kind of employee" is not actionable advice.
COUNTERFACTUAL_BOUNDS: dict[str, tuple[float, float]] = {
    "requested_amount": (1_000.0, 50_000.0),
    "annual_income": (15_000.0, 250_000.0),
    "loan_to_income_ratio": (0.0, 3.5),
    "session_duration_seconds": (10.0, 900.0),
    "mouse_movement_events": (0.0, 300.0),
    "form_paste_count": (0.0, 12.0),
    "applications_from_device_last_24h": (1.0, 10.0),
    "applications_from_ip_last_24h": (1.0, 10.0),
    "income_employer_consistency_score": (0.0, 1.0),
    "identity_consistency_score": (0.0, 1.0),
    "applicant_age": (18.0, 75.0),
}


def counterfactual_explanation(
    feature_row,
    model,
    target_band_boundary: float,
    *,
    feature_names: list[str],
    explainer: shap.TreeExplainer,
    score_fn=None,
    top_n: int = 2,
    tolerance: float = 1e-3,
) -> list[dict]:
    """Minimum single-feature changes that would cross below the band boundary.

    For each of the top `top_n` risk-increasing features (by SHAP), binary
    search the feature value toward its plausible bound until the score drops
    below `target_band_boundary`. Returns a list of
    {feature, current_value, required_value, would_change_decision_to};
    features that cannot flip the decision alone are reported with
    required_value = None.

    `score_fn(matrix) -> scores` should compute the same score the boundary is
    defined on (the calibrated ensemble). If omitted, the model's raw fraud
    probability is used.
    """
    if score_fn is None:
        score_fn = lambda X: model.predict_proba(X)[:, 1]  # noqa: E731

    base = np.asarray(feature_row, dtype=np.float64).reshape(1, -1)
    base_score = float(score_fn(base)[0])

    shap_values = np.asarray(explainer.shap_values(base)).reshape(-1)
    # Only features currently pushing toward fraud and eligible for perturbation.
    candidates = [
        idx
        for idx in np.argsort(-shap_values)
        if shap_values[idx] > 0 and feature_names[idx] in COUNTERFACTUAL_BOUNDS
    ][:top_n]

    results = []
    for idx in candidates:
        feature = feature_names[idx]
        current = float(base[0, idx])
        low_bound, high_bound = COUNTERFACTUAL_BOUNDS[feature]

        # Pick the direction that helps: evaluate the score at each bound and
        # move toward whichever lowers it more.
        best_target, best_score = None, base_score
        for bound in (low_bound, high_bound):
            trial = base.copy()
            trial[0, idx] = bound
            s = float(score_fn(trial)[0])
            if s < best_score:
                best_target, best_score = bound, s

        if best_target is None or best_score >= target_band_boundary:
            results.append(
                {
                    "feature": feature,
                    "current_value": round(current, 4),
                    "required_value": None,
                    "would_change_decision_to": None,
                    "note": "changing this feature alone cannot cross the boundary",
                }
            )
            continue

        # Binary search between current value (above boundary) and the bound
        # (below boundary) for the crossing point.
        near, far = current, float(best_target)
        for _ in range(40):
            mid = (near + far) / 2.0
            trial = base.copy()
            trial[0, idx] = mid
            if float(score_fn(trial)[0]) < target_band_boundary:
                far = mid
            else:
                near = mid
            if abs(far - near) < tolerance * max(1.0, abs(current)):
                break

        results.append(
            {
                "feature": feature,
                "current_value": round(current, 4),
                "required_value": round(far, 4),
                "would_change_decision_to": "next_lower_band",
            }
        )
    return results
