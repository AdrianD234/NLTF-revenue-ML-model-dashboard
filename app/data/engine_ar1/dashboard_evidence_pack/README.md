# Stage 1 Dashboard Evidence Pack v7 — vNext finalists

This is a Parquet-first evidence pack for the NLTF Stage 1 Governance Dashboard.

## Current finalists (vNext, production forward-scoreable)

- PED: `PED__VNEXT_SOLVED_CONVEX_TOP2` (two-component convex ensemble, saved fitted state)
- Light RUC: `dynamic_RESID_GBR_n150_d1_lr0.05_w36` (fixed two-stage recipe, unchanged)
- Heavy RUC: `HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4` (three-component convex ensemble, saved fitted state)

Default score basis is `schiff_paper_horizon_mean`. Operational metrics are retained in `operational_*` columns and scorecard tables.

## Headline metrics (paper-style horizon MAPE / paper annual MAPE)

- PED: 3.132% / 1.947%
- Light RUC: 5.363% / 1.274%
- Heavy RUC: 2.289% / 1.683%

All three streams beat the Schiff specification benchmark on the default basis. Do not mix paper-style and operational MAPE without labels.

## Key governance facts

- The PED and Heavy RUC finalists are vNext models selected by `pipeline/vnext_run.py` on the exact stored evidence keysets, with saved per-origin and production fitted state (parity replay delta 0.0; see `data/dashboard_evidence_pack_reproducibility/<stream>_vnext/forward_scorer_parity_audit.json`).
- The archived legacy finalists (`HEAVY_RUC__RECON_STATIC_REBUILT`, `PED__RESCUE_static_annual_weighted_top12_capnone`) remain historically reproducible only; the prior pack is preserved at `data/dashboard_evidence_pack_v6_backup`.
- The Light RUC finalist is a dynamic residual GBM accuracy challenger; operational annual MAPE remains a watch item.
- Diagnostics (DW, ADF, KPSS, Breusch-Pagan, White, ARCH, Jarque-Bera, cointegration, Mincer-Zarnowitz calibration) are computed on the vNext finalists' horizon-1 residuals with the same statsmodels battery and Pass/Watch/Fail rules as v6.

See `manifest.json` (`vnext_promotion`) for the promotion record and `docs/validation_report.md` for the canonical metric table.
