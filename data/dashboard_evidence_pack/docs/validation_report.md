# Dual Scorecard Evidence Pack v3 Validation Report

Default score basis: schiff_paper_horizon_mean. Operational pooled metrics are retained in parallel.

## Finalists (default paper-style metrics)

| stream_label       | model                                            |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   operational_pooled_mape |   operational_annual_mape |   paper_horizon_mean_mape |   paper_annual_mape |
|:-------------------|:-------------------------------------------------|-----------------:|--------------:|---------------------:|--------------------------:|--------------------------:|--------------------------:|--------------------:|
| PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone |          3.23714 |       2.03329 |             1.97304  |                   2.47324 |                   2.23965 |                   3.23714 |             2.03329 |
| Light RUC volume   | schiff_w36_OLS                                   |          6.06515 |       3.42519 |             0.622598 |                   7.74395 |                   6.28164 |                   6.06515 |             3.42519 |
| Heavy RUC volume   | HEAVY_RUC__RECON_STATIC_REBUILT                  |          2.80947 |       2.0611  |            -0.72733  |                   3.48437 |                   2.7846  |                   2.80947 |             2.0611  |

## Schiff benchmarks (default paper-style metrics)

| stream_label       | model                                |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   operational_pooled_mape |   operational_annual_mape |   paper_horizon_mean_mape |   paper_annual_mape |
|:-------------------|:-------------------------------------|-----------------:|--------------:|---------------------:|--------------------------:|--------------------------:|--------------------------:|--------------------:|
| PED VKT per capita | PED__SCHIFF_SPEC_FROM_WORKBOOK       |          4.67492 |       3.58573 |             2.82902  |                   4.16591 |                   4.20662 |                   4.67492 |             3.58573 |
| Light RUC volume   | LIGHT_RUC__SCHIFF_SPEC_FROM_WORKBOOK |          8.5214  |       2.702   |             0.424122 |                   9.52717 |                   5.54748 |                   8.5214  |             2.702   |
| Heavy RUC volume   | HEAVY_RUC__SCHIFF_SPEC_FROM_WORKBOOK |          8.76165 |       8.87951 |             7.79582  |                   7.8002  |                   8.11277 |                   8.76165 |             8.87951 |

## Scenario comparison (default paper-style)

| stream_label       |   finalist_quarterly_mape |   schiff_quarterly_mape |   full_sample_qtr_gain_pp |   finalist_annual_mape |   schiff_annual_mape |   full_sample_annual_gain_pp |   paired_win_rate_pct | recommendation   |
|:-------------------|--------------------------:|------------------------:|--------------------------:|-----------------------:|---------------------:|-----------------------------:|----------------------:|:-----------------|
| PED VKT per capita |                   3.23714 |                 4.67492 |                   1.43777 |                2.03329 |              3.58573 |                     1.55244  |               69.0476 | Promote          |
| Light RUC volume   |                   6.06515 |                 8.5214  |                   2.45625 |                3.42519 |              2.702   |                    -0.723188 |               55.5556 | Promote          |
| Heavy RUC volume   |                   2.80947 |                 8.76165 |                   5.95218 |                2.0611  |              8.87951 |                     6.81841  |               62.6984 | Promote          |

## Light RUC top candidates from governance search

| model                            |   operational_n |   operational_pooled_mape |   operational_horizon_mean_mape |   operational_bias_pct |   operational_annual_mape |   operational_h09_12_mape |   paper_n |   paper_horizon_mean_mape |   paper_pooled_mape |   paper_bias_pct |   paper_annual_mape |   paper_h09_12_mape |   decision_score |
|:---------------------------------|----------------:|--------------------------:|--------------------------------:|-----------------------:|--------------------------:|--------------------------:|----------:|--------------------------:|--------------------:|-----------------:|--------------------:|--------------------:|-----------------:|
| schiff_w36_OLS                   |             438 |                   7.74395 |                         7.85551 |                1.88291 |                   6.28164 |                   9.16967 |       126 |                   6.06515 |             5.55418 |       0.622598   |             3.42519 |             8.43452 |          16.196  |
| schiff_w36_Ridge_a0.001          |             438 |                   7.74438 |                         7.85593 |                1.88015 |                   6.28173 |                   9.16984 |       126 |                   6.06513 |             5.55457 |       0.615986   |             3.42907 |             8.43239 |          16.1961 |
| schiff_w36_Ridge_a0.01           |             438 |                   7.7483  |                         7.85976 |                1.85535 |                   6.28262 |                   9.17171 |       126 |                   6.06476 |             5.55785 |       0.556903   |             3.46376 |             8.41307 |          16.1975 |
| schiff_w36_Ridge_a0.1            |             438 |                   7.78221 |                         7.89257 |                1.61755 |                   6.29875 |                   9.18337 |       126 |                   6.05151 |             5.57937 |       0.00385628 |             3.79044 |             8.22406 |          16.2    |
| ENSEMBLE_dual_top8_median        |             438 |                   7.69992 |                         7.8199  |                1.47172 |                   5.99249 |                   9.25558 |       126 |                   6.33857 |             5.60724 |      -0.0288123  |             3.44641 |             9.54577 |          16.283  |
| ENSEMBLE_dual_top8_mean          |             438 |                   7.7061  |                         7.82544 |                1.50218 |                   6.01252 |                   9.26128 |       126 |                   6.37512 |             5.63603 |       0.0405436  |             3.52711 |             9.64869 |          16.3358 |
| ENSEMBLE_dual_top5_mean          |             438 |                   7.69204 |                         7.81372 |                1.50601 |                   5.96663 |                   9.28691 |       126 |                   6.45795 |             5.65789 |       0.111449   |             3.43445 |             9.98471 |          16.3889 |
| ENSEMBLE_dual_top12_median       |             438 |                   7.74261 |                         7.86396 |                1.45259 |                   5.95285 |                   9.31183 |       126 |                   6.44724 |             5.70929 |      -0.216624   |             3.49603 |             9.68682 |          16.4186 |
| ENSEMBLE_dual_top12_mean         |             438 |                   7.7482  |                         7.8694  |                1.48301 |                   5.9804  |                   9.32704 |       126 |                   6.44209 |             5.70756 |      -0.131036   |             3.53095 |             9.69515 |          16.4317 |
| schiff_w36_Elastic_a0.001_l10.15 |             438 |                   7.83884 |                         7.95397 |                1.75533 |                   6.21425 |                   9.31079 |       126 |                   6.24334 |             5.73353 |       0.0939786  |             3.54447 |             8.59761 |          16.4327 |