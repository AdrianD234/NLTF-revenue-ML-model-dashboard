# Heavy RUC Finalist Reproducibility Audit

Finalist model: `HEAVY_RUC__RECON_STATIC_REBUILT`

## Executive result

This audit rebuilds the Heavy RUC finalist as a fixed weighted ensemble of four parent-run component prediction series.
It proves whether the stored component forecasts and weights exactly reproduce the finalist forecast and MAPE.

### Prediction comparison
| comparison                                | score_basis                     |   n_common_rows |   max_abs_pred_delta |   mean_abs_pred_delta |
|:------------------------------------------|:--------------------------------|----------------:|---------------------:|----------------------:|
| rebuilt_vs_evidence_scorecard_predictions | current_grid_operational_pooled |             438 |          3.57628e-07 |           8.19224e-08 |
| rebuilt_vs_evidence_scorecard_predictions | schiff_paper_horizon_mean       |             126 |          3.57628e-07 |           7.75806e-08 |

### Metric comparison
| score_basis                     |   rebuilt_quarterly_pooled_mape |   evidence_quarterly_pooled_mape |   delta_quarterly_pooled_mape |   rebuilt_horizon_mean_mape |   evidence_horizon_mean_mape |   delta_horizon_mean_mape |   rebuilt_bias |   evidence_bias |   delta_bias |
|:--------------------------------|--------------------------------:|---------------------------------:|------------------------------:|----------------------------:|-----------------------------:|--------------------------:|---------------:|----------------:|-------------:|
| current_grid_operational_pooled |                         3.48437 |                          3.48437 |                   4.44089e-16 |                     3.54152 |                      3.54152 |               8.88178e-16 |     -0.0957778 |      -0.0957778 | -2.77556e-16 |
| schiff_paper_horizon_mean       |                         2.59873 |                          2.59873 |                   0           |                     2.80947 |                      2.80947 |               4.44089e-16 |     -0.72733   |      -0.72733   |  0           |

## Rebuilt scorecard summary
| stream    | stream_label     | model                           | score_basis                     | eval_grid             |   n_quarterly_pairs |   n_origins |   quarterly_pooled_mape |   horizon_mean_mape |   quarterly_bias_pct |   quarterly_p90_ape |   mape_h01_04 |   mape_h05_08 |   mape_h09_12 |   mape_h01 |   mape_h02 |   mape_h03 |   mape_h04 |   mape_h05 |   mape_h06 |   mape_h07 |   mape_h08 |   mape_h09 |   mape_h10 |   mape_h11 |   mape_h12 |   n_annual_pairs |   annual_mape |   annual_bias_pct |   annual_p90_ape |
|:----------|:-----------------|:--------------------------------|:--------------------------------|:----------------------|--------------------:|------------:|------------------------:|--------------------:|---------------------:|--------------------:|--------------:|--------------:|--------------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------------:|--------------:|------------------:|-----------------:|
| HEAVY_RUC | Heavy RUC volume | HEAVY_RUC__RECON_STATIC_REBUILT | current_grid_operational_pooled | current_evidence_grid |                 438 |          42 |                 3.48437 |             3.54152 |           -0.0957778 |             6.50589 |       2.80249 |       3.54948 |       4.27261 |    2.7752  |    2.75288 |    2.91494 |    2.76693 |    3.34666 |    3.37262 |    3.60179 |    3.87683 |    4.24302 |    4.00745 |    4.3574  |    4.48255 |               82 |        2.7846 |         -0.266864 |          6.07333 |
| HEAVY_RUC | Heavy RUC volume | HEAVY_RUC__RECON_STATIC_REBUILT | schiff_paper_horizon_mean       | schiff_paper_grid     |                 126 |          24 |                 2.59873 |             2.80947 |           -0.72733   |             5.11088 |       2.25814 |       2.52334 |       3.64694 |    2.48374 |    2.42527 |    2.24832 |    1.87521 |    2.17481 |    2.45169 |    2.69145 |    2.77541 |    2.43598 |    3.01524 |    4.23028 |    4.90626 |               24 |        2.0611 |         -1.02909  |          4.54917 |

## Ensemble components
| component_model                                                                          |   component_weight | model_kind   | feature_set      |   window | include_target_lags   |
|:-----------------------------------------------------------------------------------------|-------------------:|:-------------|:-----------------|---------:|:----------------------|
| HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64                   |           0.469332 | elastic_net  | dynamic_no_leads |       64 | True                  |
| HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64         |           0.281844 | gbr          | schiff           |       64 | False                 |
| HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52 |           0.144373 | gbr          | dynamic_no_leads |       52 | True                  |
| HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40 |           0.104451 | gbr          | dynamic_no_leads |       40 | True                  |

## Reproducibility status

- Exact ensemble replay: supported if prediction deltas versus evidence/parent rows are near zero.
- Component refit from workbook: not attempted in this script; parent run did not retain fitted model artifacts or coefficients.
- Feature importance: component-level ensemble weights are emitted; internal GBM/ElasticNet feature importances require model-artifact refit.
