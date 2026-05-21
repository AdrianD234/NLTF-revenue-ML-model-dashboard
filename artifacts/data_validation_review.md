# Data Validation Review

Status: pass for the current verification pass.

Source-of-truth run:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Checks completed

- Curated data rebuilt from the latest arbitration run.
- Curated verification report regenerated.
- Latest finalist models match the locked source-of-truth models.
- Latest finalist MAPE and bias values reconcile within tolerance.
- Older AutoGluon balanced-run finalist values are rejected as current winners.
- Pure Schiff benchmark rows exclude residual, blend, solver, ensemble, mean, median, convex and top-model tokens.
- Stress buckets include 1-4 qtrs, 5-8 qtrs, 9-12 qtrs, 2024+, 2022-23 and Annual.
- Ensemble composition contains positive weights for all three streams.

## Latest visible finalist values

| Stream | Quarterly MAPE | Annual MAPE |
|---|---:|---:|
| PED VKT per capita | 2.47% | 2.39% |
| Light RUC volume | 9.15% | 6.00% |
| Heavy RUC volume | 3.56% | 3.17% |

## Evidence

- `artifacts/curated_data/verification_report.md`
- `tests/test_latest_arbitration_values.py`
- `tests/test_no_stale_finalist_values.py`
- `tests/test_playwright_dashboard.py`
