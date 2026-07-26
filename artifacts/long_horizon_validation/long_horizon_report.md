# Long-horizon rolling-origin evaluation

Fixed finalists scored to H20 on the committed input history.

## What this is

* Actual-driver: exogenous inputs at each target quarter are the observed
  values, so this isolates model degradation with horizon and understates
  real forward error, which also carries driver-forecast error.
* Origin-correct: every origin refits on rows at or before that origin.
  PED and Heavy RUC use recursive predicted target lags; Light RUC has no
  target lags. Realized future target values never enter a lagged
  dependent variable. Origin/target ordering is asserted, not assumed -
  see `_assert_no_future_target_leakage`.
* Signed error: `(forecast - actual) / actual * 100; positive = overprediction`.
* Prediction-interval coverage is not reported: the production scorer
  publishes no governed interval, and manufacturing one would be worse
  than its absence.

## Governed horizon support states

| State | Meaning |
|---|---|
| H1-H12 | Backtest-supported range of the committed evidence pack. |
| H13-H20 | Extended conditional evidence from this script; thinner samples, not validated to the short-term standard. |
| H21+ | No extended evaluation evidence; unvalidated long-range extrapolation. |

## All available origins, all targets

Sample size falls with horizon, so H1 and H20 describe different origin
sets. This mixes a horizon effect with a composition effect - read the
balanced cohort below before concluding.

