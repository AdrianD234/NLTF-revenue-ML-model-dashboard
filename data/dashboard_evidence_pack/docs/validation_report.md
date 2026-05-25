# Schiff Specification v2 Evidence Pack Validation Report

## Schiff specification benchmark rows

| stream    | stream_label       | role                           | model                                      |   n_quarterly_pairs |   quarterly_mape |   quarterly_bias_pct |   quarterly_p90_ape |   n_annual_pairs |   annual_mape |   annual_bias_pct |   annual_p90_ape | scenario   | is_current_recommended   | is_pure_schiff   | model_short                               | candidate_uid    |
|:----------|:-------------------|:-------------------------------|:-------------------------------------------|--------------------:|-----------------:|---------------------:|--------------------:|-----------------:|--------------:|------------------:|-----------------:|:-----------|:-------------------------|:-----------------|:------------------------------------------|:-----------------|
| HEAVY_RUC | Heavy RUC volume   | Schiff specification benchmark | HEAVY_RUC__SCHIFF_SPEC_FINAL_AR1_EXPANDING |                 426 |          7.8002  |              7.5664  |             19.2109 |               73 |       8.11277 |           8.02235 |          23.1224 | Schiff     | False                    | True             | Heavy RUC Schiff spec final AR1 expanding | a43b1640212ea56b |
| LIGHT_RUC | Light RUC volume   | Schiff specification benchmark | LIGHT_RUC__SCHIFF_SPEC_FINAL_OLS_EXPANDING |                 426 |          8.41294 |              2.06645 |             17.3607 |               80 |       5.00057 |           1.11093 |          10.5426 | Schiff     | False                    | True             | Light RUC Schiff spec final OLS expanding | 1587a79c479e00a0 |
| PED       | PED VKT per capita | Schiff specification benchmark | PED__SCHIFF_SPEC_FINAL_OLS_EXPANDING       |                 606 |          4.09157 |              1.14917 |             10.8345 |              114 |       4.13201 |           1.28115 |          10.9017 | Schiff     | False                    | True             | PED Schiff spec final OLS expanding       | 1d59e72762e8e156 |


## Scenario comparison

| stream    | stream_label       |   finalist_quarterly_mape |   schiff_quarterly_mape |   finalist_annual_mape |   schiff_annual_mape |   paired_common_pairs |   paired_finalist_mape |   paired_schiff_mape |   paired_gain_pp |   paired_win_rate_pct |   full_sample_qtr_gain_pp |   full_sample_annual_gain_pp | recommendation   | calculation_basis                                                                                                 |
|:----------|:-------------------|--------------------------:|------------------------:|-----------------------:|---------------------:|----------------------:|-----------------------:|---------------------:|-----------------:|----------------------:|--------------------------:|-----------------------------:|:-----------------|:------------------------------------------------------------------------------------------------------------------|
| HEAVY_RUC | Heavy RUC volume   |                   3.48437 |                 7.8002  |                3.01998 |              8.11277 |                   426 |                3.47269 |              7.8002  |         4.32751  |               65.493  |                  4.31583  |                     5.09279  | Promote          | Full-sample gains from Finalist versus Schiff specification benchmark; paired metrics from common forecast pairs. |
| LIGHT_RUC | Light RUC volume   |                   9.14755 |                 8.41294 |                5.9995  |              5.00057 |                   426 |                9.17423 |              8.41294 |        -0.761294 |               46.7136 |                 -0.734606 |                    -0.998927 | Needs Stage 2    | Full-sample gains from Finalist versus Schiff specification benchmark; paired metrics from common forecast pairs. |
| PED       | PED VKT per capita |                   2.47324 |                 4.09157 |                2.38562 |              4.13201 |                   606 |                2.47324 |              4.09157 |         1.61833  |               76.7327 |                  1.61833  |                     1.74639  | Promote          | Full-sample gains from Finalist versus Schiff specification benchmark; paired metrics from common forecast pairs. |


## Data inventory

| file                                    |   rows |   columns |   size_bytes |
|:----------------------------------------|-------:|----------:|-------------:|
| annual_predictions.parquet              |    545 |        13 |        24888 |
| candidate_cone.parquet                  |    300 |       158 |       213154 |
| chart_contract.parquet                  |     16 |         4 |         4353 |
| diagnostic_acf.parquet                  |     39 |        11 |         8296 |
| diagnostic_pass_matrix.parquet          |     27 |         8 |         5679 |
| diagnostic_tests.parquet                |      6 |        37 |        23073 |
| ensemble_components.parquet             |      8 |        12 |         9402 |
| error_distribution.parquet              |   2940 |        14 |        96798 |
| finalists.parquet                       |      3 |        18 |        14690 |
| horizon_profiles.parquet                |     72 |        13 |        10939 |
| invalid_predictions_zero_actual.parquet |     24 |        31 |        20791 |
| paired_vs_schiff.parquet                |      3 |         7 |         5133 |
| residual_predictions.parquet            |   2940 |        31 |       129683 |
| scenario_comparison.parquet             |      3 |        15 |        11034 |
| schiff_benchmark.parquet                |      3 |        17 |        11241 |
| stress_horizon.parquet                  |     36 |        13 |         9879 |