# Stage 1 Dashboard Evidence Pack v4 — GBM Light RUC finalist

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
