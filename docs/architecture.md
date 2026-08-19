# Aegis Architecture — TBD

## Decision Bands

**Status: specification only. Not implemented yet — this documents the target
for the scoring/decisioning layer so we build to it in the next step.**

Every scored application falls into one of three bands based on the model's
`risk_score` (0.0–1.0):

| Band | Condition | Action |
|---|---|---|
| `AUTO_APPROVE` | `risk_score < 0.10` | High-confidence legitimate. Proceeds without human involvement. |
| `HUMAN_REVIEW` | `0.10 <= risk_score <= 0.90` | Low confidence. Routed to the investigator queue with SHAP attributions, the free-text purpose check, and the ID-name check attached. |
| `AUTO_FLAG` | `risk_score > 0.90` | High-confidence fraud. Flagged and held for action. |

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

**The 0.10 and 0.90 values above are placeholders.** They were chosen to state
the shape of the policy, not because any evidence supports them yet. They must
be tuned once training produces real score distributions, using at minimum:

- The precision/recall curve on the holdout set at each candidate cutoff.
- Resulting `HUMAN_REVIEW` queue volume — the band is only useful if a real
  team could work it.
- Behaviour on the hard-legitimate cohort specifically, not just aggregate
  accuracy.
- Score calibration. If the model's probabilities are not calibrated, a
  "confidence" band built on raw scores is measuring the wrong thing, and
  calibration (Platt scaling or isotonic regression) has to come first.

Until that tuning happens, treat any band assignment produced by the system as
provisional.
