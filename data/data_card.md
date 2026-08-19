# Aegis Data Card — Synthetic Digital Lending Applications

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
| Train | `data/applications_train.csv` | 15,000 | `42` |
| Holdout | `data/applications_holdout.csv` | 3,000 | `99` |

The employer-name pool is seeded separately with `7` and is shared by both
datasets (same fictional lender, same fictional employer universe). Timestamps
span a fixed 90-day window ending `2026-08-01` — hard-coded rather than derived
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
6. **Free-text purpose and ID document references are attached last**, since
   they depend on the final fraud labels and on the assigned application ids.
   See §9.

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
| `loan_purpose_text` | string, 20–120 chars | Free-text reason the applicant gave for the loan. Agrees with `loan_purpose` on legitimate applications; see §9. |
| `id_document_filename` | string, may be empty | Filename of an uploaded synthetic ID image in `data/id_documents/`, or empty when no ID was uploaded (~90% of rows). See §9. |
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

Approximately 5% of rows are genuine customers who trip one or two
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

Measured hard-legitimate injections: **750** rows in train, **153** rows in holdout.

| Flavor | Train | Holdout |
|---|---|---|
| `family_device` | 310 | 55 |
| `accessibility_tool` | 168 | 30 |
| `autofill_manager` | 140 | 38 |
| `thin_file` | 132 | 30 |

## 7. Measured class balance

### Train (`applications_train.csv`, seed 42)

Total rows: **15,000** · Fraud: **750** · Fraud rate: **5.00%**

| fraud_type | count | share of all rows |
|---|---|---|
| `device_recycling` | 180 | 1.20% |
| `velocity_attack` | 172 | 1.15% |
| `session_anomaly` | 158 | 1.05% |
| `income_mismatch` | 116 | 0.77% |
| `identity_inconsistency` | 124 | 0.83% |
| _(not fraud)_ | 14,250 | 95.00% |

### Holdout (`applications_holdout.csv`, seed 99)

Total rows: **3,000** · Fraud: **157** · Fraud rate: **5.23%**

| fraud_type | count | share of all rows |
|---|---|---|
| `device_recycling` | 26 | 0.87% |
| `velocity_attack` | 27 | 0.90% |
| `session_anomaly` | 46 | 1.53% |
| `income_mismatch` | 32 | 1.07% |
| `identity_inconsistency` | 26 | 0.87% |
| _(not fraud)_ | 2,843 | 94.77% |

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

## 9. Multi-modal data

Aegis fuses three modalities per application. Each carries signal the others
cannot see, and each is generated here with the same synthetic-only guarantee.

| Modality | Field(s) | Consumed by |
|---|---|---|
| **Tabular** | 17 structured columns (velocity, session, consistency, application content) | XGBoost risk model + SHAP attributions |
| **Free text** | `loan_purpose_text` | Embedding model, checked for agreement with `loan_purpose` |
| **Image** | `id_document_filename` → PNG in `data/id_documents/` | ID name extraction, compared against the applicant of record |

### 9.1 Free-text purpose (`loan_purpose_text`)

A natural-language sentence, 20–120 characters, drawn from six phrasings per
`loan_purpose` value. Legitimate applications always draw from the pool
matching their own dropdown value, so the structured and unstructured channels
agree.

The two **misrepresentation archetypes** (`income_mismatch`,
`identity_inconsistency`) contradict their own dropdown value 40% of the
time: 55% of those describe a different purpose entirely (dropdown says
`medical`, text describes starting a business), and the remainder collapse into
vague filler such as *"Personal use of funds."* with no verifiable detail.

Ring, burst and bot archetypes keep consistent text on purpose. They are
already detectable from velocity and session signals, so leaving their text
clean forces the text channel to earn its keep on exactly the cases the other
channels cannot see — rather than flattering the model with a signal that
correlates with every fraud type at once.

Measured: **93** inconsistent texts in train (of 240 eligible fraud rows —
53 contradictory, 40 generic) and **26** in holdout (of 58 —
14 contradictory, 12 generic).

### 9.2 Synthetic ID documents (`id_document_filename`)

ID upload is optional in the real product, so **10% of applications carry a
document** and the remaining ~90% leave the field empty.

One archetype departs from that base rate. `identity_inconsistency` cases
upload at **40%**, because presenting a stolen or altered document *is* the
mechanism of that attack — an identity fabricator has a reason to attach an ID
that an ordinary applicant does not. Every other row, legitimate or fraudulent,
stays at the 10% base rate, so the realistic "most people skip the optional
upload" distribution is preserved for the bulk of traffic. The practical effect
is that the ID-check feature has enough positive examples to demonstrate and
evaluate rather than a handful.

Where a document is present, the name printed on it follows the rule:

| Application type | Name on ID |
|---|---|
| Legitimate (including all hard-legitimate cases) | Matches the applicant |
| `identity_inconsistency` | Always mismatched |
| `device_recycling`, `velocity_attack` | Mismatched 30% of the time — ring operators often reuse one document across a batch |
| `session_anomaly`, `income_mismatch` | Matches the applicant |

A mismatch swaps either the first name or the surname, not both, so it reads
as a plausible document rather than an obviously different person.

**Where the applicant's name lives.** The CSV deliberately has no name column —
a name is PII-shaped and is not a modelling feature. The canonical name is
instead *derived* from `application_id` by `applicant_name_for()` in
`ml/generate_synthetic_data.py`, and the match/mismatch decision by
`id_document_plan()`. Both are pure functions of the application id, so the
image generator and the backend recompute the same answer from the CSV alone,
with nothing extra to keep in sync. Storing a match/mismatch flag in the CSV
would have leaked the label straight into a feature column.

Measured: **1,529** documents in train (1,481 matched / 48 mismatched) and
**309** in holdout (296 matched / 13 mismatched).

### 9.3 Image generation and responsible-AI markings

Images are rendered by `ml/generate_id_documents.py` (Pillow) as 400x250 PNGs.
They are **stylized cards, not reproductions of any real government ID
design** — no jurisdiction's layout, seal, colour scheme, security feature, or
typography is imitated, and nothing here could pass as a genuine document.
Every card carries three unmissable markings:

1. A navy header reading **"SYNTHETIC ID CARD — DEMO DATA ONLY"**.
2. A large diagonal **"SYNTHETIC"** watermark across the face of the card.
3. A footer stating it was generated for the Aegis demo and is not a
   government document.

Names, dates of birth, document numbers and issue dates are all fabricated and
derived deterministically from the application id. The images are gitignored
and regenerated from the CSVs by:

```bash
python ml/generate_id_documents.py
```
