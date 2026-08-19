# Aegis Architecture — TBD

## Decision Bands

**Status: implemented and tuned.** Thresholds below are the actual values
produced by `ml/train.py` on the validation split and stored in
`ml/artifacts/ensemble_config.json`; the placeholder 0.10/0.90 values from the
original spec are superseded.

Every scored application falls into one of three bands based on the
**calibrated** ensemble `risk_score` (0.0–1.0):

| Band | Condition | Action |
|---|---|---|
| `AUTO_APPROVE` | `risk_score < 0.0022` | High-confidence legitimate. Proceeds without human involvement. |
| `HUMAN_REVIEW` | `0.0022 <= risk_score <= 0.0488` band and everything between | Low confidence. Routed to the investigator queue with SHAP attributions, the free-text purpose check, and the ID-name check attached. |
| `AUTO_FLAG` | `risk_score > 0.0488` | High-confidence fraud. Flagged and held for action. |

**How these were chosen.** On the validation split (never used for model
fitting of the final evaluation), we selected the smallest AUTO_FLAG cutoff
that keeps the false-positive rate on legitimate applications at or under 3%,
and the largest AUTO_APPROVE cutoff that keeps missed fraud inside the
approve band at or under 2%. The numbers look small because the isotonic
calibrator maps the score distribution honestly: 95% of traffic is legitimate
and concentrates near zero, so "more than ~5% calibrated fraud probability"
is already an unusual application. On the untouched test split this yields
AUTO_APPROVE 48.7% / HUMAN_REVIEW 44.2% / AUTO_FLAG 7.1% of traffic, with
69.4% of AUTO_FLAG being true fraud and 0.00% fraud inside AUTO_APPROVE
(holdout: 49.3% / 43.4% / 7.3%, flag precision 70.3%, approve leak 0.07%).
Full derivation and the hard-legitimate stress test are in
`ml/artifacts/model_report.md` §6.

### Why three bands and not a single threshold

A single cutoff answers "how risky is this?" A three-way band answers "how
*sure* is the model?" — and that distinction is the whole human-in-the-loop
story.

The system escalates to a human **when it is uncertain, not merely when risk is
moderate**. A 0.55 score is not "somewhat fraudulent"; it is the model saying it
cannot tell. That is precisely the case where a human investigator adds value,
and precisely the case where an automated decision would be least defensible to
a regulator, an auditor, or a declined applicant.

The two automated bands are deliberately narrow. They exist to keep the review
queue tractable, not to maximise automation rate. Widening them trades away the
system's main safety property, so any future tuning should treat queue volume
as the constraint and confidence as the objective — not the other way round.

The hard-legitimate cases in the synthetic dataset (see §6 of
`data/data_card.md`) are the intended stress test for this design: genuine
customers who trip one or two fraud-shaped signals should land in
`HUMAN_REVIEW` and be cleared there, **not** in `AUTO_FLAG`. A model that
pushes family-device or accessibility-tool users past 0.90 is miscalibrated
regardless of its headline accuracy.

### Threshold status

Tuned as described above. The checks the original spec demanded were run and
are reported in `ml/artifacts/model_report.md`:

- **Calibration first** — the score is isotonic-calibrated on validation
  before thresholds are chosen; the out-of-sample calibration table (test
  split) is in report §5.
- **Queue volume** — HUMAN_REVIEW receives ~44% of traffic. That is high for
  a production team and is an accepted trade for the demo: the synthetic data
  is deliberately seeded with ambiguous cases, and the review queue is the
  product surface being demonstrated.
- **Hard-legitimate cohort** — the honesty check is reported in §6 of the
  model report: on test, 9.4% of hard-legitimate customers land in
  AUTO_APPROVE, 65.6% in HUMAN_REVIEW, and 25.0% in AUTO_FLAG. That last
  number is the real miscalibration cost of the current thresholds and is
  reported unvarnished; the mitigation is that AUTO_FLAG holds for action
  rather than auto-declining, so a human still sees these before any adverse
  outcome.

One known limitation, stated plainly: the calibrator is fitted on validation
scores from the pre-refit model (the final model is then retrained on
train+val). Refitting calibration on data the final model has seen would bias
it, so we accept the small model-drift instead and verify the result on the
untouched test split — where the calibration table confirms the mapping holds.
