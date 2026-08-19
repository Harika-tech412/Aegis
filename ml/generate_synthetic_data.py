"""Generate the synthetic digital-lending application datasets used by Aegis.

Everything produced here is 100% synthetic and programmatically generated with
NumPy/Pandas so the statistical properties are controlled and reproducible.
No LLM is involved in producing this tabular data, and no real applicant,
account, institution, or behavioral record is used, sampled, or approximated.

Run standalone:

    python ml/generate_synthetic_data.py

Outputs:
    data/applications_train.csv     15,000 rows, seed 42
    data/applications_holdout.csv    3,000 rows, seed 99 (different archetype mix)
    data/data_card.md               methodology + schema + measured class balance

Fairness note: the schema deliberately contains no protected or sensitive
attributes (no gender, race, ethnicity, religion, disability status, marital
status, national origin, or ZIP-code-level geography). `applicant_age` is
present only as a mild behavioral covariate with no engineered relationship to
the label, and is never used to encode a proxy for a protected characteristic.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

TRAIN_SEED = 42
HOLDOUT_SEED = 99
EMPLOYER_POOL_SEED = 7

TRAIN_ROWS = 15_000
HOLDOUT_ROWS = 3_000

# Fixed 90-day observation window. Hard-coded (rather than "now") so that
# re-running the generator reproduces identical output.
WINDOW_END = datetime(2026, 8, 1, 0, 0, 0)
WINDOW_DAYS = 90
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS)

# Nominal fraud rate. The realised rate emerges from random ring sizes and
# per-archetype jitter, so it lands near but not exactly on this number.
BASE_FRAUD_RATE = 0.05
HARD_LEGIT_RATE = 0.05

EMPLOYMENT_TYPES = ["salaried", "self_employed", "gig_worker", "unemployed"]
EMPLOYMENT_WEIGHTS = [0.62, 0.18, 0.15, 0.05]

LOAN_PURPOSES = [
    "debt_consolidation",
    "home_improvement",
    "medical",
    "education",
    "business",
    "other",
]
LOAN_PURPOSE_WEIGHTS = [0.31, 0.19, 0.14, 0.12, 0.13, 0.11]

FRAUD_TYPES = [
    "device_recycling",
    "velocity_attack",
    "session_anomaly",
    "income_mismatch",
    "identity_inconsistency",
]

# Train and holdout use different archetype mixes on purpose: a model that has
# only memorised the training mix should visibly degrade on the holdout.
TRAIN_ARCHETYPE_MIX = {
    "device_recycling": 0.26,
    "velocity_attack": 0.20,
    "session_anomaly": 0.22,
    "income_mismatch": 0.16,
    "identity_inconsistency": 0.16,
}
HOLDOUT_ARCHETYPE_MIX = {
    "device_recycling": 0.17,
    "velocity_attack": 0.15,
    "session_anomaly": 0.31,
    "income_mismatch": 0.21,
    "identity_inconsistency": 0.16,
}

HARD_LEGIT_FLAVORS = ["family_device", "accessibility_tool", "autofill_manager", "thin_file"]
HARD_LEGIT_WEIGHTS = [0.30, 0.24, 0.26, 0.20]

# Applications cluster in waking hours, peaking mid-morning and mid-evening.
HOUR_WEIGHTS = np.array(
    [0.6, 0.4, 0.3, 0.3, 0.4, 0.7, 1.2, 2.0, 3.0, 5.5, 6.0, 6.2,
     5.8, 5.0, 5.6, 5.8, 5.5, 5.2, 5.6, 6.0, 5.4, 4.2, 2.6, 1.5]
)
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

COLUMNS = [
    "application_id",
    "timestamp",
    "applicant_age",
    "annual_income",
    "employment_type",
    "employer_name",
    "requested_amount",
    "loan_purpose",
    "device_id",
    "ip_hash",
    "session_duration_seconds",
    "mouse_movement_events",
    "form_paste_count",
    "applications_from_device_last_24h",
    "applications_from_ip_last_24h",
    "income_employer_consistency_score",
    "identity_consistency_score",
    "is_fraud",
    "fraud_type",
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _hash_token(label: str) -> str:
    """Stable 16-hex-char pseudonymous token (device / IP surrogate)."""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:16]


def build_employer_pool(size: int = 50) -> list[str]:
    fake = Faker("en_US")
    Faker.seed(EMPLOYER_POOL_SEED)
    pool: list[str] = []
    while len(pool) < size:
        name = fake.company()
        if name not in pool:
            pool.append(name)
    return pool


def _sample_timestamps(rng: np.random.Generator, n: int) -> np.ndarray:
    days = rng.integers(0, WINDOW_DAYS, n)
    hours = rng.choice(24, size=n, p=HOUR_WEIGHTS)
    minutes = rng.integers(0, 60, n)
    seconds = rng.integers(0, 60, n)
    base = np.datetime64(WINDOW_START, "s").astype("int64")
    epoch = base + days * 86_400 + hours * 3_600 + minutes * 60 + seconds
    return epoch.astype("datetime64[s]")


def _random_anchor(rng: np.random.Generator, span_hours: float) -> np.datetime64:
    """Pick a window start such that a burst of `span_hours` still fits inside."""
    max_offset = WINDOW_DAYS * 86_400 - int(span_hours * 3_600) - 60
    offset = int(rng.integers(0, max(max_offset, 1)))
    return np.datetime64(WINDOW_START, "s") + np.timedelta64(offset, "s")


def _rolling_24h_counts(df: pd.DataFrame, key_col: str) -> np.ndarray:
    """For each row: how many applications shared `key_col` in the prior 24h.

    Counts are inclusive of the row itself, so a never-reused device scores 1.
    """
    counts = np.ones(len(df), dtype=np.int64)
    ts = df["timestamp"].to_numpy().astype("datetime64[s]").astype(np.int64)
    for _, positions in df.groupby(key_col, sort=False).indices.items():
        if len(positions) == 1:
            continue
        ordered = positions[np.argsort(ts[positions], kind="stable")]
        t = ts[ordered]
        left = np.searchsorted(t, t - 86_400, side="left")
        counts[ordered] = np.arange(len(t)) - left + 1
    return counts


# --------------------------------------------------------------------------
# Base (legitimate) population
# --------------------------------------------------------------------------


def _base_population(
    rng: np.random.Generator, n: int, tag: str, employers: list[str]
) -> pd.DataFrame:
    employment = rng.choice(EMPLOYMENT_TYPES, size=n, p=EMPLOYMENT_WEIGHTS)

    age = np.clip(rng.normal(35.0, 11.0, n), 18, 75).round().astype(np.int64)

    income = rng.lognormal(mean=np.log(48_000), sigma=0.55, size=n)
    income_mult = np.select(
        [employment == "unemployed", employment == "gig_worker", employment == "self_employed"],
        [0.34, 0.70, 1.16],
        default=1.0,
    )
    income = np.clip(income * income_mult, 15_000, 250_000).round(2)

    employer_idx = rng.integers(0, len(employers), n)
    employer_name = np.array([employers[i] for i in employer_idx], dtype=object)
    employer_name[employment == "unemployed"] = "NOT_EMPLOYED"

    ratio = rng.uniform(0.06, 0.45, n) * rng.lognormal(0.0, 0.25, n)
    requested = np.clip(income * ratio, 1_000, 50_000)
    requested = (requested / 100.0).round() * 100

    purpose = rng.choice(LOAN_PURPOSES, size=n, p=LOAN_PURPOSE_WEIGHTS)

    device_id = np.array([_hash_token(f"{tag}|device|{i}") for i in range(n)], dtype=object)
    ip_hash = np.array([_hash_token(f"{tag}|ip|{i}") for i in range(n)], dtype=object)

    session = np.clip(rng.normal(185.0, 65.0, n), 25, 900).round().astype(np.int64)
    mouse = np.clip(rng.normal(168.0, 55.0, n), 50, 300).round().astype(np.int64)
    paste = np.clip(rng.poisson(0.7, n), 0, 3).astype(np.int64)

    income_consistency = np.clip(rng.beta(6.5, 2.2, n), 0.05, 0.99).round(3)
    identity_consistency = np.clip(rng.beta(7.0, 2.0, n), 0.05, 0.99).round(3)

    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(_sample_timestamps(rng, n)),
            "applicant_age": age,
            "annual_income": income,
            "employment_type": employment,
            "employer_name": employer_name,
            "requested_amount": requested,
            "loan_purpose": purpose,
            "device_id": device_id,
            "ip_hash": ip_hash,
            "session_duration_seconds": session,
            "mouse_movement_events": mouse,
            "form_paste_count": paste,
            "income_employer_consistency_score": income_consistency,
            "identity_consistency_score": identity_consistency,
            "is_fraud": False,
            "fraud_type": pd.Series([None] * n, dtype=object),
        }
    )


class _IndexPool:
    """Hands out disjoint row indices so archetypes never overwrite each other."""

    def __init__(self, n: int, rng: np.random.Generator) -> None:
        self._pool: list[int] = [int(i) for i in rng.permutation(n)]

    def take(self, k: int) -> list[int]:
        k = max(0, min(k, len(self._pool)))
        out = self._pool[:k]
        del self._pool[:k]
        return out

    def __len__(self) -> int:
        return len(self._pool)


# --------------------------------------------------------------------------
# Fraud archetypes
# --------------------------------------------------------------------------


def _mark_fraud(df: pd.DataFrame, idx: list[int], fraud_type: str) -> None:
    df.loc[idx, "is_fraud"] = True
    df.loc[idx, "fraud_type"] = fraud_type


def _inject_device_recycling(df, rng, pool, target, tag) -> int:
    """Same device_id + ip_hash across 3-8 applications inside a 24-48h window."""
    made = 0
    ring = 0
    while made < target and len(pool) >= 8:
        size = int(rng.integers(3, 9))
        idx = pool.take(size)
        span_hours = float(rng.uniform(24, 48))
        anchor = _random_anchor(rng, span_hours)
        offsets = np.sort(rng.uniform(0, span_hours * 3_600, size)).astype(np.int64)
        df.loc[idx, "timestamp"] = pd.to_datetime(anchor + offsets.astype("timedelta64[s]"))
        df.loc[idx, "device_id"] = _hash_token(f"{tag}|ring-device|{ring}")
        df.loc[idx, "ip_hash"] = _hash_token(f"{tag}|ring-ip|{ring}")

        # Mostly fraud; the occasional member is a genuine shared-household user.
        is_bad = rng.random(size) < 0.85
        is_bad[0] = True
        bad = [i for i, flag in zip(idx, is_bad) if flag]
        good = [i for i, flag in zip(idx, is_bad) if not flag]

        _mark_fraud(df, bad, "device_recycling")
        # Secondary signal bleed: rings are usually operated at speed.
        df.loc[bad, "session_duration_seconds"] = (
            np.clip(rng.normal(95, 35, len(bad)), 20, 400).round().astype(np.int64)
        )
        df.loc[bad, "mouse_movement_events"] = (
            np.clip(rng.normal(85, 40, len(bad)), 5, 260).round().astype(np.int64)
        )
        df.loc[bad, "form_paste_count"] = np.clip(rng.poisson(2.4, len(bad)), 0, 9).astype(np.int64)
        df.loc[bad, "identity_consistency_score"] = (
            np.clip(rng.beta(3.0, 3.4, len(bad)), 0.05, 0.99).round(3)
        )
        if good:
            df.loc[good, "form_paste_count"] = np.clip(rng.poisson(1.0, len(good)), 0, 4).astype(np.int64)

        made += len(bad)
        ring += 1
    return made


def _inject_velocity_attack(df, rng, pool, target, employers, tag) -> int:
    """4-9 near-identical applications from one IP inside a 1-3h burst."""
    made = 0
    burst = 0
    while made < target and len(pool) >= 9:
        size = int(rng.integers(4, 10))
        idx = pool.take(size)
        span_hours = float(rng.uniform(1, 3))
        anchor = _random_anchor(rng, span_hours)
        offsets = np.sort(rng.uniform(0, span_hours * 3_600, size)).astype(np.int64)
        df.loc[idx, "timestamp"] = pd.to_datetime(anchor + offsets.astype("timedelta64[s]"))

        # One IP, but rotating device fingerprints - the tell is the burst rate.
        df.loc[idx, "ip_hash"] = _hash_token(f"{tag}|burst-ip|{burst}")
        df.loc[idx, "device_id"] = [
            _hash_token(f"{tag}|burst-device|{burst}|{k}") for k in range(size)
        ]

        # Identity-adjacent: one profile skeleton reused with small jitter.
        anchor_age = int(np.clip(rng.normal(33, 8), 21, 62))
        anchor_income = float(np.clip(rng.lognormal(np.log(56_000), 0.3), 20_000, 190_000))
        anchor_employer = employers[int(rng.integers(0, len(employers)))]
        df.loc[idx, "applicant_age"] = (
            np.clip(anchor_age + rng.integers(-2, 3, size), 18, 75).astype(np.int64)
        )
        df.loc[idx, "annual_income"] = (anchor_income * rng.uniform(0.94, 1.06, size)).round(2)
        df.loc[idx, "employer_name"] = anchor_employer
        df.loc[idx, "employment_type"] = "salaried"
        df.loc[idx, "requested_amount"] = (
            (np.clip(anchor_income * rng.uniform(0.18, 0.42, size), 1_000, 50_000) / 100).round()
            * 100
        )
        df.loc[idx, "session_duration_seconds"] = (
            np.clip(rng.normal(120, 40, size), 20, 500).round().astype(np.int64)
        )
        df.loc[idx, "mouse_movement_events"] = (
            np.clip(rng.normal(70, 35, size), 3, 240).round().astype(np.int64)
        )
        df.loc[idx, "form_paste_count"] = np.clip(rng.poisson(3.0, size), 0, 9).astype(np.int64)
        df.loc[idx, "identity_consistency_score"] = (
            np.clip(rng.beta(2.4, 4.0, size), 0.05, 0.99).round(3)
        )

        _mark_fraud(df, idx, "velocity_attack")
        made += size
        burst += 1
    return made


def _inject_session_anomaly(df, rng, pool, target) -> int:
    """Bot-like sessions: no mouse, everything pasted, in and out fast."""
    idx = pool.take(target)
    size = len(idx)
    if size == 0:
        return 0

    # Roughly a third are scripted from the same harness and land on an almost
    # identical duration - a templated-timing tell.
    templated = rng.random(size) < 0.35
    duration = np.where(
        templated,
        np.clip(rng.normal(31, 3, size), 12, 60),
        rng.uniform(14, 58, size),
    )
    df.loc[idx, "session_duration_seconds"] = duration.round().astype(np.int64)
    df.loc[idx, "mouse_movement_events"] = rng.integers(0, 9, size)
    df.loc[idx, "form_paste_count"] = rng.integers(5, 12, size)
    df.loc[idx, "income_employer_consistency_score"] = (
        np.clip(rng.beta(3.2, 3.4, size), 0.05, 0.99).round(3)
    )
    df.loc[idx, "identity_consistency_score"] = (
        np.clip(rng.beta(3.0, 3.6, size), 0.05, 0.99).round(3)
    )
    _mark_fraud(df, idx, "session_anomaly")
    return size


def _inject_income_mismatch(df, rng, pool, target) -> int:
    """Declared income implausible for the stated employer / employment type."""
    idx = pool.take(target)
    size = len(idx)
    if size == 0:
        return 0

    df.loc[idx, "income_employer_consistency_score"] = (
        np.clip(rng.beta(1.4, 9.0, size), 0.02, 0.55).round(3)
    )
    inflated = np.clip(
        df.loc[idx, "annual_income"].to_numpy() * rng.uniform(1.9, 3.6, size), 15_000, 250_000
    )
    df.loc[idx, "annual_income"] = inflated.round(2)
    df.loc[idx, "requested_amount"] = (
        (np.clip(inflated * rng.uniform(0.22, 0.5, size), 1_000, 50_000) / 100).round() * 100
    )
    df.loc[idx, "employment_type"] = rng.choice(
        ["gig_worker", "self_employed", "salaried"], size=size, p=[0.42, 0.38, 0.20]
    )
    df.loc[idx, "form_paste_count"] = np.clip(rng.poisson(1.8, size), 0, 8).astype(np.int64)
    _mark_fraud(df, idx, "income_mismatch")
    return size


def _inject_identity_inconsistency(df, rng, pool, target) -> int:
    """Small mismatches across the declared name / address / phone tuple."""
    idx = pool.take(target)
    size = len(idx)
    if size == 0:
        return 0

    df.loc[idx, "identity_consistency_score"] = (
        np.clip(rng.beta(1.3, 9.0, size), 0.02, 0.55).round(3)
    )
    df.loc[idx, "income_employer_consistency_score"] = (
        np.clip(rng.beta(3.6, 3.2, size), 0.05, 0.99).round(3)
    )
    df.loc[idx, "form_paste_count"] = np.clip(rng.poisson(2.2, size), 0, 9).astype(np.int64)
    df.loc[idx, "mouse_movement_events"] = (
        np.clip(rng.normal(120, 55, size), 8, 300).round().astype(np.int64)
    )
    _mark_fraud(df, idx, "identity_inconsistency")
    return size


# --------------------------------------------------------------------------
# Hard legitimate cases
# --------------------------------------------------------------------------


def _inject_hard_legitimate(df, rng, pool, target, tag) -> dict[str, int]:
    """Genuine customers who trip one or two fraud-shaped signals anyway.

    These stay is_fraud=False. They exist so the dataset is not trivially
    separable, and so the review queue has honest 'flagged, then cleared' cases.
    """
    made = {flavor: 0 for flavor in HARD_LEGIT_FLAVORS}
    household = 0
    while sum(made.values()) < target and len(pool) >= 4:
        flavor = str(rng.choice(HARD_LEGIT_FLAVORS, p=HARD_LEGIT_WEIGHTS))

        if flavor == "family_device":
            # One household laptop, two to four relatives applying the same week.
            size = int(rng.integers(2, 5))
            idx = pool.take(size)
            span_hours = float(rng.uniform(6, 40))
            anchor = _random_anchor(rng, span_hours)
            offsets = np.sort(rng.uniform(0, span_hours * 3_600, size)).astype(np.int64)
            df.loc[idx, "timestamp"] = pd.to_datetime(anchor + offsets.astype("timedelta64[s]"))
            df.loc[idx, "device_id"] = _hash_token(f"{tag}|household-device|{household}")
            df.loc[idx, "ip_hash"] = _hash_token(f"{tag}|household-ip|{household}")
            household += 1
            made[flavor] += size
            continue

        idx = pool.take(int(rng.integers(1, 4)))
        if not idx:
            break
        size = len(idx)

        if flavor == "accessibility_tool":
            # Stylus / switch-access user: almost no pointer movement, but they
            # take their time and type everything by hand.
            df.loc[idx, "mouse_movement_events"] = rng.integers(2, 18, size)
            df.loc[idx, "session_duration_seconds"] = (
                np.clip(rng.normal(430, 120, size), 200, 900).round().astype(np.int64)
            )
            df.loc[idx, "form_paste_count"] = np.clip(rng.poisson(0.4, size), 0, 2).astype(np.int64)
        elif flavor == "autofill_manager":
            # Password manager fills every field; movement and pacing are normal.
            df.loc[idx, "form_paste_count"] = rng.integers(5, 10, size)
            df.loc[idx, "mouse_movement_events"] = (
                np.clip(rng.normal(175, 45, size), 60, 300).round().astype(np.int64)
            )
        else:  # thin_file
            # Recently moved or newly self-employed: one score looks bad, the
            # rest of the application is clean.
            column = (
                "income_employer_consistency_score"
                if rng.random() < 0.5
                else "identity_consistency_score"
            )
            df.loc[idx, column] = np.clip(rng.uniform(0.14, 0.36, size), 0.02, 0.99).round(3)

        made[flavor] += size
    return made


# --------------------------------------------------------------------------
# Dataset assembly
# --------------------------------------------------------------------------


def generate_dataset(n_rows: int, seed: int, tag: str, archetype_mix: dict[str, float]):
    rng = np.random.default_rng(seed)
    employers = build_employer_pool()

    df = _base_population(rng, n_rows, tag, employers)
    pool = _IndexPool(n_rows, rng)

    # Per-archetype targets get +/-12% jitter so the realised fraud rate drifts
    # naturally around 5% instead of snapping to it.
    nominal = n_rows * BASE_FRAUD_RATE
    targets = {
        name: max(1, int(round(nominal * share * rng.uniform(0.88, 1.12))))
        for name, share in archetype_mix.items()
    }

    _inject_device_recycling(df, rng, pool, targets["device_recycling"], tag)
    _inject_velocity_attack(df, rng, pool, targets["velocity_attack"], employers, tag)
    _inject_session_anomaly(df, rng, pool, targets["session_anomaly"])
    _inject_income_mismatch(df, rng, pool, targets["income_mismatch"])
    _inject_identity_inconsistency(df, rng, pool, targets["identity_inconsistency"])

    hard_legit = _inject_hard_legitimate(df, rng, pool, int(round(n_rows * HARD_LEGIT_RATE)), tag)

    # Velocity features are derived from the final device/IP reuse, never set
    # directly - so they always agree with the timestamps on every row.
    df["applications_from_device_last_24h"] = _rolling_24h_counts(df, "device_id")
    df["applications_from_ip_last_24h"] = _rolling_24h_counts(df, "ip_hash")

    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    df.insert(
        0,
        "application_id",
        [str(uuid.UUID(bytes=rng.bytes(16), version=4)) for _ in range(len(df))],
    )

    df["is_fraud"] = df["is_fraud"].astype(bool)
    return df[COLUMNS], hard_legit


def summarize(df: pd.DataFrame, name: str, hard_legit: dict[str, int]) -> str:
    n = len(df)
    n_fraud = int(df["is_fraud"].sum())
    counts = df["fraud_type"].value_counts()
    lines = [
        f"{name}: {n:,} rows | fraud {n_fraud:,} ({n_fraud / n:.2%}) | legit {n - n_fraud:,}",
        "  fraud_type breakdown:",
    ]
    for fraud_type in FRAUD_TYPES:
        c = int(counts.get(fraud_type, 0))
        lines.append(f"    {fraud_type:<24} {c:>5}  ({c / n:.2%} of all rows)")
    lines.append(f"  hard-legitimate cases injected: {sum(hard_legit.values()):,}")
    for flavor, c in hard_legit.items():
        lines.append(f"    {flavor:<24} {c:>5}")
    lines.append(
        "  max applications_from_device_last_24h: "
        f"{int(df['applications_from_device_last_24h'].max())} | "
        f"max applications_from_ip_last_24h: {int(df['applications_from_ip_last_24h'].max())}"
    )
    return "\n".join(lines)


def _breakdown_table(df: pd.DataFrame) -> str:
    counts = df["fraud_type"].value_counts()
    n = len(df)
    rows = [
        f"| `{ft}` | {int(counts.get(ft, 0)):,} | {int(counts.get(ft, 0)) / n:.2%} |"
        for ft in FRAUD_TYPES
    ]
    legit = n - int(df["is_fraud"].sum())
    rows.append(f"| _(not fraud)_ | {legit:,} | {legit / n:.2%} |")
    return "\n".join(rows)


def write_data_card(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    train_hl: dict[str, int],
    holdout_hl: dict[str, int],
    path: Path,
) -> None:
    card = f"""# Aegis Data Card — Synthetic Digital Lending Applications