| stream | horizon | horizon_support_state | n_observations | n_origins | first_target_period | last_target_period | mape_pct | wape_pct | rmse | signed_mean_error_pct | revenue_equivalent_signed_error_nzd_m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HEAVY_RUC | 1 | H1-H12 | 42 | 42 | 2015Q3 | 2025Q4 | 2.400 | 2.401 | 29175246.634 | 0.011 | 0.117 |
| HEAVY_RUC | 2 | H1-H12 | 41 | 41 | 2015Q4 | 2025Q4 | 2.423 | 2.413 | 29334822.955 | 0.178 | 1.971 |
| HEAVY_RUC | 3 | H1-H12 | 40 | 40 | 2016Q1 | 2025Q4 | 2.790 | 2.776 | 32568707.064 | 0.242 | 2.691 |
| HEAVY_RUC | 4 | H1-H12 | 39 | 39 | 2016Q2 | 2025Q4 | 2.670 | 2.634 | 32073466.190 | 0.238 | 2.646 |
| HEAVY_RUC | 5 | H1-H12 | 38 | 38 | 2016Q3 | 2025Q4 | 3.009 | 2.968 | 36519546.780 | 0.183 | 2.030 |
| HEAVY_RUC | 6 | H1-H12 | 37 | 37 | 2016Q4 | 2025Q4 | 3.053 | 2.998 | 36763770.381 | 0.247 | 2.742 |
| HEAVY_RUC | 7 | H1-H12 | 36 | 36 | 2017Q1 | 2025Q4 | 3.224 | 3.164 | 38841385.120 | 0.414 | 4.595 |
| HEAVY_RUC | 8 | H1-H12 | 35 | 35 | 2017Q2 | 2025Q4 | 3.337 | 3.255 | 41670712.100 | 0.661 | 7.342 |
| HEAVY_RUC | 9 | H1-H12 | 34 | 34 | 2017Q3 | 2025Q4 | 3.399 | 3.314 | 42015684.418 | 0.809 | 8.985 |
| HEAVY_RUC | 10 | H1-H12 | 33 | 33 | 2017Q4 | 2025Q4 | 3.412 | 3.321 | 42913127.291 | 0.968 | 10.740 |
| HEAVY_RUC | 11 | H1-H12 | 32 | 32 | 2018Q1 | 2025Q4 | 3.428 | 3.325 | 42293191.426 | 1.189 | 13.201 |
| HEAVY_RUC | 12 | H1-H12 | 31 | 31 | 2018Q2 | 2025Q4 | 3.399 | 3.292 | 42091300.309 | 1.446 | 16.052 |
| HEAVY_RUC | 13 | H13-H20 | 30 | 30 | 2018Q3 | 2025Q4 | 3.294 | 3.194 | 40770806.995 | 1.679 | 18.631 |
| HEAVY_RUC | 14 | H13-H20 | 29 | 29 | 2018Q4 | 2025Q4 | 3.223 | 3.132 | 40955951.322 | 1.815 | 20.142 |
| HEAVY_RUC | 15 | H13-H20 | 28 | 28 | 2019Q1 | 2025Q4 | 3.284 | 3.176 | 41584954.858 | 2.022 | 22.447 |
| HEAVY_RUC | 16 | H13-H20 | 27 | 27 | 2019Q2 | 2025Q4 | 3.514 | 3.418 | 42772373.962 | 2.272 | 25.215 |
| HEAVY_RUC | 17 | H13-H20 | 26 | 26 | 2019Q3 | 2025Q4 | 3.930 | 3.819 | 48160460.276 | 2.439 | 27.072 |
| HEAVY_RUC | 18 | H13-H20 | 25 | 25 | 2019Q4 | 2025Q4 | 4.382 | 4.272 | 50715106.755 | 2.548 | 28.278 |
| HEAVY_RUC | 19 | H13-H20 | 24 | 24 | 2020Q1 | 2025Q4 | 4.425 | 4.287 | 55709454.575 | 2.723 | 30.223 |
| HEAVY_RUC | 20 | H13-H20 | 23 | 23 | 2020Q2 | 2025Q4 | 4.426 | 4.288 | 54534843.770 | 2.721 | 30.197 |
| LIGHT_RUC | 1 | H1-H12 | 30 | 30 | 2018Q3 | 2025Q4 | 7.387 | 7.373 | 335256562.194 | 0.823 | 6.840 |
| LIGHT_RUC | 2 | H1-H12 | 29 | 29 | 2018Q4 | 2025Q4 | 9.708 | 9.833 | 424101259.629 | 1.984 | 16.490 |
| LIGHT_RUC | 3 | H1-H12 | 28 | 28 | 2019Q1 | 2025Q4 | 8.647 | 8.914 | 385706611.652 | 2.166 | 18.003 |
| LIGHT_RUC | 4 | H1-H12 | 27 | 27 | 2019Q2 | 2025Q4 | 8.009 | 7.985 | 304963513.717 | 2.899 | 24.092 |
| LIGHT_RUC | 5 | H1-H12 | 26 | 26 | 2019Q3 | 2025Q4 | 9.236 | 9.135 | 344946931.776 | 3.803 | 31.601 |
| LIGHT_RUC | 6 | H1-H12 | 25 | 25 | 2019Q4 | 2025Q4 | 10.031 | 9.899 | 378784652.351 | 4.064 | 33.768 |
| LIGHT_RUC | 7 | H1-H12 | 24 | 24 | 2020Q1 | 2025Q4 | 11.053 | 10.995 | 404055162.522 | 4.462 | 37.082 |
| LIGHT_RUC | 8 | H1-H12 | 23 | 23 | 2020Q2 | 2025Q4 | 11.350 | 11.376 | 421792510.129 | 4.344 | 36.101 |
| LIGHT_RUC | 9 | H1-H12 | 22 | 22 | 2020Q3 | 2025Q4 | 11.011 | 11.042 | 409568877.633 | 4.690 | 38.973 |
| LIGHT_RUC | 10 | H1-H12 | 21 | 21 | 2020Q4 | 2025Q4 | 10.756 | 10.701 | 411608597.400 | 4.694 | 39.010 |
| LIGHT_RUC | 11 | H1-H12 | 20 | 20 | 2021Q1 | 2025Q4 | 11.910 | 11.924 | 445071874.507 | 4.535 | 37.688 |
| LIGHT_RUC | 12 | H1-H12 | 19 | 19 | 2021Q2 | 2025Q4 | 12.295 | 12.142 | 437737188.902 | 5.059 | 42.035 |
| LIGHT_RUC | 13 | H13-H20 | 18 | 18 | 2021Q3 | 2025Q4 | 13.869 | 13.445 | 476068437.481 | 6.898 | 57.320 |
| LIGHT_RUC | 14 | H13-H20 | 17 | 17 | 2021Q4 | 2025Q4 | 13.537 | 12.937 | 490021342.436 | 7.812 | 64.918 |
| LIGHT_RUC | 15 | H13-H20 | 16 | 16 | 2022Q1 | 2025Q4 | 13.062 | 12.360 | 480699216.788 | 7.652 | 63.586 |
| LIGHT_RUC | 16 | H13-H20 | 15 | 15 | 2022Q2 | 2025Q4 | 15.350 | 14.118 | 566071681.985 | 9.419 | 78.273 |
| LIGHT_RUC | 17 | H13-H20 | 14 | 14 | 2022Q3 | 2025Q4 | 15.890 | 14.226 | 571439421.044 | 12.894 | 107.149 |
| LIGHT_RUC | 18 | H13-H20 | 13 | 13 | 2022Q4 | 2025Q4 | 16.006 | 14.180 | 580246811.950 | 13.401 | 111.359 |
| LIGHT_RUC | 19 | H13-H20 | 12 | 12 | 2023Q1 | 2025Q4 | 16.937 | 14.929 | 598851595.168 | 14.052 | 116.770 |
| LIGHT_RUC | 20 | H13-H20 | 11 | 11 | 2023Q2 | 2025Q4 | 19.822 | 17.747 | 667849970.453 | 17.242 | 143.277 |
| PED | 1 | H1-H12 | 56 | 56 | 2012Q1 | 2025Q4 | 1.087 | 1.059 | 24.570 | -0.100 | -2.004 |
| PED | 2 | H1-H12 | 55 | 55 | 2012Q2 | 2025Q4 | 1.483 | 1.440 | 34.888 | 0.067 | 1.333 |
| PED | 3 | H1-H12 | 54 | 54 | 2012Q3 | 2025Q4 | 1.676 | 1.624 | 41.141 | 0.275 | 5.491 |
| PED | 4 | H1-H12 | 53 | 53 | 2012Q4 | 2025Q4 | 1.955 | 1.891 | 47.264 | 0.490 | 9.789 |
| PED | 5 | H1-H12 | 52 | 52 | 2013Q1 | 2025Q4 | 2.350 | 2.276 | 54.306 | 0.661 | 13.203 |
| PED | 6 | H1-H12 | 51 | 51 | 2013Q2 | 2025Q4 | 2.598 | 2.518 | 59.263 | 0.770 | 15.375 |
| PED | 7 | H1-H12 | 50 | 50 | 2013Q3 | 2025Q4 | 2.818 | 2.731 | 64.602 | 0.879 | 17.552 |
| PED | 8 | H1-H12 | 49 | 49 | 2013Q4 | 2025Q4 | 3.092 | 2.994 | 70.387 | 1.000 | 19.969 |
| PED | 9 | H1-H12 | 48 | 48 | 2014Q1 | 2025Q4 | 3.515 | 3.403 | 76.801 | 1.169 | 23.361 |
| PED | 10 | H1-H12 | 47 | 47 | 2014Q2 | 2025Q4 | 3.826 | 3.702 | 82.770 | 1.371 | 27.382 |
| PED | 11 | H1-H12 | 46 | 46 | 2014Q3 | 2025Q4 | 4.085 | 3.949 | 87.042 | 1.598 | 31.918 |
| PED | 12 | H1-H12 | 45 | 45 | 2014Q4 | 2025Q4 | 4.307 | 4.164 | 90.225 | 1.792 | 35.796 |
| PED | 13 | H13-H20 | 44 | 44 | 2015Q1 | 2025Q4 | 4.581 | 4.433 | 94.319 | 2.026 | 40.480 |
| PED | 14 | H13-H20 | 43 | 43 | 2015Q2 | 2025Q4 | 4.794 | 4.643 | 97.849 | 2.281 | 45.571 |
| PED | 15 | H13-H20 | 42 | 42 | 2015Q3 | 2025Q4 | 5.029 | 4.876 | 100.868 | 2.599 | 51.926 |
| PED | 16 | H13-H20 | 41 | 41 | 2015Q4 | 2025Q4 | 5.175 | 5.024 | 101.982 | 2.899 | 57.921 |
| PED | 17 | H13-H20 | 40 | 40 | 2016Q1 | 2025Q4 | 5.302 | 5.155 | 103.393 | 3.240 | 64.717 |
| PED | 18 | H13-H20 | 39 | 39 | 2016Q2 | 2025Q4 | 5.547 | 5.399 | 105.559 | 3.569 | 71.293 |
| PED | 19 | H13-H20 | 38 | 38 | 2016Q3 | 2025Q4 | 5.785 | 5.636 | 107.451 | 3.939 | 78.700 |
| PED | 20 | H13-H20 | 37 | 37 | 2016Q4 | 2025Q4 | 5.986 | 5.835 | 108.865 | 4.311 | 86.114 |

