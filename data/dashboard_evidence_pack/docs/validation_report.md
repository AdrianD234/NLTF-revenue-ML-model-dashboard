# Evidence Pack Validation Report

## Version
v6 GBM Light RUC evidence pack with balanced all-stream frontier. Default score basis: schiff_paper_horizon_mean.

## Canonical finalists

| stream_label       | model                                            |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   annual_bias_pct |   operational_pooled_mape |   operational_annual_mape |
|:-------------------|:-------------------------------------------------|-----------------:|--------------:|---------------------:|------------------:|--------------------------:|--------------------------:|
| PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone |          3.23714 |       2.03329 |             1.97304  |           1.82749 |                   2.47324 |                   2.23965 |
| Light RUC volume   | dynamic_RESID_GBR_n150_d1_lr0.05_w36             |          5.36321 |       1.27377 |             0.836891 |          -1.02345 |                   8.27297 |                   6.77491 |
| Heavy RUC volume   | HEAVY_RUC__RECON_STATIC_REBUILT                  |          2.80947 |       2.0611  |            -0.72733  |          -1.02909 |                   3.48437 |                   2.7846  |

## Schiff specification benchmarks

| stream_label       | model                                |   quarterly_mape |   annual_mape |   quarterly_bias_pct |   annual_bias_pct |
|:-------------------|:-------------------------------------|-----------------:|--------------:|---------------------:|------------------:|
| PED VKT per capita | PED__SCHIFF_SPEC_FROM_WORKBOOK       |          4.67492 |       3.58573 |             2.82902  |           2.84775 |
| Light RUC volume   | LIGHT_RUC__SCHIFF_SPEC_FROM_WORKBOOK |          8.5214  |       2.702   |             0.424122 |          -1.25121 |
| Heavy RUC volume   | HEAVY_RUC__SCHIFF_SPEC_FROM_WORKBOOK |          8.76165 |       8.87951 |             7.79582  |           8.73278 |

## Scenario comparison

| stream_label       |   finalist_quarterly_mape |   schiff_quarterly_mape |   full_sample_qtr_gain_pp |   finalist_annual_mape |   schiff_annual_mape |   full_sample_annual_gain_pp |   paired_gain_pp |   paired_win_rate_pct | recommendation   |
|:-------------------|--------------------------:|------------------------:|--------------------------:|-----------------------:|---------------------:|-----------------------------:|-----------------:|----------------------:|:-----------------|
| PED VKT per capita |                   3.23714 |                 4.67492 |                   1.43777 |                2.03329 |              3.58573 |                      1.55244 |          1.21446 |               69.0476 | Promote          |
| Light RUC volume   |                   5.36321 |                 8.5214  |                   3.15819 |                1.27377 |              2.702   |                      1.42823 |          2.93221 |               62.6984 | Promote          |
| Heavy RUC volume   |                   2.80947 |                 8.76165 |                   5.95218 |                2.0611  |              8.87951 |                      6.81841 |          5.6418  |               62.6984 | Promote          |

## Light RUC selected finalist caveat
The Light RUC finalist is an accuracy-challenger dynamic residual GBM. It improves paper-style and operational quarterly MAPE against the Schiff specification benchmark, but operational annual MAPE is weaker than the Schiff specification benchmark and should remain visible as an annual-watch caveat.

## Inventory

| file                                    |   rows |   columns |   size_bytes |
|:----------------------------------------|-------:|----------:|-------------:|
| annual_predictions.parquet              |    130 |        17 |        14956 |
| candidate_cone.parquet                  |    400 |        54 |       69336 |
| chart_contract.parquet                  |     16 |         5 |         5520 |
| diagnostic_acf.parquet                  |     39 |        12 |         9137 |
| diagnostic_pass_matrix.parquet          |     27 |         9 |         6406 |
| diagnostic_tests.parquet                |      6 |        38 |        23770 |
| ensemble_components.parquet             |      6 |        15 |        11241 |
| error_distribution.parquet              |    756 |        23 |        38554 |
| finalists.parquet                       |      3 |        33 |        25604 |
| horizon_profiles.parquet                |     72 |        16 |        12424 |
| invalid_predictions_zero_actual.parquet |     24 |        31 |        20791 |
| light_ruc_candidate_scorecard.parquet   |    887 |        14 |        98060 |
| paired_vs_schiff.parquet                |      3 |        22 |        15805 |
| residual_predictions.parquet            |    756 |        22 |        36896 |
| scenario_comparison.parquet             |      3 |        19 |        14102 |
| schiff_benchmark.parquet                |      3 |        31 |        20540 |
| scorecard_annual_metric_summary.parquet |     12 |         7 |         5264 |
| scorecard_annual_predictions.parquet    |    662 |        17 |        28632 |
| scorecard_horizon_profiles.parquet      |    144 |        16 |        14003 |
| scorecard_model_summary.parquet         |     12 |        33 |        22973 |
| scorecard_predictions.parquet           |   3648 |        22 |       107000 |
| scorecard_stress_horizon.parquet        |     72 |        15 |        11860 |
| stress_horizon.parquet                  |     36 |        15 |        10915 |


## v5 Candidate Frontier Coverage

Default plotted candidate rows: 400.

Plotted rows by stream: {'Heavy RUC volume': 102, 'Light RUC volume': 196, 'PED VKT per capita': 102}.

Light RUC rows are challenger-search candidates. PED and Heavy RUC include transparent visual frontier sample rows for all-stream chart continuity. These rows are not used for model selection, KPI metrics, diagnostics or scenario scoring.


## Balanced frontier note
The candidate_cone table contains balanced all-stream frontier visualization samples plus true finalist and Schiff specification anchors. Samples are explicitly tagged and excluded from governance scoring.
