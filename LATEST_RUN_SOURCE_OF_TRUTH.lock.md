# LATEST_RUN_SOURCE_OF_TRUTH.lock.md

This file locks the Stage 1 Model Governance Dashboard to the latest finalist arbitration run.

Do not weaken this file, remove these values, or mark this contract complete without reconciliation evidence from the source run.

## Source-of-truth run

The dashboard must load this latest arbitration run folder by default:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

Latest finalist values must come from the latest arbitration outputs, primarily:

1. `final_summary.csv`
2. `recommended_finalists_by_quarterly.csv`
3. `pdf_expected_comparison.csv`
4. `stress_tests.csv`
5. `ensemble_weights.csv`
6. `annual_predictions.csv` or `all_annual_predictions.csv`
7. selected subset of `quarterly_predictions.csv` or `all_quarterly_predictions.csv`, if available locally

`recommended_finalists.csv` may be stale or from an earlier run. Use it only if it reconciles to latest `final_summary.csv` values.

## Latest expected finalists

| Stream | Model | Quarterly MAPE | Annual MAPE | Quarterly Bias |
|---|---|---:|---:|---:|
| PED | PED__solver_static_convex_top18 | 2.47358 | 2.38709 | 1.50491 |
| LIGHT_RUC | LIGHT_RUC__solver_static_convex_top18 | 9.14755 | 5.99950 | 0.738125 |
| HEAVY_RUC | HEAVY_RUC__solver_static_convex_top18 | 3.56092 | 3.17141 | 0.165850 |

## Stale values that must not appear as latest finalists

The dashboard must not show older AutoGluon balanced-run finalist values as the latest arbitration finalists, including:

- PED quarterly MAPE around `5.49%`
- Light RUC quarterly MAPE around `11.55%`
- Heavy RUC quarterly MAPE around `12.38%`

If any visible current-finalist card/chart uses those stale values, verification must fail.