## Balanced cohort: identical origins at every horizon

Restricted to origins observed at every horizon 1..20. H1 and
H20 are computed from the same origins, so surviving degradation is a
horizon effect rather than a change in which periods are scored.

| stream | horizon | horizon_support_state | n_observations | n_origins | first_target_period | last_target_period | mape_pct | wape_pct | rmse | signed_mean_error_pct | revenue_equivalent_signed_error_nzd_m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HEAVY_RUC | 1 | H1-H12 | 23 | 23 | 2015Q3 | 2021Q1 | 2.394 | 2.397 | 27411887.291 | -0.318 | -3.534 |
| HEAVY_RUC | 2 | H1-H12 | 23 | 23 | 2015Q4 | 2021Q2 | 2.517 | 2.503 | 30920856.724 | -0.180 | -1.997 |
| HEAVY_RUC | 3 | H1-H12 | 23 | 23 | 2016Q1 | 2021Q3 | 2.957 | 2.943 | 33297961.460 | -0.019 | -0.213 |
| HEAVY_RUC | 4 | H1-H12 | 23 | 23 | 2016Q2 | 2021Q4 | 2.881 | 2.839 | 34067611.580 | -0.137 | -1.516 |
| HEAVY_RUC | 5 | H1-H12 | 23 | 23 | 2016Q3 | 2022Q1 | 3.006 | 2.950 | 37568974.417 | -0.139 | -1.543 |
| HEAVY_RUC | 6 | H1-H12 | 23 | 23 | 2016Q4 | 2022Q2 | 3.220 | 3.148 | 39706600.610 | -0.381 | -4.232 |
| HEAVY_RUC | 7 | H1-H12 | 23 | 23 | 2017Q1 | 2022Q3 | 3.464 | 3.392 | 42039054.838 | -0.213 | -2.364 |
| HEAVY_RUC | 8 | H1-H12 | 23 | 23 | 2017Q2 | 2022Q4 | 3.604 | 3.507 | 45281388.328 | 0.012 | 0.134 |
| HEAVY_RUC | 9 | H1-H12 | 23 | 23 | 2017Q3 | 2023Q1 | 3.540 | 3.438 | 44879661.670 | 0.188 | 2.082 |
| HEAVY_RUC | 10 | H1-H12 | 23 | 23 | 2017Q4 | 2023Q2 | 3.620 | 3.508 | 46940523.114 | 0.112 | 1.249 |
| HEAVY_RUC | 11 | H1-H12 | 23 | 23 | 2018Q1 | 2023Q3 | 3.726 | 3.601 | 46213510.315 | 0.637 | 7.071 |
| HEAVY_RUC | 12 | H1-H12 | 23 | 23 | 2018Q2 | 2023Q4 | 3.625 | 3.503 | 44920350.146 | 1.007 | 11.176 |
| HEAVY_RUC | 13 | H13-H20 | 23 | 23 | 2018Q3 | 2024Q1 | 3.541 | 3.427 | 43407145.142 | 1.439 | 15.968 |
| HEAVY_RUC | 14 | H13-H20 | 23 | 23 | 2018Q4 | 2024Q2 | 3.501 | 3.393 | 44100994.146 | 1.730 | 19.203 |
| HEAVY_RUC | 15 | H13-H20 | 23 | 23 | 2019Q1 | 2024Q3 | 3.654 | 3.537 | 44861511.442 | 2.166 | 24.043 |
| HEAVY_RUC | 16 | H13-H20 | 23 | 23 | 2019Q2 | 2024Q4 | 3.811 | 3.707 | 45350327.843 | 2.368 | 26.284 |
| HEAVY_RUC | 17 | H13-H20 | 23 | 23 | 2019Q3 | 2025Q1 | 4.156 | 4.036 | 50417996.327 | 2.471 | 27.425 |
| HEAVY_RUC | 18 | H13-H20 | 23 | 23 | 2019Q4 | 2025Q2 | 4.616 | 4.504 | 52520153.174 | 2.622 | 29.101 |
| HEAVY_RUC | 19 | H13-H20 | 23 | 23 | 2020Q1 | 2025Q3 | 4.612 | 4.478 | 56906866.376 | 2.835 | 31.472 |
| HEAVY_RUC | 20 | H13-H20 | 23 | 23 | 2020Q2 | 2025Q4 | 4.426 | 4.288 | 54534843.770 | 2.721 | 30.197 |
| LIGHT_RUC | 1 | H1-H12 | 11 | 11 | 2018Q3 | 2021Q1 | 2.548 | 2.459 | 91220041.859 | 0.836 | 6.948 |
| LIGHT_RUC | 2 | H1-H12 | 11 | 11 | 2018Q4 | 2021Q2 | 3.478 | 3.430 | 117580448.583 | 2.272 | 18.881 |
| LIGHT_RUC | 3 | H1-H12 | 11 | 11 | 2019Q1 | 2021Q3 | 5.063 | 4.873 | 190910967.384 | 4.107 | 34.130 |
| LIGHT_RUC | 4 | H1-H12 | 11 | 11 | 2019Q2 | 2021Q4 | 6.259 | 6.092 | 227727194.751 | 5.651 | 46.956 |
| LIGHT_RUC | 5 | H1-H12 | 11 | 11 | 2019Q3 | 2022Q1 | 7.812 | 7.684 | 255439222.284 | 7.355 | 61.119 |
| LIGHT_RUC | 6 | H1-H12 | 11 | 11 | 2019Q4 | 2022Q2 | 8.101 | 7.938 | 269220179.452 | 6.374 | 52.970 |
| LIGHT_RUC | 7 | H1-H12 | 11 | 11 | 2020Q1 | 2022Q3 | 9.295 | 9.179 | 300604939.219 | 7.290 | 60.576 |
| LIGHT_RUC | 8 | H1-H12 | 11 | 11 | 2020Q2 | 2022Q4 | 9.037 | 9.048 | 320165736.634 | 6.568 | 54.576 |
| LIGHT_RUC | 9 | H1-H12 | 11 | 11 | 2020Q3 | 2023Q1 | 11.736 | 11.720 | 419780845.976 | 5.510 | 45.787 |
| LIGHT_RUC | 10 | H1-H12 | 11 | 11 | 2020Q4 | 2023Q2 | 13.510 | 13.601 | 505284292.973 | 3.511 | 29.179 |
| LIGHT_RUC | 11 | H1-H12 | 11 | 11 | 2021Q1 | 2023Q3 | 15.400 | 15.605 | 537130167.846 | 4.364 | 36.265 |
| LIGHT_RUC | 12 | H1-H12 | 11 | 11 | 2021Q2 | 2023Q4 | 16.932 | 16.683 | 546647263.455 | 7.649 | 63.563 |
| LIGHT_RUC | 13 | H13-H20 | 11 | 11 | 2021Q3 | 2024Q1 | 19.572 | 18.941 | 591132436.313 | 10.666 | 88.629 |
| LIGHT_RUC | 14 | H13-H20 | 11 | 11 | 2021Q4 | 2024Q2 | 19.643 | 18.787 | 605472322.930 | 11.687 | 97.114 |
| LIGHT_RUC | 15 | H13-H20 | 11 | 11 | 2022Q1 | 2024Q3 | 18.203 | 17.279 | 578224454.228 | 11.499 | 95.557 |
| LIGHT_RUC | 16 | H13-H20 | 11 | 11 | 2022Q2 | 2024Q4 | 20.064 | 18.417 | 659014014.256 | 13.199 | 109.680 |
| LIGHT_RUC | 17 | H13-H20 | 11 | 11 | 2022Q3 | 2025Q1 | 19.589 | 17.614 | 643188158.781 | 16.447 | 136.666 |
| LIGHT_RUC | 18 | H13-H20 | 11 | 11 | 2022Q4 | 2025Q2 | 18.695 | 16.684 | 630563056.931 | 15.875 | 131.920 |
| LIGHT_RUC | 19 | H13-H20 | 11 | 11 | 2023Q1 | 2025Q3 | 18.451 | 16.383 | 625473430.041 | 15.356 | 127.604 |
| LIGHT_RUC | 20 | H13-H20 | 11 | 11 | 2023Q2 | 2025Q4 | 19.822 | 17.747 | 667849970.453 | 17.242 | 143.277 |
| PED | 1 | H1-H12 | 37 | 37 | 2012Q1 | 2021Q1 | 0.967 | 0.935 | 24.728 | 0.189 | 3.774 |
| PED | 2 | H1-H12 | 37 | 37 | 2012Q2 | 2021Q2 | 1.364 | 1.307 | 36.210 | 0.513 | 10.252 |
| PED | 3 | H1-H12 | 37 | 37 | 2012Q3 | 2021Q3 | 1.592 | 1.520 | 43.974 | 0.888 | 17.738 |
| PED | 4 | H1-H12 | 37 | 37 | 2012Q4 | 2021Q4 | 1.975 | 1.878 | 51.762 | 1.303 | 26.022 |
| PED | 5 | H1-H12 | 37 | 37 | 2013Q1 | 2022Q1 | 2.525 | 2.405 | 60.635 | 1.636 | 32.682 |
| PED | 6 | H1-H12 | 37 | 37 | 2013Q2 | 2022Q2 | 2.793 | 2.667 | 65.644 | 1.822 | 36.404 |
| PED | 7 | H1-H12 | 37 | 37 | 2013Q3 | 2022Q3 | 3.003 | 2.869 | 71.129 | 1.972 | 39.403 |
| PED | 8 | H1-H12 | 37 | 37 | 2013Q4 | 2022Q4 | 3.308 | 3.162 | 77.339 | 2.110 | 42.152 |
| PED | 9 | H1-H12 | 37 | 37 | 2014Q1 | 2023Q1 | 3.758 | 3.596 | 83.917 | 2.319 | 46.333 |
| PED | 10 | H1-H12 | 37 | 37 | 2014Q2 | 2023Q2 | 4.072 | 3.897 | 89.863 | 2.529 | 50.521 |
| PED | 11 | H1-H12 | 37 | 37 | 2014Q3 | 2023Q3 | 4.343 | 4.158 | 94.011 | 2.721 | 54.365 |
| PED | 12 | H1-H12 | 37 | 37 | 2014Q4 | 2023Q4 | 4.566 | 4.376 | 96.710 | 2.851 | 56.957 |
| PED | 13 | H13-H20 | 37 | 37 | 2015Q1 | 2024Q1 | 4.833 | 4.640 | 99.961 | 3.024 | 60.421 |
| PED | 14 | H13-H20 | 37 | 37 | 2015Q2 | 2024Q2 | 5.017 | 4.824 | 102.422 | 3.205 | 64.028 |
| PED | 15 | H13-H20 | 37 | 37 | 2015Q3 | 2024Q3 | 5.227 | 5.038 | 104.633 | 3.432 | 68.566 |
| PED | 16 | H13-H20 | 37 | 37 | 2015Q4 | 2024Q4 | 5.332 | 5.153 | 105.079 | 3.616 | 72.231 |
| PED | 17 | H13-H20 | 37 | 37 | 2016Q1 | 2025Q1 | 5.416 | 5.250 | 105.787 | 3.818 | 76.272 |
| PED | 18 | H13-H20 | 37 | 37 | 2016Q2 | 2025Q2 | 5.550 | 5.394 | 106.542 | 4.058 | 81.073 |
| PED | 19 | H13-H20 | 37 | 37 | 2016Q3 | 2025Q3 | 5.781 | 5.627 | 107.807 | 4.207 | 84.045 |
| PED | 20 | H13-H20 | 37 | 37 | 2016Q4 | 2025Q4 | 5.986 | 5.835 | 108.865 | 4.311 | 86.114 |

