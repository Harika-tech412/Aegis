"""Train the Aegis fraud-risk ensemble end to end.

    python ml/train.py

Pipeline (tasks map to the project plan):
  1. Feature engineering via ml/features.py; spec frozen to artifacts.
  2. XGBoost with a small hyperparameter grid, selected on validation PR-AUC.
  3. IsolationForest unsupervised anomaly layer.
  4. Ensemble (0.7 * XGBoost probability + 0.3 * anomaly score), isotonic
     calibration fitted on the validation split.
  5. Decision-band thresholds tuned on validation to meet the architecture
     spec (AUTO_FLAG FPR <= 3%, AUTO_APPROVE missed-fraud <= 2%), plus the
     hard-legitimate stress test.
 10. Full report to ml/artifacts/model_report.md (includes the fraud-ring and
     Benford analyses from ml/graph_fraud.py / ml/benford.py).

Split discipline: applications_train.csv is split 70/15/15 (train/val/test,
stratified, seed 42). applications_holdout.csv is generated from a different
seed with a different fraud-archetype mix and is touched exactly once, at the
end, for the honest generalization number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))

import benford
import graph_fraud
from features import build_feature_matrix, save_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

SEED = 42
XGB_WEIGHT = 0.7
ANOMALY_WEIGHT = 0.3
AUTO_FLAG_MAX_FPR = 0.03
AUTO_APPROVE_MAX_MISSED_FRAUD = 0.02

PARAM_GRID = [
    {"max_depth": d, "n_estimators": n, "learning_rate": lr}
    for d in (3, 4, 6)
    for n in (200, 400)
    for lr in (0.05, 0.10)
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def metrics_at_half(y_true, scores) -> dict:
    """PR-AUC / ROC-AUC on the score, plus threshold metrics at 0.5."""
    pred = (np.asarray(scores) >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "pr_auc": average_precision_score(y_true, scores),
        "roc_auc": roc_auc_score(y_true, scores),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fp / (fp + tn) if (fp + tn) else 0.0,
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def normalize_anomaly(raw: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((raw - lo) / max(hi - lo, 1e-12), 0.0, 1.0)


def hard_legit_mask(df: pd.DataFrame) -> pd.Series:
    """Heuristic for the hard-legitimate cohort (no marker column exists by design)."""
    return (~df["is_fraud"]) & (
        (df["applications_from_device_last_24h"] >= 3)
        | (df["mouse_movement_events"] < 20)
        | (df["form_paste_count"] >= 5)
        | (df["identity_consistency_score"] < 0.4)
    )


def band_of(scores: np.ndarray, lo: float, hi: float) -> np.ndarray:
    bands = np.full(len(scores), "HUMAN_REVIEW", dtype=object)
    bands[scores < lo] = "AUTO_APPROVE"
    bands[scores > hi] = "AUTO_FLAG"
    return bands


def band_table(bands: np.ndarray) -> dict[str, float]:
    n = len(bands)
    return {b: float((bands == b).sum()) / n for b in ("AUTO_APPROVE", "HUMAN_REVIEW", "AUTO_FLAG")}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    # ---- Load and split ----------------------------------------------------
    df = pd.read_csv(DATA_DIR / "applications_train.csv")
    holdout_df = pd.read_csv(DATA_DIR / "applications_holdout.csv")

    X_all, feature_names, spec = build_feature_matrix(df)
    save_spec(spec)
    y_all = df["is_fraud"].astype(int).to_numpy()

    idx_train, idx_temp = train_test_split(
        np.arange(len(df)), test_size=0.30, stratify=y_all, random_state=SEED
    )
    idx_val, idx_test = train_test_split(
        idx_temp, test_size=0.50, stratify=y_all[idx_temp], random_state=SEED
    )

    X_train, y_train = X_all.iloc[idx_train], y_all[idx_train]
    X_val, y_val = X_all.iloc[idx_val], y_all[idx_val]
    X_test, y_test = X_all.iloc[idx_test], y_all[idx_test]
    X_holdout, _, _ = build_feature_matrix(holdout_df, spec)
    y_holdout = holdout_df["is_fraud"].astype(int).to_numpy()

    print(
        f"splits: train {len(idx_train):,} | val {len(idx_val):,} | "
        f"test {len(idx_test):,} | holdout {len(holdout_df):,}"
    )

    # ---- Task 2: XGBoost grid on train, selected on val PR-AUC --------------
    spw = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    print(f"scale_pos_weight = {spw:.1f}")

    results = []
    for params in PARAM_GRID:
        model = XGBClassifier(
            **params,
            scale_pos_weight=spw,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="aucpr",
            random_state=SEED,
            n_jobs=-1,
        )
        model.fit(X_train, y_train, verbose=False)
        pr = average_precision_score(y_val, model.predict_proba(X_val)[:, 1])
        results.append((pr, params, model))
        print(f"  {params} -> val PR-AUC {pr:.4f}")

    results.sort(key=lambda r: -r[0])
    best_pr, best_params, model_train_only = results[0]
    print(f"selected: {best_params} (val PR-AUC {best_pr:.4f})")

    val_proba = model_train_only.predict_proba(X_val)[:, 1]
    val_metrics = metrics_at_half(y_val, val_proba)

    # ---- Task 3: IsolationForest (unsupervised, fit on train split only) ----
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=SEED, n_jobs=-1)
    iso.fit(X_train)

    raw_train = -iso.score_samples(X_train)
    a_lo, a_hi = float(raw_train.min()), float(raw_train.max())

    def anomaly_score(X) -> np.ndarray:
        return normalize_anomaly(-iso.score_samples(X), a_lo, a_hi)

    # Signal check: fraud share among the top-5% most anomalous (val split).
    val_anom = anomaly_score(X_val)
    k = max(1, int(0.05 * len(val_anom)))
    top_idx = np.argsort(-val_anom)[:k]
    iso_capture = float(y_val[top_idx].mean())
    print(f"IsolationForest top-5% anomalies on val: {iso_capture:.1%} fraud (baseline {y_val.mean():.1%})")

    # ---- Task 4: ensemble + isotonic calibration on the val split -----------
    # Calibration MUST be fitted on data the XGBoost model never trained on,
    # which is why it is fitted here, with the train-only model, before the
    # final refit on train+val below.
    raw_val_ensemble = XGB_WEIGHT * val_proba + ANOMALY_WEIGHT * val_anom
    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    calibrator.fit(raw_val_ensemble, y_val)

    # ---- Task 5: decision-band thresholds on calibrated val scores ----------
    cal_val = calibrator.predict(raw_val_ensemble)
    candidates = np.unique(np.concatenate([[0.0, 1.0], cal_val]))

    legit_scores = cal_val[y_val == 0]
    fraud_scores = cal_val[y_val == 1]

    hi_options = [t for t in candidates if (legit_scores > t).mean() <= AUTO_FLAG_MAX_FPR]
    hi = float(min(hi_options)) if hi_options else 1.0
    lo_options = [t for t in candidates if (fraud_scores < t).mean() <= AUTO_APPROVE_MAX_MISSED_FRAUD]
    lo = float(max(lo_options)) if lo_options else 0.0
    lo = min(lo, hi)  # never let the bands cross

    print(f"decision bands (calibrated): AUTO_APPROVE < {lo:.4f} | AUTO_FLAG > {hi:.4f}")

    # ---- Final model: refit on train+val, evaluate once on test & holdout ---
    X_trval = pd.concat([X_train, X_val])
    y_trval = np.concatenate([y_train, y_val])
    spw_final = float((y_trval == 0).sum() / max((y_trval == 1).sum(), 1))
    final_model = XGBClassifier(
        **best_params,
        scale_pos_weight=spw_final,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="aucpr",
        random_state=SEED,
        n_jobs=-1,
    )
    final_model.fit(X_trval, y_trval, verbose=False)

    def pipeline_score(X) -> np.ndarray:
        raw = XGB_WEIGHT * final_model.predict_proba(X)[:, 1] + ANOMALY_WEIGHT * anomaly_score(X)
        return calibrator.predict(raw)

    test_scores = pipeline_score(X_test)
    holdout_scores = pipeline_score(X_holdout)
    test_metrics = metrics_at_half(y_test, test_scores)
    holdout_metrics = metrics_at_half(y_holdout, holdout_scores)

    xgb_test_auc = {
        "pr_auc": average_precision_score(y_test, final_model.predict_proba(X_test)[:, 1]),
        "roc_auc": roc_auc_score(y_test, final_model.predict_proba(X_test)[:, 1]),
    }
    xgb_holdout_auc = {
        "pr_auc": average_precision_score(y_holdout, final_model.predict_proba(X_holdout)[:, 1]),
        "roc_auc": roc_auc_score(y_holdout, final_model.predict_proba(X_holdout)[:, 1]),
    }

    # ---- Calibration table (on TEST - out of sample for the calibrator) -----
    bins = np.linspace(0.0, 1.0, 11)
    calibration_rows = []
    bin_ids = np.clip(np.digitize(test_scores, bins) - 1, 0, 9)
    for b in range(10):
        mask = bin_ids == b
        calibration_rows.append(
            {
                "bin": f"{bins[b]:.1f}-{bins[b + 1]:.1f}",
                "n": int(mask.sum()),
                "mean_predicted": float(test_scores[mask].mean()) if mask.any() else None,
                "actual_fraud_rate": float(y_test[mask].mean()) if mask.any() else None,
            }
        )

    # ---- Band populations + hard-legitimate stress test ----------------------
    test_bands = band_of(test_scores, lo, hi)
    holdout_bands = band_of(holdout_scores, lo, hi)

    def stress(df_split: pd.DataFrame, scores: np.ndarray) -> dict:
        mask = hard_legit_mask(df_split).to_numpy()
        bands = band_of(scores, lo, hi)[mask]
        n = int(mask.sum())
        return {
            "n": n,
            **{b: float((bands == b).sum()) / n if n else 0.0 for b in ("AUTO_APPROVE", "HUMAN_REVIEW", "AUTO_FLAG")},
        }

    stress_test = stress(df.iloc[idx_test].reset_index(drop=True), test_scores)
    stress_holdout = stress(holdout_df, holdout_scores)

    # Fraud capture inside AUTO_FLAG / leak into AUTO_APPROVE, for the report.
    def band_outcomes(y, bands) -> dict:
        return {
            "flag_precision": float(y[bands == "AUTO_FLAG"].mean()) if (bands == "AUTO_FLAG").any() else 0.0,
            "approve_miss_rate": float(y[bands == "AUTO_APPROVE"].mean()) if (bands == "AUTO_APPROVE").any() else 0.0,
            "review_share": float((bands == "HUMAN_REVIEW").mean()),
        }

    test_outcomes = band_outcomes(y_test, test_bands)
    holdout_outcomes = band_outcomes(y_holdout, holdout_bands)

    # ---- Tasks 8 & 9: ring + Benford analyses --------------------------------
    graph = graph_fraud.build_graph(df)
    ring_analysis = graph_fraud.analyse_rings(df, graph)
    graph_fraud.save_ring_lookup(df)

    benford_result = benford.compare_legit_vs_fraud(df)

    # ---- Feature importance ---------------------------------------------------
    gain = final_model.get_booster().get_score(importance_type="gain")
    importance = sorted(gain.items(), key=lambda kv: -kv[1])[:10]

    # ---- Save artifacts --------------------------------------------------------
    final_model.get_booster().save_model(str(ARTIFACTS_DIR / "xgboost_model.json"))
    joblib.dump(iso, ARTIFACTS_DIR / "isolation_forest.joblib")
    joblib.dump(calibrator, ARTIFACTS_DIR / "calibrator.joblib")
    (ARTIFACTS_DIR / "ensemble_config.json").write_text(
        json.dumps(
            {
                "xgb_weight": XGB_WEIGHT,
                "anomaly_weight": ANOMALY_WEIGHT,
                "anomaly_norm": {"min": a_lo, "max": a_hi},
                "bands": {"auto_approve_below": lo, "auto_flag_above": hi},
                "xgb_params": best_params,
                "scale_pos_weight_final": spw_final,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # ---- Report -----------------------------------------------------------------
    report = build_report(
        sizes=dict(train=len(idx_train), val=len(idx_val), test=len(idx_test), holdout=len(holdout_df)),
        best_params=best_params,
        spw=spw_final,
        val_metrics=val_metrics,
        test_metrics=test_metrics,
        holdout_metrics=holdout_metrics,
        xgb_test_auc=xgb_test_auc,
        xgb_holdout_auc=xgb_holdout_auc,
        iso_capture=iso_capture,
        val_baseline=float(y_val.mean()),
        calibration_rows=calibration_rows,
        lo=lo,
        hi=hi,
        test_band_share=band_table(test_bands),
        holdout_band_share=band_table(holdout_bands),
        test_outcomes=test_outcomes,
        holdout_outcomes=holdout_outcomes,
        stress_test=stress_test,
        stress_holdout=stress_holdout,
        ring_analysis=ring_analysis,
        benford_result=benford_result,
        importance=importance,
    )
    (ARTIFACTS_DIR / "model_report.md").write_text(report, encoding="utf-8")

    print("\nartifacts written to ml/artifacts/:")
    for p in sorted(ARTIFACTS_DIR.iterdir()):
        print(f"  {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
    print("\nfull report: ml/artifacts/model_report.md")


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

PLAIN_ENGLISH = {
    "applicant_age": "Applicant age",
    "annual_income": "Declared annual income",
    "requested_amount": "Requested loan amount",
    "session_duration_seconds": "How long the application session lasted",
    "mouse_movement_events": "Amount of mouse movement during the session",
    "form_paste_count": "How many form fields were pasted rather than typed",
    "applications_from_device_last_24h": "Applications from the same device in 24h",
    "applications_from_ip_last_24h": "Applications from the same IP in 24h",
    "income_employer_consistency_score": "Whether declared income fits the stated employer",
    "identity_consistency_score": "Whether name/address/phone records agree",
    "loan_to_income_ratio": "Requested amount as a share of income",
    "has_id_document": "Whether an ID document was uploaded",
}


def _plain(feature: str) -> str:
    if feature in PLAIN_ENGLISH:
        return PLAIN_ENGLISH[feature]
    if "=" in feature:
        col, val = feature.split("=", 1)
        return f"{col.replace('_', ' ').capitalize()} is '{val}'"
    return feature


def _metric_row(name, t, h, fmt="{:.4f}"):
    return f"| {name} | {fmt.format(t)} | {fmt.format(h)} |"


def build_report(**k) -> str:
    m_t, m_h = k["test_metrics"], k["holdout_metrics"]

    cal_lines = ["| bin | n | mean predicted | actual fraud rate |", "|---|---|---|---|"]
    for row in k["calibration_rows"]:
        pred = f"{row['mean_predicted']:.3f}" if row["mean_predicted"] is not None else "—"
        act = f"{row['actual_fraud_rate']:.3f}" if row["actual_fraud_rate"] is not None else "—"
        cal_lines.append(f"| {row['bin']} | {row['n']} | {pred} | {act} |")

    imp_lines = ["| rank | feature | meaning | gain |", "|---|---|---|---|"]
    for i, (feat, g) in enumerate(k["importance"], 1):
        imp_lines.append(f"| {i} | `{feat}` | {_plain(feat)} | {g:.1f} |")

    ring = k["ring_analysis"]
    ring_lift = ring["fraud_rate_in_rings_3plus"] / max(ring["baseline_fraud_rate"], 1e-9)
    ben_l, ben_f = k["benford_result"]["legitimate"], k["benford_result"]["fraud"]

    st, sh = k["stress_test"], k["stress_holdout"]

    return f"""# Aegis Model Report