## 1. Synthetic data statement

**Every row in these files is synthetic.** The datasets were produced
programmatically by `ml/generate_synthetic_data.py` using NumPy and Pandas. No
real customer, applicant, account, application, device, IP address, employer,
or institution is represented, sampled, anonymised, or approximated here. No
production data, scraped data, or personally identifiable information of any
kind was used as input. Employer names come from the `faker` library and are
fictional; any resemblance to a real company is coincidental. Metrics computed
on this data describe performance on a simulation and are not claims about
real-world fraud detection accuracy.

No large language model was involved in generating this tabular data. The
generation is fully deterministic given the seeds below, which keeps the
statistical properties controllable and every downstream result reproducible.
(The LLM in Aegis is used only for free-text investigator narratives, generated
separately by `ml/generate_narratives.py`.)

## 2. Reproducibility

| Dataset | File | Rows | Seed |
|---|---|---|---|
| Train | `data/applications_train.csv` | {len(train):,} | `{TRAIN_SEED}` |
| Holdout | `data/applications_holdout.csv` | {len(holdout):,} | `{HOLDOUT_SEED}` |

The employer-name pool is seeded separately with `{EMPLOYER_POOL_SEED}` and is shared by both
datasets (same fictional lender, same fictional employer universe). Timestamps
span a fixed 90-day window ending `{WINDOW_END:%Y-%m-%d}` — hard-coded rather than derived
from the current date, so re-running the generator reproduces identical output.

