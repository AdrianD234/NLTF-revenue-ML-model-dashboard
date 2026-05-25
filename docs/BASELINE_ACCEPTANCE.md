# Baseline Acceptance

Status: BASELINE_ACCEPTED

Evidence pack root: `data/dashboard_evidence_pack`

## Accepted Current Finalists

| Stream | Quarterly MAPE | Annual MAPE |
| --- | ---: | ---: |
| PED VKT per capita | 2.47% | 2.39% |
| Light RUC volume | 9.15% | 6.00% |
| Heavy RUC volume | 3.48% | 3.02% |

## Pure Schiff Benchmarks

| Stream | Quarterly MAPE | Annual MAPE |
| --- | ---: | ---: |
| PED VKT per capita | 3.08% | 2.97% |
| Light RUC volume | 11.55% | 7.84% |
| Heavy RUC volume | 11.48% | 11.72% |

## Gain Semantics

Full-sample gains compare finalist MAPE with pure Schiff MAPE over their full evidence rows. Paired common-grid gain is separate. Light RUC has positive full-sample gain (+2.40 pp quarterly, +1.84 pp annual) but negative paired quarterly gain of about -1.16 pp with paired win rate about 50.56%.

## Evidence Pack Row Counts

| Table | Rows |
| --- | ---: |
| candidate_cone.parquet | 300 |
| finalists.parquet | 3 |
| schiff_benchmark.parquet | 3 |
| ensemble_components.parquet | 8 |
| residual_predictions.parquet | 2,886 |
| horizon_profiles.parquet | 72 |
| stress_horizon.parquet | 36 |
| scenario_comparison.parquet | 3 |
| diagnostic_tests.parquet | 6 |
| diagnostic_pass_matrix.parquet | 27 |
| diagnostic_acf.parquet | 39 |
| error_distribution.parquet | 1,482 |
| annual_predictions.parquet | 508 |
| chart_contract.parquet | 16 |

Candidate frontier baseline: 287 plotted candidates from 300 curated rows; 5 plotted pure-Schiff anchor rows across 3 benchmark streams.
