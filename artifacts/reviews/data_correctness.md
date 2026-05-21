# Data Correctness Review

Reviewer: simulated data correctness reviewer

Source-of-truth run:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Verdict

Pass. The dashboard is wired to the curated latest-arbitration data pack and the headline finalist metrics reconcile to the expected source-of-truth values within 0.01 percentage points.

## Latest finalist checks

| Stream | Expected model | Quarterly MAPE | Annual MAPE | Quarterly bias | Status |
|---|---|---:|---:|---:|---|
| PED VKT per capita | `PED__solver_static_convex_top18` | 2.47358 | 2.38709 | 1.50491 | Pass |
| Light RUC volume | `LIGHT_RUC__solver_static_convex_top18` | 9.14755 | 5.99950 | 0.738125 | Pass |
| Heavy RUC volume | `HEAVY_RUC__solver_static_convex_top18` | 3.56092 | 3.17141 | 0.165850 | Pass |

## Stale-value rejection

The older AutoGluon balanced-run finalist values are not current finalist values in `artifacts/curated_data/finalist_accuracy.csv`.

| Stale value | Current use | Status |
|---:|---|---|
| 5.49% | Rejected as stale current-finalist value | Pass |
| 11.55% | Rejected as stale current-finalist value | Pass |
| 12.38% | Rejected as stale current-finalist value | Pass |

Historical prediction-error rows may naturally contain similar percentages as individual forecast errors; those are not current finalist headline metrics.

## Curated file checks

- `finalist_accuracy.csv`: 3 rows.
- `candidate_landscape_sample.csv`: 293 rows.
- `schiff_benchmark.csv`: 3 rows.
- `pdf_comparison.csv`: 3 rows.
- `stress_horizon.csv`: 18 rows.
- `ensemble_composition.csv`: 12 positive-weight rows.
- `annual_predictions_selected.csv`: 530 rows.
- `quarterly_predictions_selected.csv`: 3,036 rows.

## Evidence

- `artifacts/curated_data/verification_report.md`
- `tests/test_latest_arbitration_values.py`
- `tests/test_no_stale_finalist_values.py`
- `tests/test_curated_data.py`