```bash
pip install -r ml/requirements.txt
python ml/generate_synthetic_data.py
```

## 3. Generation methodology

1. **Base population.** Every record starts as a legitimate application.
   Applicant age is normal (mu=35, sigma=11) clipped to 18–75. Annual income is
   log-normal around $48k, scaled by employment type, clipped to $15k–$250k.
   Requested amount is a noisy fraction (6–45%) of income, clipped to
   $1,000–$50,000. Timestamps are uniform across 90 days with an hour-of-day
   weighting that concentrates activity between 09:00 and 21:00. Device and IP
   identifiers are SHA-256 surrogates, unique per application by default.
   Behavioral signals are drawn from human-plausible distributions: session
   duration ~ N(185s, 65s); mouse movement ~ N(168, 55) clipped to 50–300
   events; paste count ~ Poisson(0.7) capped at 3. Both consistency scores are
   Beta-distributed and skew high.
2. **Fraud archetypes are carved out of that population** on disjoint row
   indices, so no record is claimed by two archetypes. Rings and bursts also
   rewrite the timestamps and shared identifiers of their members.
3. **Hard-legitimate cases** are then carved from the remaining rows.
4. **Velocity features are derived last**, by counting prior-24h reuse of each
   `device_id` / `ip_hash` across the finished table (inclusive of the row
   itself). They are never written directly, so they always agree with the
   timestamps and identifiers actually present.
