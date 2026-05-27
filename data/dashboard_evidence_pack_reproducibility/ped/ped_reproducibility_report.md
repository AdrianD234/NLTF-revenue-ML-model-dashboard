# PED Finalist Reproducibility Audit

Model: `PED__RESCUE_static_annual_weighted_top12_capnone`
Outer component: `hpo::PED__HPOREFINE_solver_static_convex_top18` with 100% weight.

## Result

| score_basis                     |   n_rows |   max_abs_pred_delta_vs_evidence |   mean_abs_pred_delta_vs_evidence |   max_abs_pred_delta_vs_parent_final |   mean_abs_pred_delta_vs_parent_final | stream   | stream_label       | model                                            |   n_pairs |   n_origins |   n_horizons |   pooled_mape |   horizon_mean_mape |   bias_pct |   mape_h01 |   mape_h02 |   mape_h03 |   mape_h04 |   mape_h05 |   mape_h06 |   mape_h07 |   mape_h08 |   mape_h09 |   mape_h10 |   mape_h11 |   mape_h12 |
|:--------------------------------|---------:|---------------------------------:|----------------------------------:|-------------------------------------:|--------------------------------------:|:---------|:-------------------|:-------------------------------------------------|----------:|------------:|-------------:|--------------:|--------------------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|
| current_grid_operational_pooled |      606 |                                0 |                                 0 |                                    0 |                                     0 | PED      | PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone |       606 |          56 |           12 |       2.47324 |             2.53072 |    1.51532 |    1.16263 |    1.51549 |    1.69388 |    1.8697  |    2.13408 |    2.42551 |    2.6485  |    2.83088 |    3.17968 |    3.39678 |    3.65998 |    3.85156 |
| schiff_paper_horizon_mean       |      126 |                                0 |                                 0 |                                    0 |                                     0 | PED      | PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone |       126 |          24 |           12 |       2.65961 |             3.23714 |    1.97304 |    1.1728  |    1.73788 |    2.06423 |    2.08652 |    2.18618 |    2.28858 |    2.25953 |    2.34102 |    3.39862 |    4.54993 |    6.34023 |    8.4202  |

## Interpretation

The PED finalist is exactly score- and prediction-reproducible from the parent candidate-rescue output rows. 
This proves the final packed predictions and MAPEs can be replayed. It does not yet prove first-principles model-build reproducibility of the nested HPO/static-convex component from workbook inputs alone.

## Known limitation

The parent HPO run provides the final HPO-refined component prediction and nested weights, but not all fitted inner model states/coefficient paths. Scenario sensitivities and feature-level explanations therefore remain incomplete unless the nested HPO components are replayed from their original build scripts.