All numbers below are measured on **synthetic data** (see `data/data_card.md`)
and describe performance on a simulation, not real-world fraud detection.

## 1. Data splits

| split | rows | source |
|---|---|---|
| train | {k['sizes']['train']:,} | applications_train.csv (70%, stratified, seed 42) |
| validation | {k['sizes']['val']:,} | applications_train.csv (15%) — model selection, calibration, thresholds |
| test | {k['sizes']['test']:,} | applications_train.csv (15%) — untouched until final evaluation |
| holdout | {k['sizes']['holdout']:,} | applications_holdout.csv — different seed **and** different fraud-archetype mix; touched exactly once |

## 2. Model

**XGBoost** selected on validation PR-AUC from a 12-point grid:
`max_depth={k['best_params']['max_depth']}`, `n_estimators={k['best_params']['n_estimators']}`,
`learning_rate={k['best_params']['learning_rate']}`, `scale_pos_weight={k['spw']:.1f}`,
`subsample=0.9`, `colsample_bytree=0.9`. Final model refit on train+val.

Validation (train-only model, raw probability, 0.5 threshold): PR-AUC {k['val_metrics']['pr_auc']:.4f},
ROC-AUC {k['val_metrics']['roc_auc']:.4f}, precision {k['val_metrics']['precision']:.3f},
recall {k['val_metrics']['recall']:.3f}, F1 {k['val_metrics']['f1']:.3f}.