5. Rows are sorted by timestamp and assigned UUID application ids.

Per-archetype targets carry +/-12% random jitter and ring/burst sizes are
themselves random, so the realised fraud rate emerges near 5% rather than being
forced to it exactly.

## 4. Schema

| Field | Type | Description |
|---|---|---|
| `application_id` | UUID string | Unique application identifier. |
| `timestamp` | datetime | Submission time within the 90-day window, clustered in waking hours. |
| `applicant_age` | int | 18–75. Mild covariate only — see the fairness note in §8. |
| `annual_income` | float | Declared annual income, $15k–$250k, log-normal. |
| `employment_type` | categorical | `salaried` / `self_employed` / `gig_worker` / `unemployed`. |
| `employer_name` | string | Fictional employer (Faker). `NOT_EMPLOYED` when unemployed. |
| `requested_amount` | float | Requested principal, $1,000–$50,000, correlated with income. |
| `loan_purpose` | categorical | `debt_consolidation`, `home_improvement`, `medical`, `education`, `business`, `other`. |
| `device_id` | string | 16-char SHA-256 surrogate for a device fingerprint. |
| `ip_hash` | string | 16-char SHA-256 surrogate for a source IP. |
| `session_duration_seconds` | int | Time from form open to submit. |
| `mouse_movement_events` | int | Pointer-movement events captured during the session. |
| `form_paste_count` | int | Form fields filled by paste rather than keystrokes. |
| `applications_from_device_last_24h` | int | Derived velocity: applications sharing this `device_id` in the prior 24h, inclusive of this one. |
| `applications_from_ip_last_24h` | int | Derived velocity: applications sharing this `ip_hash` in the prior 24h, inclusive of this one. |
| `income_employer_consistency_score` | float 0–1 | Plausibility of declared income given the stated employer and employment type. Higher is more consistent. |
| `identity_consistency_score` | float 0–1 | Agreement across the declared name / address / phone tuple. Higher is more consistent. |
| `is_fraud` | bool | Ground-truth label. |
| `fraud_type` | categorical or empty | Dominant archetype when `is_fraud` is true; empty otherwise. |

