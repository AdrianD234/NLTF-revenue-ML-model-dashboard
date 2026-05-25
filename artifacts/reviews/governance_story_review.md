# Governance Story Review

## Resolution Status

Closed for the latest-arbitration curated-data pass.

## Scope

Reviewed whether the dashboard tells the management story for the latest arbitration run:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Management Questions

### Which model won?

The latest arbitration finalists are:

| Stream | Winning model | Quarterly MAPE | Annual MAPE |
|---|---|---:|---:|
| PED VKT per capita | `PED__solver_static_convex_top18` | 2.47% | 2.39% |
| Light RUC volume | `LIGHT_RUC__solver_static_convex_top18` | 9.15% | 6.00% |
| Heavy RUC volume | `HEAVY_RUC__RECON_STATIC_REBUILT` | 3.48% | 3.02% |

### Did it beat Schiff?

Yes, the dashboard frames the benchmark comparison against pure Schiff rows only, not residual or blended Schiff-derived challengers.

### Is the result robust?

Partly. PED and Heavy RUC read strongly at Stage 1. Light RUC remains the watch stream because RUC discount and purchase-timing effects continue to show up in the 2022-23 stress window.

### What are the warnings?

Warnings are now framed as governance caveats rather than app errors: Stage 1 uses realised explanatory variables, Light RUC remains difficult in stress periods, and Stage 2 still needs macro/fuel-input forecast uncertainty.

### What should a manager conclude?

Use the latest arbitration finalists as the Stage 1 champion set, retain pure Schiff as the structural benchmark, and move the Light RUC stress-window caveat explicitly into Stage 2 governance.

## Evidence

- `REFERENCE_DASHBOARD_INSIGHTS.lock.md`
- `artifacts/curated_data/finalist_accuracy.csv`
- `artifacts/curated_data/schiff_benchmark.csv`
- `artifacts/curated_data/stress_horizon.csv`
- `tests/test_playwright_dashboard.py`
