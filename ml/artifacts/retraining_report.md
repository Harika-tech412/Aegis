# Aegis Retraining Report — Feedback Loop Demonstration

**What this is.** 200 simulated investigator confirmations
(130 CONFIRMED_FRAUD, 70 CONFIRMED_LEGITIMATE) drawn from the
train+val data where investigator attention actually lands: every
decision-time-uncertain fraud plus the least-confident held AUTO_FLAG cases
(11 of the fraud events came from HUMAN_REVIEW, the rest
from confirming flagged-and-held cases), and 70 genuinely ambiguous
HUMAN_REVIEW legitimate cases. Verdicts come from existing labels, standing in
for what investigators would confirm over weeks in production; the events are
saved in `simulated_feedback.json` for reproducibility. Feedback rows were
upweighted (sample_weight 2.0) and the model retrained with
**identical hyperparameters** — no tuning was performed on these results.

**Selection methodology note.** Candidate cases were identified by
**out-of-fold** scores (3-fold cross-fit), not the deployed model's in-sample
scores. The deployed model is near-perfectly confident on its own training
fraud — its in-sample review band contains zero fraud cases — whereas in
production every application is scored before anyone knows its label.
Out-of-fold scoring reproduces that decision-time uncertainty honestly.

**What was not touched.** The test split and the shifted-mix holdout set were
used exactly once each, below. Feedback selection never saw them.

## Test split (n=2,250) — original (v1) vs retrained (v2)

| metric | v1 | v2 | delta |
|---|---|---|---|
| PR-AUC | 0.9634 | 0.9643 | +0.0010 |
| ROC-AUC | 0.9964 | 0.9964 | +0.0000 |
| PRECISION | 0.914 | 0.868 | -0.0460 |
| RECALL | 0.946 | 0.938 | -0.0089 |
| F1 | 0.930 | 0.901 | -0.0285 |
| FPR | 0.0047 | 0.0075 | +0.0028 |

## Holdout (n=3,000, different fraud mix) — original vs retrained

| metric | v1 | v2 | delta |
|---|---|---|---|
| PR-AUC | 0.9717 | 0.9564 | -0.0153 |
| ROC-AUC | 0.9937 | 0.9951 | +0.0014 |
| PRECISION | 0.918 | 0.895 | -0.0227 |
| RECALL | 0.924 | 0.924 | +0.0000 |
| F1 | 0.921 | 0.909 | -0.0115 |
| FPR | 0.0046 | 0.0060 | +0.0014 |

## HUMAN_REVIEW cases on the test split

Of the 995 test cases the original model routed to
HUMAN_REVIEW, v1 misclassified 1 at the 0.5
threshold. The retrained model correctly reclassifies
**0** of those — and newly misclassifies
**0** that v1 had right. Both numbers are reported;
the net is what matters.

## Interpretation — reported as measured

The retrained model is **not better in aggregate**: PR-AUC is flat-to-slightly
up on test and down on holdout, and precision gives up more than recall gains.
That is the expected outcome here, and it is reported rather than tuned away.
The v1 model is already near ceiling on this synthetic data, and nearly all
simulated feedback *confirms decisions the model already made correctly* —
upweighting those rows sharpens the decision boundary around cases it had
right at the cost of slight overconfidence elsewhere. The feedback loop's
value in production comes when verdicts carry information the model does NOT
have: novel fraud patterns, false-positive corrections, drift. What this
demonstration establishes is the mechanics — capture, weighting, retraining,
honest evaluation on untouched splits, and versioned artifacts — so that when
disagreeing feedback arrives, the pipeline that learns from it already exists.

## Artifacts

- `xgboost_model_v2.json` — retrained model (the original `xgboost_model.json`
  is untouched; both are loadable side by side for the demo)
- `simulated_feedback.json` — the exact 200 events (seed 123)