**Ensemble:** calibrated( 0.7 × XGBoost probability + 0.3 × IsolationForest anomaly ),
isotonic calibration fitted on the validation split only.

## 3. Final evaluation — test vs holdout (calibrated ensemble)

| metric | test | holdout |
|---|---|---|
{_metric_row('PR-AUC', m_t['pr_auc'], m_h['pr_auc'])}
{_metric_row('ROC-AUC', m_t['roc_auc'], m_h['roc_auc'])}
{_metric_row('precision @0.5', m_t['precision'], m_h['precision'], '{:.3f}')}
{_metric_row('recall @0.5', m_t['recall'], m_h['recall'], '{:.3f}')}
{_metric_row('F1 @0.5', m_t['f1'], m_h['f1'], '{:.3f}')}
{_metric_row('FPR @0.5', m_t['fpr'], m_h['fpr'], '{:.4f}')}

XGBoost probability alone: test PR-AUC {k['xgb_test_auc']['pr_auc']:.4f} / ROC-AUC {k['xgb_test_auc']['roc_auc']:.4f};
holdout PR-AUC {k['xgb_holdout_auc']['pr_auc']:.4f} / ROC-AUC {k['xgb_holdout_auc']['roc_auc']:.4f}.

Confusion (test, 0.5): TP {m_t['confusion']['tp']} FP {m_t['confusion']['fp']} FN {m_t['confusion']['fn']} TN {m_t['confusion']['tn']}.
Confusion (holdout, 0.5): TP {m_h['confusion']['tp']} FP {m_h['confusion']['fp']} FN {m_h['confusion']['fn']} TN {m_h['confusion']['tn']}.

