# Data Correctness Review

## Resolution Status

Closed for the latest-arbitration curated-data pass.

The dashboard now defaults to:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Headline metric reconciliation

| Stream | Curated model | Quarterly MAPE | Annual MAPE | Quarterly bias | Result |
|---|---|---:|---:|---:|---|
| PED VKT per capita | `PED__solver_static_convex_top18` | 2.47358 | 2.38709 | 1.50491 | Pass |
| Light RUC volume | `LIGHT_RUC__solver_static_convex_top18` | 9.14755 | 5.99950 | 0.738125 | Pass |
| Heavy RUC volume | `HEAVY_RUC__RECON_STATIC_REBUILT` | 3.48437 | 3.01998 | Current Parquet | Pass |

## Data-pack checks

- `candidate_landscape_sample.csv` is capped at 293 rows.
- The candidate landscape contains selected finalists, pure Schiff rows, distribution samples, top candidates, previous PDF/reference rows, and frontier flags.
- `schiff_benchmark.csv` contains only pure `SCHIFF_OLS` benchmark rows and excludes solver/residual/blend variants.
- `stress_horizon.csv` includes 1-4 qtrs, 5-8 qtrs, 9-12 qtrs, 2024+, 2022-23 and Annual.
- `ensemble_composition.csv` contains positive weights for all three latest finalists.

## Rejected stale values

The old balanced-run values 5.49%, 11.55%, and 12.38% are not the latest finalist headline values. They are allowed only in explicit stale-value rejection notes or as incidental forecast-error percentages in selected prediction rows.

## Evidence

- `artifacts/curated_data/verification_report.md`
- `tests/test_latest_arbitration_values.py`
- `tests/test_no_stale_finalist_values.py`
- `tests/test_curated_data.py`
