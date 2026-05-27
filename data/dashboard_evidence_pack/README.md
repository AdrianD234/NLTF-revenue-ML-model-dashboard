# Stage 1 Dashboard Evidence Pack v6 — balanced frontier and reproducibility audit

This is a Parquet-first evidence pack for the NLTF Stage 1 Governance Dashboard.

## Current finalists

- PED: `PED__RESCUE_static_annual_weighted_top12_capnone`
- Light RUC: `dynamic_RESID_GBR_n150_d1_lr0.05_w36`
- Heavy RUC: `HEAVY_RUC__RECON_STATIC_REBUILT`

Default score basis is `schiff_paper_horizon_mean`. Operational metrics are retained in `operational_*` columns and scorecard tables.

## Key governance caveat

The Light RUC finalist is a dynamic residual GBM accuracy challenger. It improves the default paper-style horizon MAPE and operational quarterly MAPE, but operational annual MAPE remains a watch item.

## Default paper-style Light RUC metrics

- Paper horizon mean MAPE: 5.363%
- Paper pooled MAPE: 4.795%
- Paper annual MAPE: 1.274%
- Operational pooled MAPE: 8.273%
- Operational annual MAPE: 6.775%

Do not mix paper-style and operational MAPE without labels.


## v5 frontier note

The default Candidate Search Frontier now includes all three streams. Light RUC points are real challenger-search rows. PED and Heavy RUC include transparent visual frontier sample rows anchored to the current finalist and Schiff specification benchmark so the management chart shows a consistent all-stream frontier shape. These visual frontier sample rows are not used for finalist selection, KPI values, diagnostics, stress tests, scenario comparisons, or benchmark scoring.


## v6 frontier note

The default Candidate Search Frontier uses balanced all-stream frontier visualization samples anchored to true current finalist and Schiff specification benchmark points. These rows are for chart context only and must not feed finalist selection, KPIs, diagnostics, scenario comparisons or stress metrics.

## Reproducibility audit note

The pack now includes finalist reproducibility audit tables:

- `data/model_registry.parquet`
- `data/component_predictions.parquet`
- `data/model_coefficients.parquet`
- `data/feature_importance.parquet`
- `data/scenario_sensitivities.parquet`
- `data/shap_summary.parquet`

The audit report is `docs/reproducibility_report.md`. The artifact search evidence is `docs/reproducibility_artifact_search.md`. Heavy RUC component forecasts are loaded from the closure output and reconcile to the final weighted ensemble prediction. The report remains intentionally incomplete where source scripts, fitted model objects, origin-level coefficients, feature importances, SHAP values or executable scenario sensitivities are not present in the current evidence pack.
