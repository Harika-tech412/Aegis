"""Benford's Law check on declared incomes.

Benford's Law predicts the leading-digit distribution of naturally occurring
multi-magnitude quantities: digit d appears with frequency log10(1 + 1/d).
Fabricated numbers - invented incomes typed by a fraudster - tend to deviate
from it more than organically generated ones.

This is a supplementary, population-level signal for the report and demo. It
is deliberately NOT a per-application model feature: a single application has
one leading digit, which carries no distributional information.

Run standalone for the comparison on the training data:

    python ml/benford.py
"""

from __future__ import annotations

import numpy as np
from scipy import stats

BENFORD_EXPECTED = np.array([np.log10(1 + 1 / d) for d in range(1, 10)])


def leading_digits(values) -> np.ndarray:
    """First significant digit (1-9) of each strictly positive value."""
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    # Shift each value into [1, 10) by dividing out its magnitude.
    magnitudes = np.floor(np.log10(arr))
    return np.floor(arr / 10.0**magnitudes).astype(int)


def benford_analysis(values) -> dict:
    """Observed vs Benford-expected leading-digit distribution + chi-square GOF."""
    digits = leading_digits(values)
    n = len(digits)
    if n == 0:
        raise ValueError("no positive finite values to analyse")

    observed_counts = np.array([(digits == d).sum() for d in range(1, 10)], dtype=np.float64)
    expected_counts = BENFORD_EXPECTED * n

    chi_square = float(((observed_counts - expected_counts) ** 2 / expected_counts).sum())
    p_value = float(stats.chi2.sf(chi_square, df=8))

    return {
        "n": n,
        "observed_freq": (observed_counts / n).round(4).tolist(),
        "expected_freq": BENFORD_EXPECTED.round(4).tolist(),
        "chi_square": round(chi_square, 2),
        # Chi-square grows linearly with sample size, so raw values from two
        # populations of very different n are not comparable. This is the
        # per-observation divergence (chi-square / n) - the fair comparison.
        "divergence_per_obs": round(chi_square / n, 5),
        "p_value": p_value,
    }


def compare_legit_vs_fraud(df) -> dict:
    """Run the Benford check separately on legitimate and fraudulent incomes."""
    legit = benford_analysis(df.loc[~df["is_fraud"], "annual_income"])
    fraud = benford_analysis(df.loc[df["is_fraud"], "annual_income"])
    return {"legitimate": legit, "fraud": fraud}


def format_comparison(result: dict) -> str:
    legit, fraud = result["legitimate"], result["fraud"]
    lines = [
        f"{'digit':>5} | {'Benford':>8} | {'legit obs':>9} | {'fraud obs':>9}",
        "-" * 42,
    ]
    for i, d in enumerate(range(1, 10)):
        lines.append(
            f"{d:>5} | {legit['expected_freq'][i]:>8.4f} | "
            f"{legit['observed_freq'][i]:>9.4f} | {fraud['observed_freq'][i]:>9.4f}"
        )
    lines.append("")
    lines.append(
        f"chi-square vs Benford:  legitimate {legit['chi_square']:.1f} "
        f"(n={legit['n']:,})  |  fraud {fraud['chi_square']:.1f} (n={fraud['n']:,})"
    )
    lines.append(
        f"per-observation divergence (chi2/n, sample-size fair): "
        f"legitimate {legit['divergence_per_obs']:.4f} | fraud {fraud['divergence_per_obs']:.4f}"
    )
    ratio = fraud["divergence_per_obs"] / max(legit["divergence_per_obs"], 1e-9)
    lines.append(f"fraud incomes deviate {ratio:.1f}x more per observation than legitimate incomes")
    return "\n".join(lines)


if __name__ == "__main__":
    import pandas as pd
    from pathlib import Path

    df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "applications_train.csv")
    print(format_comparison(compare_legit_vs_fraud(df)))