## 5. Fraud archetypes

Each archetype is a structurally distinct pattern, not label noise. Signals
bleed mildly across archetypes (a ring operator is usually also fast and
paste-heavy), so no single feature cleanly separates the classes.

1. **`device_recycling`** — one `device_id` and `ip_hash` reused across 3–8
   applications inside a 24–48h window. Roughly 15% of ring members are left
   labelled legitimate, representing genuine shared-household use of the same
   machine.
2. **`velocity_attack`** — a burst of 4–9 applications from a single `ip_hash`
   within 1–3 hours, rotating device fingerprints but reusing one
   identity-adjacent profile skeleton (same employer, near-identical age and
   income) with small deliberate jitter.
3. **`session_anomaly`** — bot-like sessions: near-zero mouse movement (0–8
   events), 5–11 pasted fields, and 14–58 second durations. About a third
   cluster tightly near 31s, the tell of a scripted harness.
4. **`income_mismatch`** — `income_employer_consistency_score` drawn from
   Beta(1.4, 9) so it lands in the bottom decile of the legitimate
   distribution, paired with income inflated 1.9–3.6x and a correspondingly
   larger ask.
5. **`identity_inconsistency`** — `identity_consistency_score` drawn from
   Beta(1.3, 9), landing in the bottom decile, with otherwise ordinary
   application content.