The gap between the test and holdout columns is the honest generalization
cost of the deliberately shifted archetype mix in the holdout set.

## 4. IsolationForest anomaly layer

Fit unsupervised on the training split (labels never seen). Among the top-5%
most anomalous validation applications, **{k['iso_capture']:.1%} are fraud** against a
{k['val_baseline']:.1%} baseline — the unsupervised layer concentrates fraud
{k['iso_capture'] / max(k['val_baseline'], 1e-9):.0f}× over base rate on its own.

## 5. Calibration (test split, out of sample)

{chr(10).join(cal_lines)}

A calibrated score of ~0.8 should sit in a bin whose actual fraud rate is
~0.8. Sparse high bins reflect the 5% base rate: few applications score high.

## 6. Decision bands (tuned on validation)

| band | rule | test share | holdout share |
|---|---|---|---|
| AUTO_APPROVE | score < **{k['lo']:.4f}** | {k['test_band_share']['AUTO_APPROVE']:.1%} | {k['holdout_band_share']['AUTO_APPROVE']:.1%} |
| HUMAN_REVIEW | between | {k['test_band_share']['HUMAN_REVIEW']:.1%} | {k['holdout_band_share']['HUMAN_REVIEW']:.1%} |
| AUTO_FLAG | score > **{k['hi']:.4f}** | {k['test_band_share']['AUTO_FLAG']:.1%} | {k['holdout_band_share']['AUTO_FLAG']:.1%} |

