# Evidence Pack Validation Report

## Version
v7 vNext-finalists evidence pack. Default score basis: schiff_paper_horizon_mean.
Promoted by `scripts/promote_vnext_to_evidence_pack.py`; every rebuild formula was
verified to reproduce the stored v6 values exactly before replacement (--check mode).

## Canonical finalists

| stream_label       | model                                |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   annual_bias_pct |   operational_pooled_mape |   operational_annual_mape |
|:-------------------|:-------------------------------------|-----------------:|--------------:|---------------------:|------------------:|--------------------------:|--------------------------:|
| PED VKT per capita | PED__VNEXT_SOLVED_CONVEX_TOP2        |          3.13166 |       1.94685 |              1.60759 |           1.43453 |                   2.66414 |                   2.54063 |
| Light RUC volume   | dynamic_RESID_GBR_n150_d1_lr0.05_w36 |          5.36321 |       1.27377 |              0.83689 |          -1.02345 |                   8.27297 |                   6.77491 |
| Heavy RUC volume   | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4  |          2.28872 |       1.68272 |             -0.11126 |          -0.22005 |                   3.01185 |                   2.31949 |

## Schiff specification comparison (paper basis)

| stream_label       |   finalist_quarterly_mape |   schiff_quarterly_mape |   full_sample_qtr_gain_pp |   paired_win_rate_pct | recommendation   |
|:-------------------|--------------------------:|------------------------:|--------------------------:|----------------------:|:-----------------|
| PED VKT per capita |                   3.13166 |                 4.67492 |                   1.54325 |               69.8413 | Promote          |
| Light RUC volume   |                   5.36321 |                 8.5214  |                   3.15819 |               62.6984 | Promote          |
| Heavy RUC volume   |                   2.28872 |                 8.76165 |                   6.47294 |               65.0794 | Promote          |

## Validation chain

- Row-count invariants preserved (scorecard_predictions 3648, candidate_cone 400, pass matrix 27).
- Actuals identical to the canonical model-input history (max delta 0.0).
- vNext finalist predictions replay exactly from saved fitted state (state and recipe parity 0.0).
- Diagnostics recomputed with the verified statsmodels battery on h1 residuals.
- Validators: `scripts/validate_dashboard_data.py`, `scripts/validate_chart_sources.py`,
  `scripts/validate_semantic_labels.py`, `scripts/validate_reproducibility_audit_pack.py`.
