# PED inner HPO/static-solver governance audit

Created: 2026-06-09T12:07:43


## Finalist

- Finalist: `PED__RESCUE_static_annual_weighted_top12_capnone`

- Outer component: `PED__HPOREFINE_solver_static_convex_top18` with weight 100%.

- Max outer replay delta: `0.0`.

- Max evidence-pack delta: `0.0`.


## Inner HPO/static-solver layer

Found 6 inner HPO/static-solver weights. Weight sum = 1.000000000000.

Found inner component prediction rows: 3,708.

Max weighted inner replay delta vs outer component: 10.361948081296077.


## Governance interpretation

This audit proves the outer PED component-prediction replay and, if inner weights/predictions are present, the nested HPO/static-convex ensemble replay. It does not claim workbook-first refit reproducibility unless the inner component builders and fitted states are supplied.


## Scorecard summary

| stream   | stream_label       | model                                            | score_basis                     |   n_pairs |   n_origins |   n_horizons |   pooled_mape |   horizon_mean_mape |   bias_pct |   mape_h01 |   mape_h02 |   mape_h03 |   mape_h04 |   mape_h05 |   mape_h06 |   mape_h07 |   mape_h08 |   mape_h09 |   mape_h10 |   mape_h11 |   mape_h12 |
|:---------|:-------------------|:-------------------------------------------------|:--------------------------------|----------:|------------:|-------------:|--------------:|--------------------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|
| PED      | PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone | current_grid_operational_pooled |       606 |          56 |           12 |       2.47324 |             2.53072 |    1.51532 |    1.16263 |    1.51549 |    1.69388 |    1.8697  |    2.13408 |    2.42551 |    2.6485  |    2.83088 |    3.17968 |    3.39678 |    3.65998 |    3.85156 |
| PED      | PED VKT per capita | PED__RESCUE_static_annual_weighted_top12_capnone | schiff_paper_horizon_mean       |       126 |          24 |           12 |       2.65961 |             3.23714 |    1.97304 |    1.1728  |    1.73788 |    2.06423 |    2.08652 |    2.18618 |    2.28858 |    2.25953 |    2.34102 |    3.39862 |    4.54993 |    6.34023 |    8.4202  |


## Gaps

| gap                               | severity   | detail                                                                                                                                        |
|:----------------------------------|:-----------|:----------------------------------------------------------------------------------------------------------------------------------------------|
| feature_level_refit_not_attempted | medium     | This script audits parent-run outputs. Full workbook-first refit requires rerunning the inner component builders with retained fitted states. |