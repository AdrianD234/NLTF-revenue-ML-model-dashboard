# Evidence Pack Validation Report

## Canonical finalists
| stream_label       | model                                              |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   annual_bias_pct |
|:-------------------|:---------------------------------------------------|-----------------:|--------------:|---------------------:|------------------:|
| PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone   |          2.47324 |       2.38562 |            1.51532   |           1.61908 |
| Light RUC volume   | LIGHT_RUC__RESCUE_static_bias_penalty_top25_cap0p4 |          9.14755 |       5.9995  |            0.738125  |           0.34524 |
| Heavy RUC volume   | HEAVY_RUC__RECON_STATIC_REBUILT                    |          3.48437 |       3.01998 |           -0.0957778 |          -0.22056 |

## Pure Schiff benchmarks
| stream_label       | model                                              |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   annual_bias_pct |
|:-------------------|:---------------------------------------------------|-----------------:|--------------:|---------------------:|------------------:|
| PED VKT per capita | PED__schiff__SCHIFF_OLS__noylag__w64               |          3.08212 |       2.96576 |             0.762148 |          0.893912 |
| Light RUC volume   | LIGHT_RUC__schiff__SCHIFF_OLS__noylag__w40         |         11.5468  |       7.84368 |             3.15534  |          2.38094  |
| Heavy RUC volume   | HEAVY_RUC__schiff_no_lead__SCHIFF_OLS__noylag__w40 |         11.4826  |      11.7178  |            10.7112   |         11.18     |

## Scenario comparison
| stream_label       |   finalist_quarterly_mape |   schiff_quarterly_mape |   full_sample_qtr_gain_pp |   finalist_annual_mape |   schiff_annual_mape |   full_sample_annual_gain_pp |   paired_gain_pp |   paired_win_rate_pct | recommendation   |
|:-------------------|--------------------------:|------------------------:|--------------------------:|-----------------------:|---------------------:|-----------------------------:|-----------------:|----------------------:|:-----------------|
| Heavy RUC volume   |                   3.48437 |                11.4826  |                  7.99828  |                3.01998 |             11.7178  |                     8.69782  |         7.99828  |               64.1553 | Promote          |
| Light RUC volume   |                   9.14755 |                11.5468  |                  2.39924  |                5.9995  |              7.84368 |                     1.84418  |        -1.15912  |               50.5556 | Needs Stage 2    |
| PED VKT per capita |                   2.47324 |                 3.08212 |                  0.608873 |                2.38562 |              2.96576 |                     0.580133 |         0.608873 |               63.2013 | Promote          |

## Inventory
| file                                    |   rows |   columns |   size_bytes |
|:----------------------------------------|-------:|----------:|-------------:|
| annual_predictions.parquet              |    508 |        13 |        23376 |
| candidate_cone.parquet                  |    300 |       158 |       212471 |
| chart_contract.parquet                  |     16 |         4 |         4353 |
| diagnostic_acf.parquet                  |     39 |        11 |         8296 |
| diagnostic_pass_matrix.parquet          |     27 |         8 |         5679 |
| diagnostic_tests.parquet                |      6 |        37 |        23057 |
| ensemble_components.parquet             |      8 |        12 |         9402 |
| error_distribution.parquet              |   1482 |        14 |        54374 |
| finalists.parquet                       |      3 |        18 |        14690 |
| horizon_profiles.parquet                |     72 |        13 |        10920 |
| invalid_predictions_zero_actual.parquet |     24 |        31 |        20791 |
| paired_vs_schiff.parquet                |      3 |         7 |         5152 |
| residual_predictions.parquet            |   2886 |        31 |       114207 |
| scenario_comparison.parquet             |      3 |        15 |        10926 |
| schiff_benchmark.parquet                |      3 |        17 |        11197 |
| stress_horizon.parquet                  |     36 |        13 |         9678 |