## 6. Hard-legitimate cases

Approximately {HARD_LEGIT_RATE:.0%} of rows are genuine customers who trip one or two
fraud-shaped signals and are nonetheless labelled `is_fraud = False`:

- **`family_device`** — 2–4 relatives applying from one household machine
  within a few days, so device- and IP-velocity look elevated.
- **`accessibility_tool`** — stylus or switch-access users with almost no
  pointer movement, but long, unhurried sessions and no pasting.
- **`autofill_manager`** — password managers filling every field, producing a
  high paste count alongside completely normal movement and pacing.
- **`thin_file`** — recently relocated or newly self-employed applicants whose
  income-employer *or* identity consistency score is genuinely low while the
  rest of the application is clean.

These exist for two reasons. First, without them the dataset is trivially
separable and any model scores near-perfectly for the wrong reason. Second,
they give the review queue and the explainability layer honest material: cases
that are correctly surfaced for human review and then correctly cleared. They
are deliberately **not** flagged by a column in the CSV — a "this looks
suspicious but isn't" label would leak straight into training — but they are
fully reproducible from the seeds above.

Measured hard-legitimate injections: **{sum(train_hl.values()):,}** rows in train, **{sum(holdout_hl.values()):,}** rows in holdout.

| Flavor | Train | Holdout |
|---|---|---|
| `family_device` | {train_hl.get('family_device', 0):,} | {holdout_hl.get('family_device', 0):,} |
| `accessibility_tool` | {train_hl.get('accessibility_tool', 0):,} | {holdout_hl.get('accessibility_tool', 0):,} |
| `autofill_manager` | {train_hl.get('autofill_manager', 0):,} | {holdout_hl.get('autofill_manager', 0):,} |
| `thin_file` | {train_hl.get('thin_file', 0):,} | {holdout_hl.get('thin_file', 0):,} |