## Balanced cohort excluding 2020-2021 targets

The original methodology excluded 2020-2021 outcomes from
forecast-accuracy tests while retaining them in training data, on the
grounds that they were not realistically forecastable.

| stream | horizon | horizon_support_state | n_observations | n_origins | first_target_period | last_target_period | mape_pct | wape_pct | rmse | signed_mean_error_pct | revenue_equivalent_signed_error_nzd_m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HEAVY_RUC | 1 | H1-H12 | 18 | 18 | 2015Q3 | 2019Q4 | 2.160 | 2.172 | 24524459.507 | -0.406 | -4.504 |
| HEAVY_RUC | 2 | H1-H12 | 17 | 17 | 2015Q4 | 2019Q4 | 2.160 | 2.174 | 25728483.182 | -0.476 | -5.281 |
| HEAVY_RUC | 3 | H1-H12 | 16 | 16 | 2016Q1 | 2019Q4 | 2.526 | 2.544 | 28905979.375 | -0.577 | -6.407 |
| HEAVY_RUC | 4 | H1-H12 | 15 | 15 | 2016Q2 | 2019Q4 | 2.587 | 2.604 | 30898308.752 | -1.034 | -11.477 |
| HEAVY_RUC | 5 | H1-H12 | 15 | 15 | 2016Q3 | 2022Q1 | 2.766 | 2.788 | 33887617.893 | -1.436 | -15.939 |
| HEAVY_RUC | 6 | H1-H12 | 15 | 15 | 2016Q4 | 2022Q2 | 3.134 | 3.149 | 36791327.864 | -1.973 | -21.903 |
| HEAVY_RUC | 7 | H1-H12 | 15 | 15 | 2017Q1 | 2022Q3 | 3.242 | 3.258 | 38624447.779 | -2.024 | -22.464 |
| HEAVY_RUC | 8 | H1-H12 | 15 | 15 | 2017Q2 | 2022Q4 | 3.348 | 3.361 | 40207819.077 | -2.007 | -22.273 |
| HEAVY_RUC | 9 | H1-H12 | 15 | 15 | 2017Q3 | 2023Q1 | 3.124 | 3.131 | 38395858.130 | -1.730 | -19.207 |
| HEAVY_RUC | 10 | H1-H12 | 15 | 15 | 2017Q4 | 2023Q2 | 3.323 | 3.324 | 41660479.559 | -1.787 | -19.834 |
| HEAVY_RUC | 11 | H1-H12 | 15 | 15 | 2018Q1 | 2023Q3 | 3.352 | 3.323 | 40619461.425 | -0.988 | -10.971 |
| HEAVY_RUC | 12 | H1-H12 | 15 | 15 | 2018Q2 | 2023Q4 | 3.330 | 3.298 | 39337113.183 | -0.434 | -4.823 |
| HEAVY_RUC | 13 | H13-H20 | 15 | 15 | 2018Q3 | 2024Q1 | 3.213 | 3.185 | 38041496.105 | 0.467 | 5.184 |
| HEAVY_RUC | 14 | H13-H20 | 15 | 15 | 2018Q4 | 2024Q2 | 3.190 | 3.166 | 38802664.190 | 1.118 | 12.411 |
| HEAVY_RUC | 15 | H13-H20 | 15 | 15 | 2019Q1 | 2024Q3 | 3.197 | 3.144 | 39754525.460 | 2.135 | 23.701 |
| HEAVY_RUC | 16 | H13-H20 | 15 | 15 | 2019Q2 | 2024Q4 | 3.324 | 3.284 | 40037120.903 | 2.605 | 28.917 |
| HEAVY_RUC | 17 | H13-H20 | 15 | 15 | 2019Q3 | 2025Q1 | 3.731 | 3.670 | 47425558.513 | 3.123 | 34.669 |
| HEAVY_RUC | 18 | H13-H20 | 15 | 15 | 2019Q4 | 2025Q2 | 4.233 | 4.180 | 48459858.655 | 3.643 | 40.433 |
| HEAVY_RUC | 19 | H13-H20 | 15 | 15 | 2022Q1 | 2025Q3 | 4.544 | 4.458 | 55752749.434 | 4.149 | 46.050 |
| HEAVY_RUC | 20 | H13-H20 | 16 | 16 | 2022Q1 | 2025Q4 | 4.175 | 4.090 | 51125290.628 | 4.005 | 44.454 |
| LIGHT_RUC | 1 | H1-H12 | 6 | 6 | 2018Q3 | 2019Q4 | 1.745 | 1.711 | 68764856.042 | 1.068 | 8.872 |
| LIGHT_RUC | 2 | H1-H12 | 5 | 5 | 2018Q4 | 2019Q4 | 2.405 | 2.372 | 80596745.386 | 2.119 | 17.610 |
| LIGHT_RUC | 3 | H1-H12 | 4 | 4 | 2019Q1 | 2019Q4 | 2.350 | 2.305 | 83010339.729 | 1.988 | 16.523 |
| LIGHT_RUC | 4 | H1-H12 | 3 | 3 | 2019Q2 | 2019Q4 | 3.001 | 2.922 | 106264347.148 | 2.439 | 20.270 |
| LIGHT_RUC | 5 | H1-H12 | 3 | 3 | 2019Q3 | 2022Q1 | 5.874 | 5.811 | 192042855.326 | 5.874 | 48.814 |
| LIGHT_RUC | 6 | H1-H12 | 3 | 3 | 2019Q4 | 2022Q2 | 5.910 | 5.956 | 223287958.234 | 1.371 | 11.392 |
| LIGHT_RUC | 7 | H1-H12 | 3 | 3 | 2022Q1 | 2022Q3 | 8.279 | 8.296 | 282670621.082 | 2.674 | 22.218 |
| LIGHT_RUC | 8 | H1-H12 | 4 | 4 | 2022Q1 | 2022Q4 | 7.090 | 7.488 | 304216020.864 | 1.068 | 8.875 |
| LIGHT_RUC | 9 | H1-H12 | 5 | 5 | 2022Q1 | 2023Q1 | 11.402 | 11.721 | 470658416.415 | -2.296 | -19.077 |
| LIGHT_RUC | 10 | H1-H12 | 6 | 6 | 2022Q1 | 2023Q2 | 14.447 | 14.728 | 582658008.062 | -3.884 | -32.274 |
| LIGHT_RUC | 11 | H1-H12 | 7 | 7 | 2022Q1 | 2023Q3 | 16.321 | 16.730 | 591140521.756 | -1.021 | -8.482 |
| LIGHT_RUC | 12 | H1-H12 | 8 | 8 | 2022Q1 | 2023Q4 | 16.974 | 16.752 | 565494156.993 | 4.210 | 34.982 |
| LIGHT_RUC | 13 | H13-H20 | 9 | 9 | 2022Q1 | 2024Q1 | 19.223 | 18.524 | 592844157.603 | 8.337 | 69.280 |
| LIGHT_RUC | 14 | H13-H20 | 10 | 10 | 2022Q1 | 2024Q2 | 19.709 | 18.769 | 610440989.698 | 10.958 | 91.056 |
| LIGHT_RUC | 15 | H13-H20 | 11 | 11 | 2022Q1 | 2024Q3 | 18.203 | 17.279 | 578224454.228 | 11.499 | 95.557 |
| LIGHT_RUC | 16 | H13-H20 | 11 | 11 | 2022Q2 | 2024Q4 | 20.064 | 18.417 | 659014014.256 | 13.199 | 109.680 |
| LIGHT_RUC | 17 | H13-H20 | 11 | 11 | 2022Q3 | 2025Q1 | 19.589 | 17.614 | 643188158.781 | 16.447 | 136.666 |
| LIGHT_RUC | 18 | H13-H20 | 11 | 11 | 2022Q4 | 2025Q2 | 18.695 | 16.684 | 630563056.931 | 15.875 | 131.920 |
| LIGHT_RUC | 19 | H13-H20 | 11 | 11 | 2023Q1 | 2025Q3 | 18.451 | 16.383 | 625473430.041 | 15.356 | 127.604 |
| LIGHT_RUC | 20 | H13-H20 | 11 | 11 | 2023Q2 | 2025Q4 | 19.822 | 17.747 | 667849970.453 | 17.242 | 143.277 |
| PED | 1 | H1-H12 | 32 | 32 | 2012Q1 | 2019Q4 | 0.690 | 0.680 | 17.837 | 0.142 | 2.833 |
| PED | 2 | H1-H12 | 31 | 31 | 2012Q2 | 2019Q4 | 0.866 | 0.851 | 24.876 | 0.260 | 5.197 |
| PED | 3 | H1-H12 | 30 | 30 | 2012Q3 | 2019Q4 | 0.933 | 0.917 | 27.244 | 0.242 | 4.843 |
| PED | 4 | H1-H12 | 29 | 29 | 2012Q4 | 2019Q4 | 1.022 | 1.004 | 29.058 | 0.179 | 3.579 |
| PED | 5 | H1-H12 | 29 | 29 | 2013Q1 | 2022Q1 | 1.355 | 1.321 | 33.017 | 0.220 | 4.402 |
| PED | 6 | H1-H12 | 29 | 29 | 2013Q2 | 2022Q2 | 1.414 | 1.383 | 32.818 | 0.175 | 3.490 |
| PED | 7 | H1-H12 | 29 | 29 | 2013Q3 | 2022Q3 | 1.357 | 1.338 | 31.737 | 0.042 | 0.843 |
| PED | 8 | H1-H12 | 29 | 29 | 2013Q4 | 2022Q4 | 1.414 | 1.400 | 32.634 | -0.114 | -2.285 |
| PED | 9 | H1-H12 | 29 | 29 | 2014Q1 | 2023Q1 | 1.787 | 1.756 | 39.125 | -0.048 | -0.969 |
| PED | 10 | H1-H12 | 29 | 29 | 2014Q2 | 2023Q2 | 2.052 | 2.006 | 46.399 | 0.084 | 1.679 |
| PED | 11 | H1-H12 | 29 | 29 | 2014Q3 | 2023Q3 | 2.342 | 2.276 | 52.965 | 0.272 | 5.437 |
| PED | 12 | H1-H12 | 29 | 29 | 2014Q4 | 2023Q4 | 2.645 | 2.564 | 59.340 | 0.457 | 9.134 |
| PED | 13 | H13-H20 | 29 | 29 | 2015Q1 | 2024Q1 | 2.990 | 2.892 | 65.919 | 0.683 | 13.635 |
| PED | 14 | H13-H20 | 29 | 29 | 2015Q2 | 2024Q2 | 3.228 | 3.121 | 70.858 | 0.916 | 18.294 |
| PED | 15 | H13-H20 | 29 | 29 | 2015Q3 | 2024Q3 | 3.495 | 3.383 | 74.767 | 1.205 | 24.079 |
| PED | 16 | H13-H20 | 29 | 29 | 2015Q4 | 2024Q4 | 3.692 | 3.579 | 77.677 | 1.502 | 30.013 |
| PED | 17 | H13-H20 | 29 | 29 | 2016Q1 | 2025Q1 | 3.875 | 3.765 | 81.035 | 1.835 | 36.667 |
| PED | 18 | H13-H20 | 29 | 29 | 2016Q2 | 2025Q2 | 4.099 | 3.989 | 83.927 | 2.195 | 43.860 |
| PED | 19 | H13-H20 | 29 | 29 | 2016Q3 | 2025Q3 | 4.433 | 4.317 | 87.131 | 2.425 | 48.451 |
| PED | 20 | H13-H20 | 29 | 29 | 2016Q4 | 2025Q4 | 4.750 | 4.628 | 90.101 | 2.613 | 52.201 |

