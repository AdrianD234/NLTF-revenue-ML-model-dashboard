# Data Correctness Review

Status: **PASS** for the Parquet-backed Stage 1 dashboard validation run on 2026-05-22.

Retained latest arbitration smoke run: `run_20260520_002339`.

Primary data root:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack`

Resolved primary Parquet:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet`

## Current Finalist Checks

| Stream | Quarterly MAPE | Annual MAPE | Status |
|---|---:|---:|---|
| PED VKT per capita | 2.473245 | 2.385625 | PASS |
| Light RUC volume | 9.147545 | 5.999499 | PASS |
| Heavy RUC volume | 3.484368 | 3.019980 | PASS |

## Pure Schiff And Gain Checks

| Stream | Schiff Qtr | Schiff Annual | Full-sample Qtr Gain | Full-sample Annual Gain | Paired Win Rate | Status |
|---|---:|---:|---:|---:|---:|---|
| PED VKT per capita | 3.082117 | 2.965758 | +0.608873 | +0.580133 | 63.201320 | PASS |
| Light RUC volume | 11.546786 | 7.843683 | +2.399241 | +1.844184 | 50.555556 | PASS |
| Heavy RUC volume | 11.482643 | 11.717804 | +7.998276 | +8.697824 | 64.155251 | PASS |

Light RUC paired common-grid quarterly gain is recorded separately as -1.159120 pp. It is not labelled as the full-sample gain.

## Source Table Evidence

- `artifacts/chart_sources/overview_finalist_forecast_accuracy.csv`
- `artifacts/chart_sources/overview_candidate_search_frontier.csv`
- `artifacts/chart_sources/overview_ensemble_composition.csv`
- `artifacts/chart_sources/overview_stress_horizon_checks.csv`
- `artifacts/chart_sources/diagnostics_residual_autocorrelation.csv`
- `artifacts/chart_sources/diagnostics_residual_vs_fitted.csv`
- `artifacts/chart_sources/diagnostics_pass_matrix.csv`
- `artifacts/chart_sources/diagnostics_error_distribution_by_horizon.csv`
- `artifacts/chart_sources/scenario_stream_comparison.csv`
- `artifacts/chart_sources/scenario_improvement_vs_benchmark.csv`
- `artifacts/chart_sources/scenario_horizon_comparison.csv`
- `artifacts/chart_sources/scenario_decision_summary.csv`
- `artifacts/chart_sources/schiff_vs_finalist_mape.csv`
- `artifacts/chart_sources/schiff_benchmark_horizon_profiles.csv`
- `artifacts/chart_sources/schiff_paired_or_fullsample_gain.csv`
- `artifacts/chart_sources/schiff_benchmark_summary.csv`

## Stale-Value Rejection

The old finalist values 5.49%, 11.55% as a Light RUC finalist value, and 12.38% are rejected by data validation and browser DOM checks. The 11.55% value may appear only as the Light RUC pure-Schiff benchmark value.
