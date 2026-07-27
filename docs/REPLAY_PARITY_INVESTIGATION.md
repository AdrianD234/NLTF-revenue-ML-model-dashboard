# Governed replay parity: open investigation

**Status:** open. Cause not yet confirmed; tolerances deliberately untouched.

## What was observed

Clean-environment CI found the governed fixed-finalist replay producing values
up to **0.42% apart** from the local Windows run:

| Test | Observed | Expected | Relative |
|---|---|---|---|
| `test_append_creates_three_distinct_idempotent_traces...` | 3,356,901,625.22 | 3,359,089,541.45 | 6.5e-4 |
| same, worst of 98/294 mismatched elements | — | — | **4.2e-3** |
| `test_base_original_timing_reconciles_to_default_dashboard_hover_benchmarks` | 2084.543502923883 | 2084.543721076793 | 1.0e-7 |

For a *fixed-finalist* replay — one that is supposed to reproduce committed
fitted state exactly — 0.42% is far too large to dismiss as floating-point
noise. It is not being dismissed, and no tolerance has been relaxed.

## Baseline comparison: nothing was introduced by the P0 branch

Identical CI was run against unmodified `main` (`8431c61`) to establish a
baseline rather than assume one.

| | Baseline `main` | P0 branch |
|---|---|---|
| Run | `30228519139` | `30226687382` |
| Result | 36 failed, 572 passed | 36 failed, 615 passed |
| Failing test set | — | **identical, zero difference** |

`comm` over the sorted failure lists returns empty in both directions: no test
fails on the P0 branch that does not fail on `main`, and none was fixed. The 43
extra passes are the tests this branch adds.

The **magnitude** of the numerical divergence does differ slightly:

| | Baseline | P0 |
|---|---|---|
| Timing checkpoint observed | 2084.543432234145 | 2084.543502923883 |
| Expected (Windows-generated) | 2084.543721076793 | 2084.543721076793 |
| Max relative divergence | 0.00478 | 0.00416 |
| Mismatched elements | 98 / 294 | 98 / 294 |

The same 98 rows diverge in both, by slightly different amounts. This should
**not** be read as the P0 branch improving reproducibility. The P0 changes to
the replay path are metadata — component labelling, validation status columns,
guard lineage — and none of them alters an arithmetic operation. A divergence
whose size shifts under unrelated code changes, while its location does not, is
the signature of an environment-driven floating-point difference rather than a
deterministic code difference.

Local determinism was checked separately: two consecutive runs of
`scripts/replay_parity_fingerprint.py` on the same machine produce an identical
`replay_fingerprint.csv` SHA-256, so the replay is deterministic *within* an
environment. The divergence is *between* environments.

## The leading hypothesis is environment skew, not platform

The local development environment does not match the pinned runtime:

| Package | `requirements.txt` | Local `.venv` | CI |
|---|---|---|---|
| Python | `runtime.txt`: 3.11 | **3.13.5** | 3.11 |
| scikit-learn | **1.9.0** | **1.7.2** | 1.9.0 |
| streamlit | 1.59.0 | 1.58.0 | 1.59.0 |
| numpy | 2.4.6 | 2.4.6 | 2.4.6 |
| pandas | 3.0.3 | 3.0.3 | 3.0.3 |
| pyarrow | 24.0.0 | 24.0.0 | 24.0.0 |

The finalists are scikit-learn estimators (`GradientBoostingRegressor`,
`Ridge`, OLS-plus-residual-GBR) whose fitted states are joblib-serialized. A
two-minor-version scikit-learn gap across a serialization boundary is a
sufficient explanation on its own, and there is precedent in this repository:
commit `849fce9` had to add a legacy scikit-learn `_loss` import alias so old
fitted states would load at all.

**This means the "648 passed locally" result was obtained under a runtime that
is not the pinned production runtime.** That is an assurance finding in its own
right, independent of which way the parity question resolves.

## How the question gets settled

`.github/workflows/ci.yml` runs a `replay-parity` job on **both**
`ubuntu-latest` and `windows-latest`, each installing the *same pinned*
`requirements.txt`. That separates the two candidate causes:

- **Both platforms agree** → the divergence was environment skew, not platform.
  The fix is to make the local environment conform, and to keep CI as the
  authority.
- **They still differ** → the divergence is genuinely platform-dependent
  (BLAS/LAPACK backend being the usual culprit), and the governed replay needs
  an explicitly locked authoritative runtime with a documented parity result.

`scripts/replay_parity_fingerprint.py` emits what is needed to localise it:

- resolved versions for Python, numpy, pandas, scipy, scikit-learn, joblib,
  pyarrow and statsmodels, plus the `threadpoolctl` BLAS backend report;
- SHA-256 of every committed scenario input and fitted-state file;
- a **raw-input** fingerprint that calls no model, so a difference there would
  mean the divergence is in data loading rather than in the model;
- a full-precision (`.17g`) per scenario/stream/quarter replay fingerprint.

Diffing the two platforms' `replay_fingerprint.csv` identifies the first stage
that diverges: if `raw_bridge_fingerprint.csv` matches but
`replay_fingerprint.csv` does not, the cause is in the model call, not the
inputs.

## What must not happen

- Do **not** widen the failing tolerances to make CI green. The tolerances are
  the only thing currently detecting this.
- Do **not** treat "the baseline branch fails the same way" as resolution. That
  establishes the P0 branch did not introduce it; it does not make the governed
  model reproducible.

## Next actions

1. Read the two `replay-parity` job artifacts and diff them.
2. If they agree, rebuild the local `.venv` from `requirements.txt` under
   Python 3.11 and re-run the suite; expect the two failing tests to pass.
3. If they disagree, capture the BLAS backends from both and decide whether to
   pin an authoritative runtime or to record a documented parity tolerance with
   an explicit governance rationale.