Chosen on the validation split as: the smallest AUTO_FLAG cutoff keeping the
legitimate-applications false-positive rate ≤ {AUTO_FLAG_MAX_FPR:.0%}, and the largest
AUTO_APPROVE cutoff keeping missed fraud in the approve band ≤ {AUTO_APPROVE_MAX_MISSED_FRAUD:.0%}.

Outcomes: AUTO_FLAG precision (share of flagged that are truly fraud) —
test {k['test_outcomes']['flag_precision']:.1%}, holdout {k['holdout_outcomes']['flag_precision']:.1%}.
Fraud rate inside AUTO_APPROVE — test {k['test_outcomes']['approve_miss_rate']:.2%},
holdout {k['holdout_outcomes']['approve_miss_rate']:.2%}.

### Hard-legitimate stress test

Cohort: `is_fraud = False` AND (device velocity ≥ 3 OR mouse events < 20 OR
paste count ≥ 5 OR identity consistency < 0.4) — the family-device /
accessibility-tool / autofill / thin-file customers built into the data.

| | n | AUTO_APPROVE | HUMAN_REVIEW | AUTO_FLAG |
|---|---|---|---|---|
| test | {st['n']} | {st['AUTO_APPROVE']:.1%} | {st['HUMAN_REVIEW']:.1%} | {st['AUTO_FLAG']:.1%} |
| holdout | {sh['n']} | {sh['AUTO_APPROVE']:.1%} | {sh['HUMAN_REVIEW']:.1%} | {sh['AUTO_FLAG']:.1%} |

