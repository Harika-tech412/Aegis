# Aegis Model Report

All numbers below are measured on **synthetic data** (see `data/data_card.md`)
and describe performance on a simulation, not real-world fraud detection.

## 1. Data splits

| split | rows | source |
|---|---|---|
| train | 10,500 | applications_train.csv (70%, stratified, seed 42) |
| validation | 2,250 | applications_train.csv (15%) — model selection, calibration, thresholds |
| test | 2,250 | applications_train.csv (15%) — untouched until final evaluation |
| holdout | 3,000 | applications_holdout.csv — different seed **and** different fraud-archetype mix; touched exactly once |

## 2. Model

**XGBoost** selected on validation PR-AUC from a 12-point grid:
`max_depth=4`, `n_estimators=200`,
`learning_rate=0.05`, `scale_pos_weight=19.0`,
`subsample=0.9`, `colsample_bytree=0.9`. Final model refit on train+val.

Validation (train-only model, raw probability, 0.5 threshold): PR-AUC 0.9666,
ROC-AUC 0.9965, precision 0.904,
recall 0.920, F1 0.912.

**Ensemble:** calibrated( 0.7 × XGBoost probability + 0.3 × IsolationForest anomaly ),
isotonic calibration fitted on the validation split only.

## 3. Final evaluation — test vs holdout (calibrated ensemble)

| metric | test | holdout |
|---|---|---|
| PR-AUC | 0.9634 | 0.9717 |
| ROC-AUC | 0.9964 | 0.9937 |
| precision @0.5 | 0.914 | 0.918 |
| recall @0.5 | 0.946 | 0.924 |
| F1 @0.5 | 0.930 | 0.921 |
| FPR @0.5 | 0.0047 | 0.0046 |

XGBoost probability alone: test PR-AUC 0.9750 / ROC-AUC 0.9985;
holdout PR-AUC 0.9802 / ROC-AUC 0.9981.

Confusion (test, 0.5): TP 106 FP 10 FN 6 TN 2128.
Confusion (holdout, 0.5): TP 145 FP 13 FN 12 TN 2830.

The gap between the test and holdout columns is the honest generalization
cost of the deliberately shifted archetype mix in the holdout set.

## 4. IsolationForest anomaly layer

Fit unsupervised on the training split (labels never seen). Among the top-5%
most anomalous validation applications, **52.7% are fraud** against a
5.0% baseline — the unsupervised layer concentrates fraud
10× over base rate on its own.

## 5. Calibration (test split, out of sample)

| bin | n | mean predicted | actual fraud rate |
|---|---|---|---|
| 0.0-0.1 | 2091 | 0.002 | 0.000 |
| 0.1-0.2 | 40 | 0.125 | 0.125 |
| 0.2-0.3 | 1 | 0.255 | 0.000 |
| 0.3-0.4 | 1 | 0.384 | 0.000 |
| 0.4-0.5 | 1 | 0.455 | 0.000 |
| 0.5-0.6 | 11 | 0.567 | 0.636 |
| 0.6-0.7 | 1 | 0.615 | 0.000 |
| 0.7-0.8 | 0 | — | — |
| 0.8-0.9 | 8 | 0.816 | 0.625 |
| 0.9-1.0 | 96 | 0.987 | 0.979 |

A calibrated score of ~0.8 should sit in a bin whose actual fraud rate is
~0.8. Sparse high bins reflect the 5% base rate: few applications score high.

## 6. Decision bands (tuned on validation)

| band | rule | test share | holdout share |
|---|---|---|---|
| AUTO_APPROVE | score < **0.0022** | 48.7% | 49.3% |
| HUMAN_REVIEW | between | 44.2% | 43.4% |
| AUTO_FLAG | score > **0.0488** | 7.1% | 7.3% |

Chosen on the validation split as: the smallest AUTO_FLAG cutoff keeping the
legitimate-applications false-positive rate ≤ 3%, and the largest
AUTO_APPROVE cutoff keeping missed fraud in the approve band ≤ 2%.

Outcomes: AUTO_FLAG precision (share of flagged that are truly fraud) —
test 69.4%, holdout 70.3%.
Fraud rate inside AUTO_APPROVE — test 0.00%,
holdout 0.07%.

### Hard-legitimate stress test

Cohort: `is_fraud = False` AND (device velocity ≥ 3 OR mouse events < 20 OR
paste count ≥ 5 OR identity consistency < 0.4) — the family-device /
accessibility-tool / autofill / thin-file customers built into the data.

| | n | AUTO_APPROVE | HUMAN_REVIEW | AUTO_FLAG |
|---|---|---|---|---|
| test | 96 | 9.4% | 65.6% | 25.0% |
| holdout | 124 | 5.6% | 69.4% | 25.0% |

The design intent is that these customers land in AUTO_APPROVE or
HUMAN_REVIEW — the AUTO_FLAG column is the miscalibration cost, reported
plainly whatever it is.

## 7. Fraud-ring graph signal

Applications sharing a `device_id` or `ip_hash` form 173 connected
components of size ≥ 2 (134 of size ≥ 3; largest 9).

| | fraud rate |
|---|---|
| applications in rings of size ≥ 3 (609 apps) | **57.8%** |
| overall baseline | 5.0% |

Ring membership alone carries a **11.6× lift** over base rate. This signal
is served by the graph module (`ml/graph_fraud.py` + `ring_lookup.json`), not
the tabular model — device/IP identifiers are deliberately kept out of the
feature matrix.

## 8. Benford's Law — declared incomes

Distance from Benford's expected leading-digit distribution:

| population | n | chi-square (raw) | chi²/n (sample-size fair) |
|---|---|---|---|
| legitimate incomes | 14,250 | 1762.1 | 0.1237 |
| fraud incomes | 750 | 164.3 | 0.2191 |

Raw chi-square grows linearly with sample size, so with a 19× difference in n
the raw column is not a fair comparison — the per-observation divergence is.
By that measure, fraudulent incomes deviate
**1.8×** more from Benford than legitimate ones.

One caveat stated plainly: the synthetic incomes are clipped log-normal
spanning barely one order of magnitude, so *neither* population truly follows
Benford (both chi-squares are significant). The meaningful finding is the
relative gap, not absolute conformance. Supplementary population-level
evidence for the demo — not a per-application model feature (one application
has one leading digit).

## 9. Top 10 features by XGBoost gain

| rank | feature | meaning | gain |
|---|---|---|---|
| 1 | `identity_consistency_score` | Whether name/address/phone records agree | 251.2 |
| 2 | `form_paste_count` | How many form fields were pasted rather than typed | 185.7 |
| 3 | `income_employer_consistency_score` | Whether declared income fits the stated employer | 160.5 |
| 4 | `applications_from_ip_last_24h` | Applications from the same IP in 24h | 136.3 |
| 5 | `mouse_movement_events` | Amount of mouse movement during the session | 71.3 |
| 6 | `requested_amount` | Requested loan amount | 41.6 |
| 7 | `session_duration_seconds` | How long the application session lasted | 40.3 |
| 8 | `applications_from_device_last_24h` | Applications from the same device in 24h | 38.2 |
| 9 | `employment_type=salaried` | Employment type is 'salaried' | 20.8 |
| 10 | `annual_income` | Declared annual income | 16.2 |