## 7. Measured class balance

### Train (`applications_train.csv`, seed {TRAIN_SEED})

Total rows: **{len(train):,}** · Fraud: **{int(train['is_fraud'].sum()):,}** · Fraud rate: **{train['is_fraud'].mean():.2%}**

| fraud_type | count | share of all rows |
|---|---|---|
{_breakdown_table(train)}

### Holdout (`applications_holdout.csv`, seed {HOLDOUT_SEED})

Total rows: **{len(holdout):,}** · Fraud: **{int(holdout['is_fraud'].sum()):,}** · Fraud rate: **{holdout['is_fraud'].mean():.2%}**

| fraud_type | count | share of all rows |
|---|---|---|
{_breakdown_table(holdout)}

The holdout deliberately uses a **different archetype mix** (more
`session_anomaly` and `income_mismatch`, fewer ring- and burst-driven cases) so
that generalisation is measured honestly rather than against a copy of the
training distribution.

## 8. Fairness and excluded attributes

The schema contains **no protected or sensitive attributes**: no gender, race,
ethnicity, religion, disability status, marital or family status, national
origin, sexual orientation, or ZIP-code-level geography. None of these were
generated, and none are recoverable from the fields present.

`applicant_age` is included only as a mild behavioral covariate. It carries no
engineered relationship to `is_fraud` in any archetype and is not used as a
proxy for any protected characteristic. It is retained because session
behavior genuinely varies with age in real products, and because dropping it
silently would hide that question rather than answer it. If age-related
disparity shows up in downstream model evaluation, the correct response is to
measure it explicitly and remove the feature — not to assume its absence from
the schema would have guaranteed fairness.