## June-year error by support state

Only June years whose four quarters all come from one origin are scored.

| cohort | target_window | stream | stream_label | horizon_support_state | n_june_years | annual_mape_pct | annual_signed_bias_pct | cumulative_signed_error_units | cumulative_actual_units | cumulative_signed_error_pct | cumulative_revenue_equivalent_error_nzd_m | revenue_equivalent_basis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all_available | all_targets | HEAVY_RUC | Heavy RUC volume | H1-H12 | 78 | 2.584 | 0.449 | 1302225361.313 | 313732918794.000 | 0.415 | 4.607 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | all_targets | HEAVY_RUC | Heavy RUC volume | H13-H20 | 52 | 3.130 | 1.831 | 3801207095.298 | 210029971112.000 | 1.810 | 20.088 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | all_targets | LIGHT_RUC | Light RUC volume | H1-H12 | 51 | 8.230 | 4.028 | 21216443767.876 | 616254649561.000 | 3.443 | 28.609 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | all_targets | LIGHT_RUC | Light RUC volume | H13-H20 | 28 | 10.067 | 9.193 | 27976905019.886 | 340039410000.000 | 8.228 | 68.369 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | all_targets | PED | PED VKT per capita | H1-H12 | 109 | 2.580 | 0.943 | 6021.600 | 698249.940 | 0.862 | 17.228 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | all_targets | PED | PED VKT per capita | H13-H20 | 80 | 4.873 | 3.010 | 14203.169 | 507802.949 | 2.797 | 55.876 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | excl_2020_2021 | HEAVY_RUC | Heavy RUC volume | H1-H12 | 51 | 2.635 | -0.341 | -734148387.538 | 204115782135.000 | -0.360 | -3.992 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | excl_2020_2021 | HEAVY_RUC | Heavy RUC volume | H13-H20 | 28 | 3.190 | 2.126 | 2377671815.731 | 112592516304.000 | 2.112 | 23.439 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | excl_2020_2021 | LIGHT_RUC | Light RUC volume | H1-H12 | 28 | 10.402 | 2.748 | 5571114022.879 | 337543624522.000 | 1.650 | 13.715 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | excl_2020_2021 | LIGHT_RUC | Light RUC volume | H13-H20 | 24 | 10.675 | 9.656 | 24730451917.194 | 289462577168.000 | 8.544 | 70.995 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | excl_2020_2021 | PED | PED VKT per capita | H1-H12 | 82 | 1.162 | -0.948 | -4963.789 | 534562.042 | -0.929 | -18.550 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| all_available | excl_2020_2021 | PED | PED VKT per capita | H13-H20 | 56 | 2.527 | -0.134 | -792.257 | 362302.596 | -0.219 | -4.368 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | all_targets | HEAVY_RUC | Heavy RUC volume | H1-H12 | 52 | 2.682 | -0.227 | -529051347.231 | 209502962567.000 | -0.253 | -2.803 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | all_targets | HEAVY_RUC | Heavy RUC volume | H13-H20 | 46 | 3.277 | 1.808 | 3324059482.660 | 186216742151.000 | 1.785 | 19.813 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | all_targets | LIGHT_RUC | Light RUC volume | H1-H12 | 25 | 6.086 | 3.538 | 10291467260.222 | 305980696676.000 | 3.363 | 27.949 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | all_targets | LIGHT_RUC | Light RUC volume | H13-H20 | 22 | 11.714 | 10.899 | 26138289242.408 | 268313939981.000 | 9.742 | 80.951 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | all_targets | PED | PED VKT per capita | H1-H12 | 83 | 2.781 | 1.746 | 8592.220 | 541065.168 | 1.588 | 31.724 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | all_targets | PED | PED VKT per capita | H13-H20 | 74 | 5.083 | 3.439 | 15023.190 | 471860.748 | 3.184 | 63.604 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | excl_2020_2021 | HEAVY_RUC | Heavy RUC volume | H1-H12 | 27 | 2.690 | -2.383 | -2570996308.450 | 108227683740.000 | -2.376 | -26.367 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | excl_2020_2021 | HEAVY_RUC | Heavy RUC volume | H13-H20 | 22 | 3.512 | 2.157 | 1900524203.094 | 88779287343.000 | 2.141 | 23.761 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | excl_2020_2021 | LIGHT_RUC | Light RUC volume | H1-H12 | 4 | 8.126 | -7.803 | -4241036506.540 | 52558088053.000 | -8.069 | -67.053 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | excl_2020_2021 | LIGHT_RUC | Light RUC volume | H13-H20 | 18 | 12.890 | 11.895 | 22891836139.716 | 217737107149.000 | 10.514 | 87.365 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | excl_2020_2021 | PED | PED VKT per capita | H1-H12 | 58 | 0.825 | -0.564 | -2219.701 | 389196.632 | -0.570 | -11.394 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |
| balanced_h20 | excl_2020_2021 | PED | PED VKT per capita | H13-H20 | 50 | 2.556 | 0.123 | 27.764 | 326360.395 | 0.009 | 0.170 | signed percentage activity error applied to governed FY2025 revenue for the stream, assuming unit pass-through at fixed rates and class mix; indicative materiality scale only |

