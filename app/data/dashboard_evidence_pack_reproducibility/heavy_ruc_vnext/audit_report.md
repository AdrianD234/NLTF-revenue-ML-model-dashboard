# NLTF Stage 1 vNext pipeline audit report

Created: 2026-06-10T23:11:23.331484+00:00  
Pipeline version: vnext-pipeline-v1.0  

## Verdicts per stream

### PED VKT per capita

- Legacy finalist `PED__RESCUE_static_annual_weighted_top12_capnone`: **historically reproducible but NOT forward-scoreable** (parent fitted state unrecoverable; see reproducibility_gap_register.parquet).
- vNext finalist `PED__VNEXT_SOLVED_CONVEX_TOP2`: **production forecast-ready** (replaces the legacy finalist for forward scoring).
- Parity: state replay max delta 0.000e+00; recipe replay max delta 0.000e+00; tolerance 1e-06.
- current_grid_operational_pooled: pooled MAPE 2.664, horizon-mean MAPE 2.734, annual MAPE 2.541, bias +0.799pp, win-rate vs Schiff 78.9%, forecast R2 0.4864, calibration R2 0.5592.
- schiff_paper_horizon_mean: pooled MAPE 2.627, horizon-mean MAPE 3.132, annual MAPE 1.947, bias +1.608pp, win-rate vs Schiff 69.8%, forecast R2 0.5458, calibration R2 0.6681.

### Light RUC volume

- Status: **production forecast-ready** (incumbent fixed recipe, unchanged).
- The incumbent finalist `dynamic_RESID_GBR_n150_d1_lr0.05_w36` was already forward-scoreable; this pipeline additionally exports its saved production fitted state, training matrix, coefficients and importances for audit.

### Heavy RUC volume

- Legacy finalist `HEAVY_RUC__RECON_STATIC_REBUILT`: **historically reproducible but NOT forward-scoreable** (parent fitted state unrecoverable; see reproducibility_gap_register.parquet).
- vNext finalist `HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4`: **production forecast-ready** (replaces the legacy finalist for forward scoring).
- Parity: state replay max delta 0.000e+00; recipe replay max delta 0.000e+00; tolerance 1e-06.
- current_grid_operational_pooled: pooled MAPE 3.012, horizon-mean MAPE 3.045, annual MAPE 2.319, bias +0.510pp, win-rate vs Schiff 71.6%, forecast R2 0.4980, calibration R2 0.5209.
- schiff_paper_horizon_mean: pooled MAPE 2.311, horizon-mean MAPE 2.289, annual MAPE 1.683, bias -0.111pp, win-rate vs Schiff 65.1%, forecast R2 0.4768, calibration R2 0.5352.

## Governance basis

- Canonical input basis: `data/model_input_history` (actuals verified equal to the governed evidence-pack actuals; schema-equal to the forecast input template).
- Evaluation grids: the exact stored (origin, target) keysets of the governed evidence pack for both score bases, guaranteeing comparability with incumbent finalists and the Schiff specification benchmark.
- All fitted estimators, training matrices, prediction feature rows, feature column order, target transform, lag-recursion policy, seeds and training windows are saved under each stream's `*_vnext` reproducibility pack.
- Forward scoring runs a production-state gate on every call: archived training-fit predictions must replay from saved state within 1e-6 or the stream emits a governed gap.
- The historical evidence pack at `data/dashboard_evidence_pack` was not modified.

## What is and is not reproducible

| Stream | Score replay | Historical replay | Production forward scoring |
|---|---|---|---|
| PED legacy | yes | yes (outer exact) | no - inner fitted state lost |
| PED vNext | yes | yes (saved state) | yes (parity-gated) |
| Light RUC | yes | yes | yes (fixed recipe) |
| Heavy RUC legacy | yes | yes (stored weighted replay) | no - C3/C4 parent state lost |
| Heavy RUC vNext | yes | yes (saved state) | yes (parity-gated) |