The design intent is that these customers land in AUTO_APPROVE or
HUMAN_REVIEW — the AUTO_FLAG column is the miscalibration cost, reported
plainly whatever it is.

## 7. Fraud-ring graph signal

Applications sharing a `device_id` or `ip_hash` form {ring['n_rings']:,} connected
components of size ≥ 2 ({ring['n_rings_3plus']:,} of size ≥ 3; largest {ring['largest_ring']}).

| | fraud rate |
|---|---|
| applications in rings of size ≥ 3 ({ring['apps_in_rings_3plus']:,} apps) | **{ring['fraud_rate_in_rings_3plus']:.1%}** |
| overall baseline | {ring['baseline_fraud_rate']:.1%} |

Ring membership alone carries a **{ring_lift:.1f}× lift** over base rate. This signal
is served by the graph module (`ml/graph_fraud.py` + `ring_lookup.json`), not
the tabular model — device/IP identifiers are deliberately kept out of the
feature matrix.

## 8. Benford's Law — declared incomes

Distance from Benford's expected leading-digit distribution:

| population | n | chi-square (raw) | chi²/n (sample-size fair) |
|---|---|---|---|
| legitimate incomes | {ben_l['n']:,} | {ben_l['chi_square']:.1f} | {ben_l['divergence_per_obs']:.4f} |
| fraud incomes | {ben_f['n']:,} | {ben_f['chi_square']:.1f} | {ben_f['divergence_per_obs']:.4f} |

Raw chi-square grows linearly with sample size, so with a 19× difference in n
the raw column is not a fair comparison — the per-observation divergence is.
By that measure, fraudulent incomes deviate
**{ben_f['divergence_per_obs'] / max(ben_l['divergence_per_obs'], 1e-9):.1f}×** more from Benford than legitimate ones.

One caveat stated plainly: the synthetic incomes are clipped log-normal
spanning barely one order of magnitude, so *neither* population truly follows
Benford (both chi-squares are significant). The meaningful finding is the
relative gap, not absolute conformance. Supplementary population-level
evidence for the demo — not a per-application model feature (one application
has one leading digit).

## 9. Top 10 features by XGBoost gain

{chr(10).join(imp_lines)}
"""


if __name__ == "__main__":
    main()
