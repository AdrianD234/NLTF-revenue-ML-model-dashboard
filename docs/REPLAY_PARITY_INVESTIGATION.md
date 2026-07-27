# Governed replay parity: cause identified, decision required

**Status:** cause located and evidenced. Tolerances untouched. A scope decision
is required before this closes — see [Two ways to close it](#two-ways-to-close-it).

## Conclusion first

The divergence is **entirely confined to Light RUC**, and it is caused by Light
RUC being **refit at score time** while PED and Heavy RUC load committed fitted
state.

Same pinned runtime on both platforms — identical Python 3.11, numpy 2.4.6,
pandas 3.0.3, scipy 1.17.1, scikit-learn 1.9.0, joblib 1.5.3, pyarrow 24.0.0,
statsmodels 0.14.6, OpenBLAS 0.3.31.188.0 + 0.3.30, 2 threads:

| Stream | Rows compared | Rows diverging | Max relative difference | Fitted state |
|---|---:|---:|---:|---|
| PED | 1200 | **0** | 6.2e-16 | loaded from `fitted_state/` |
| Heavy RUC | 1200 | **0** | 3.4e-16 | loaded from `fitted_state/` |
| Light RUC | 1200 | **1200** | **4.8e-3** | **refit at runtime** |

PED and Heavy RUC are identical to machine epsilon. Light RUC diverges on every
single row.

The repository's own manifest states the mechanism plainly
(`light_ruc_vnext/fitted_model_manifest.json`):

> State export of the incumbent Light RUC fixed recipe. The Forecast Builder
> **refits this exact recipe at score time** from the canonical history; this
> saved state is the audit artifact proving what that refit produces.

The refit is an OLS base fit followed by a `GradientBoostingRegressor` on its
residuals. The OLS solve goes through BLAS, whose kernel selection varies with
CPU architecture even at an identical OpenBLAS version. A last-digit difference
in the OLS residuals becomes the GBR's training target, and gradient boosting is
a step-function amplifier: a marginally different residual can flip a split
decision, turning 1e-16 into 1e-3.

So the "fixed-finalist" replay is **not fixed for Light RUC**. It is the only
stream whose numbers depend on the machine that computes them — and it is also
the weakest stream on the H13–H20 evidence (~20% MAPE at H20).

## Stage localisation

`scripts/replay_parity_fingerprint.py` isolates where the two platforms first
disagree:

| Stage | What it compares | Result |
|---|---|---|
| 1 | SHA-256 of all 248 committed inputs and fitted-state files | **0 differ** |
| 2 | 38 raw input columns, no model call | **0 differ** |
| 3 | 3600 replay forecasts | **1200 differ**, all Light RUC |

Inputs and data loading are identical. The divergence enters at the model call,
and only for the stream that refits.

Evidence: `artifacts/replay_parity_evidence/`, produced by the `replay-parity`
matrix job on `ubuntu-latest` and `windows-latest`.

## What was observed originally

Clean-environment CI found two tests failing against Windows-generated
checkpoints:

| Test | Observed (Linux) | Expected (Windows) | Relative |
|---|---|---|---|
| `test_append_creates_three_distinct_idempotent_traces...` | 3,356,901,625.22 | 3,359,089,541.45 | 6.5e-4 |
| worst of 98/294 mismatched elements | — | — | **4.2e-3** |
| `test_base_original_timing_reconciles_to_default_dashboard_hover_benchmarks` | 2084.543502923883 | 2084.543721076793 | 1.0e-7 |

## Ruled out: environment skew

The local development environment does not match the pinned runtime:

| Package | `requirements.txt` | Local `.venv` | CI |
|---|---|---|---|
| Python | `runtime.txt`: 3.11 | **3.13.5** | 3.11 |
| scikit-learn | **1.9.0** | **1.7.2** | 1.9.0 |
| streamlit | 1.59.0 | 1.58.0 | 1.59.0 |
| numpy / pandas / pyarrow | 2.4.6 / 3.0.3 / 24.0.0 | same | same |

This was the initial hypothesis and it is **wrong**. The parity matrix installs
the same pinned `requirements.txt` on both platforms, every version matched
exactly, and the fingerprints still differ. Version skew is not the cause.

The local mismatch remains a real assurance problem for a different reason:
**every local suite result — including the original handoff's 611 and this
branch's 673 — describes a runtime that is not the one that ships.** The local
`.venv` should be rebuilt from `requirements.txt` under Python 3.11 regardless
of how the parity question is closed.

## Ruled out: non-determinism within an environment

Two consecutive runs of `scripts/replay_parity_fingerprint.py` on the same
machine produce an identical `replay_fingerprint.csv` SHA-256. The replay is
deterministic *within* an environment; the divergence is *between* them.

## Baseline comparison: nothing was introduced by the P0 branch

Identical CI was run against unmodified `main` (`8431c61`):

| | Baseline `main` | P0 branch |
|---|---|---|
| Run | `30228519139` | `30226687382` |
| Result | 36 failed, 572 passed | 36 failed, 615 passed |
| Failing test set | — | **identical, zero difference** |

The divergence *magnitude* differs slightly between branches (max relative
0.00478 vs 0.00416) while the diverging rows are identical. That is not the P0
branch improving reproducibility — its replay-path changes are metadata only.
It is the expected signature of a floating-point effect whose size shifts under
unrelated changes.

## Two ways to close it

**A. Fix at source — use the committed fitted state for Light RUC.** Makes all
three streams state-loading, which is what "fixed finalist" should mean, and
removes the platform sensitivity entirely. It changes the production model path
and will move Light RUC numbers, so it needs an explicit governance decision and
re-promotion of affected checkpoints. This is the correct long-run answer.

**B. Govern it — declare an authoritative runtime and record a parity
tolerance.** Keep the runtime refit, nominate one platform as authoritative
(CI/Linux is the natural choice, being the pinned runtime), regenerate the
Windows-generated checkpoints under it, and record a documented cross-platform
parity tolerance for Light RUC with this investigation as its rationale. Faster,
but it accepts that Light RUC is machine-dependent.

Doing neither and widening the failing assertions is **not** an option: those
two tests are the only thing currently detecting this.

## What must not happen

- Do **not** widen the failing tolerances to make CI green.
- Do **not** treat "the baseline branch fails the same way" as resolution. That
  establishes the P0 branch did not introduce it; it does not make the governed
  model reproducible.

## Reproducing

```bash
python scripts/replay_parity_fingerprint.py --output artifacts/replay_parity
```

Run on two platforms and diff `replay_fingerprint.csv`. If
`raw_bridge_fingerprint.csv` matches while `replay_fingerprint.csv` does not,
the divergence is in the model call rather than the inputs.
