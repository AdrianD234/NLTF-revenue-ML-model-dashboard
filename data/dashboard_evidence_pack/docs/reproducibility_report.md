# Finalist Reproducibility Audit Report

Status: **INCOMPLETE**.

This pack adds traceability tables for the current finalists, Schiff benchmarks and ensemble components without changing the dashboard design.

- Evidence pack: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\data\dashboard_evidence_pack`
- Workbook: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\Master Copy revenue modelling workbook.xlsx`
- Workbook sheets used: `PED Inputs`, `Light RUC Inputs`, `Heavy RUC Inputs`
- Built at: `2026-05-27T05:28:05.375222+00:00`

## Added Tables

| File | Rows | Columns |
| --- | ---: | ---: |
| data/model_registry.parquet | 12 | 27 |
| data/component_predictions.parquet | 3504 | 18 |
| data/model_coefficients.parquet | 4 | 14 |
| data/feature_importance.parquet | 4 | 11 |
| data/scenario_sensitivities.parquet | 15 | 13 |
| data/shap_summary.parquet | 4 | 11 |

## Reconciliation

- Component prediction rows: 3,504
- Model registry rows: 12
- Maximum final-prediction delta versus evidence pack: 0
- Heavy RUC weighted-sum status: `verified`
- Heavy RUC weighted-sum rows: 564
- Heavy RUC weighted-sum max delta: 3.57627868652e-07
- Heavy RUC missing component rows: 0
- Registry rows marked incomplete: 10

| Stream | Score basis | Rebuilt pooled MAPE | Evidence pooled MAPE | Pooled delta | Rebuilt horizon mean MAPE | Evidence horizon mean MAPE | Horizon delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEAVY_RUC | current_grid_operational_pooled | 3.484368 | 3.484368 | 0 | 3.541524 | 3.541524 | 0 |
| HEAVY_RUC | schiff_paper_horizon_mean | 2.598732 | 2.598732 | 0 | 2.809473 | 2.809473 | 0 |
| LIGHT_RUC | current_grid_operational_pooled | 8.272972 | 8.272972 | 0 | 8.396299 | 8.396299 | 0 |
| LIGHT_RUC | schiff_paper_horizon_mean | 4.794903 | 4.794903 | 8.88178e-16 | 5.363207 | 5.363207 | 0 |
| PED | current_grid_operational_pooled | 2.473245 | 2.473245 | 0 | 2.530722 | 2.530722 | 4.44089e-16 |
| PED | schiff_paper_horizon_mean | 2.659610 | 2.659610 | 0 | 3.237144 | 3.237144 | 0 |

## Current Gaps

- Heavy RUC component forecast rows are loaded from the closure output and the weighted ensemble sum reconciles to the evidence-pack final predictions, but the fitted component objects are not yet rebuilt from workbook plus registry alone.
- Coefficient artifacts for ElasticNet/Ridge/OLS/Schiff workbook formulas are not present as fitted origin-level tables.
- GBM feature importance and SHAP artifacts are not present as fitted model outputs.
- Scenario sensitivities require executable fitted-model rebuilds and are therefore explicitly marked incomplete.

Do not claim full finalist reproducibility until every finalist has complete component traceability, fitted-model metadata and score reconciliation from rebuilt predictions.