## Provenance

| stream | stream_label | finalist_model | pipeline_version | scorer_version | forecast_runner_version | max_horizon | backtest_supported_max_horizon | extended_evidence_max_horizon | signed_error_definition | driver_basis | target_lag_basis | fitted_model_manifest_path | fitted_model_manifest_sha256 | input_history_path | input_history_sha256 | reference_revenue_fy | reference_revenue_series | reference_revenue_nzd_m | prediction_interval_coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PED | PED VKT per capita | PED__VNEXT_SOLVED_CONVEX_TOP2 | vnext-pipeline-v1.0 | long-horizon-rolling-origin-v2 | forecast-runner-v5-forward-scorer-governance | 20 | 12 | 20 | (forecast - actual) / actual * 100; positive = overprediction | actual_observed_drivers | recursive_predicted_target_lags | data/dashboard_evidence_pack_reproducibility/ped_vnext/fitted_model_manifest.json | aea81e4ff915c4f739705a8394a0695e241762d51464ab3d23edd01f691a025d | data/model_input_history/ped_inputs.parquet | d1955e01e07c74ad5aff08736cc822cd914cfa2df201e1f7dd8872116219a1f9 | 2025 | net_fed_revenue | 1997.727 | unavailable_no_governed_interval_from_production_scorer |
| HEAVY_RUC | Heavy RUC volume | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | vnext-pipeline-v1.0 | long-horizon-rolling-origin-v2 | forecast-runner-v5-forward-scorer-governance | 20 | 12 | 20 | (forecast - actual) / actual * 100; positive = overprediction | actual_observed_drivers | recursive_predicted_target_lags | data/dashboard_evidence_pack_reproducibility/heavy_ruc_vnext/fitted_model_manifest.json | 87fcef0ba36780a752d9b1ec6981ef593644d344b6b87f8dbbbcb50846fc8e98 | data/model_input_history/heavy_ruc_inputs.parquet | 751d6f71ac0941c2c606b4bd87980c249b798df4ddd93d1e7c372b51394dc5bb | 2025 | heavy_ruc_net_revenue | 1109.950 | unavailable_no_governed_interval_from_production_scorer |
| LIGHT_RUC | Light RUC volume | dynamic_RESID_GBR_n150_d1_lr0.05_w36 | vnext-pipeline-v1.0 | long-horizon-rolling-origin-v2 | forecast-runner-v5-forward-scorer-governance | 20 | 12 | 20 | (forecast - actual) / actual * 100; positive = overprediction | actual_observed_drivers | no_target_lags_in_recipe | data/dashboard_evidence_pack_reproducibility/light_ruc_vnext/fitted_model_manifest.json | f96ba64d710f8e069b17472e950704656689859b1f15ecae1ce02292c348c511 | data/model_input_history/light_ruc_inputs.parquet | ab0a7ccc4b9c7f2a92c596fe3c25c2a21f973a8643733c50da08c4db0ceea76d | 2025 | light_ruc_net_revenue | 830.974 | unavailable_no_governed_interval_from_production_scorer |

## What this does and does not establish

The H13-H20 actual-driver evaluation shows material error growth,
especially for Light RUC, and historical average signed error is
positive. This weakens a systematic downward conditional-model-bias
explanation for the current MBU26 gap. Because this is not a
forecast-vintage comparison, it does not identify the source of the gap.
The common-input decomposition is therefore the next diagnostic
workstream. A structural long-term bridge remains open as a
forecast-governance project.

Specifically, this evaluation does **not** distinguish between input
vintage, MBU26 assumptions, migration and class definitions,
path-specific model dynamics, and judgmental overlays. A positive
historical model bias is compatible with a model path below MBU26 - for
instance if MBU26 is itself high relative to eventual outcomes, or if the
two forecasts share direction but differ in long-run level.

