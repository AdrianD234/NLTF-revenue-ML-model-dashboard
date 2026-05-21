# DATA_VALIDATION_SPRINT.lock.md

This locked file defines the recursive data-quality sprint for the Stage 1 Model Governance Dashboard.

The dashboard must use the latest arbitration run as its source of truth:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Required latest finalist values

| Stream | Model | Quarterly MAPE | Annual MAPE | Quarterly bias |
|---|---|---:|---:|---:|
| PED | PED__solver_static_convex_top18 | 2.47358 | 2.38709 | 1.50491 |
| LIGHT_RUC | LIGHT_RUC__solver_static_convex_top18 | 9.14755 | 5.99950 | 0.738125 |
| HEAVY_RUC | HEAVY_RUC__solver_static_convex_top18 | 3.56092 | 3.17141 | 0.165850 |

## Stale-value rejection

The dashboard must not present these older AutoGluon balanced-run values as current latest finalists:

- PED quarterly MAPE around 5.49%.
- Light RUC quarterly MAPE around 11.55%.
- Heavy RUC quarterly MAPE around 12.38%.

Historical artifacts may mention these values only as explicitly rejected stale values, not as current winners.

## Completion rule

Do not complete a data-quality sprint unless:

- curated data is rebuilt from the latest arbitration run;
- curated verification passes;
- visible dashboard values round to 2.47%, 2.39%, 9.15%, 6.00%, 3.56%, and 3.17%;
- stale finalist values are absent from current finalist cards/charts;
- `artifacts/data_validation_review.md` and reviewer reports document the result.
