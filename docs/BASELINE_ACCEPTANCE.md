> **SUPERSEDED NOTE (2026-06):** The metric values in this historical acceptance
> record describe the legacy v6 finalists. The governed pack is now v7 with the
> vNext finalists; see `docs/SCHIFF_SPECIFICATION_BENCHMARK.md` and
> `artifacts/vnext/audit_report.md` for current values. Retained unchanged below
> as the original acceptance record.

# Baseline Acceptance

Status: SCHIFF_SPECIFICATION_BASELINE_ACCEPTED

Evidence pack root: `data/dashboard_evidence_pack`

## Accepted Current Finalists

| Stream | Quarterly MAPE | Annual MAPE |
| --- | ---: | ---: |
| PED VKT per capita | 2.47% | 2.39% |
| Light RUC volume | 9.15% | 6.00% |
| Heavy RUC volume | 3.48% | 3.02% |

## Schiff Specification Benchmark

| Stream | Quarterly MAPE | Annual MAPE |
| --- | ---: | ---: |
| PED VKT per capita | 4.09% | 4.13% |
| Light RUC volume | 8.41% | 5.00% |
| Heavy RUC volume | 7.80% | 8.11% |

## Gain Semantics

Full-sample gains compare finalist MAPE with Schiff specification benchmark MAPE over their full evidence rows. Paired common-grid gain is separate. Light RUC has negative full-sample gain (-0.73 pp quarterly, -1.00 pp annual), negative paired quarterly gain of about -0.76 pp, and paired win rate about 46.71%.

## Evidence Pack Row Counts

| Table | Rows |
| --- | ---: |
| candidate_cone.parquet | 300 |
| finalists.parquet | 3 |
| schiff_benchmark.parquet | 3 |
| ensemble_components.parquet | 8 |
| residual_predictions.parquet | 3,196 |
| horizon_profiles.parquet | 72 |
| stress_horizon.parquet | 36 |
| scenario_comparison.parquet | 3 |
| diagnostic_tests.parquet | 6 |
| diagnostic_pass_matrix.parquet | 27 |
| diagnostic_acf.parquet | 39 |
| error_distribution.parquet | 2,796 |
| annual_predictions.parquet | 762 |
| chart_contract.parquet | 16 |

Candidate frontier baseline: 286 plotted candidates from 300 curated rows; 5 plotted Schiff specification benchmark anchor rows across 3 benchmark streams. The legacy Heavy RUC 20.50% H12 Schiff-style value is excluded from default pages.