Employment type and employer name are economic attributes rather than
protected ones, but they are the most plausible route to proxy discrimination
in this schema and should be monitored in any fairness audit of the trained
model.
"""
    path.write_text(card, encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    train, train_hl = generate_dataset(TRAIN_ROWS, TRAIN_SEED, "aegis-train", TRAIN_ARCHETYPE_MIX)
    holdout, holdout_hl = generate_dataset(
        HOLDOUT_ROWS, HOLDOUT_SEED, "aegis-holdout", HOLDOUT_ARCHETYPE_MIX
    )

    train_path = DATA_DIR / "applications_train.csv"
    holdout_path = DATA_DIR / "applications_holdout.csv"
    card_path = DATA_DIR / "data_card.md"

    train.to_csv(train_path, index=False)
    holdout.to_csv(holdout_path, index=False)
    write_data_card(train, holdout, train_hl, holdout_hl, card_path)

    print("=" * 74)
    print("Aegis synthetic dataset generation complete (100% synthetic data)")
    print("=" * 74)
    print(summarize(train, f"TRAIN   (seed {TRAIN_SEED})", train_hl))
    print()
    print(summarize(holdout, f"HOLDOUT (seed {HOLDOUT_SEED})", holdout_hl))
    print()
    print("Written:")
    for p in (train_path, holdout_path, card_path):
        print(f"  {p.relative_to(PROJECT_ROOT)}  ({p.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
