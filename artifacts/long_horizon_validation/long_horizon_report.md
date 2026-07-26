# Long-horizon rolling-origin evaluation

Fixed finalists scored to H20 on the committed input history.
Actual-driver evaluation: exogenous inputs at each target quarter are the
observed values, so this measures model degradation with horizon, not
driver-forecast error. Sample size falls with horizon because each extra
horizon costs one origin at the end of the sample - read `n_observations`
before drawing conclusions from the tail.

## Quarterly metrics by horizon

| stream | stream_label | horizon | horizon_scope | n_observations | n_origins | mape_pct | wape_pct | rmse | signed_mean_error_pct | signed_mean_error |
|---|---|---|---|---|---|---|---|---|---|---|
| HEAVY_RUC | Heavy RUC volume | 1 | H1-H12 | 42 | 42 | 2.400 | 2.401 | 29175246.634 | 0.011 | -665032.300 |
| HEAVY_RUC | Heavy RUC volume | 2 | H1-H12 | 41 | 41 | 2.423 | 2.413 | 29334822.955 | 0.178 | 939424.228 |
| HEAVY_RUC | Heavy RUC volume | 3 | H1-H12 | 40 | 40 | 2.790 | 2.776 | 32568707.064 | 0.242 | 1533288.008 |
| HEAVY_RUC | Heavy RUC volume | 4 | H1-H12 | 39 | 39 | 2.670 | 2.634 | 32073466.190 | 0.238 | 1519849.515 |
| HEAVY_RUC | Heavy RUC volume | 5 | H1-H12 | 38 | 38 | 3.009 | 2.968 | 36519546.780 | 0.183 | 730616.988 |
| HEAVY_RUC | Heavy RUC volume | 6 | H1-H12 | 37 | 37 | 3.053 | 2.998 | 36763770.381 | 0.247 | 1354389.493 |
| HEAVY_RUC | Heavy RUC volume | 7 | H1-H12 | 36 | 36 | 3.224 | 3.164 | 38841385.120 | 0.414 | 2972085.239 |
| HEAVY_RUC | Heavy RUC volume | 8 | H1-H12 | 35 | 35 | 3.337 | 3.255 | 41670712.100 | 0.661 | 5286938.708 |
| HEAVY_RUC | Heavy RUC volume | 9 | H1-H12 | 34 | 34 | 3.399 | 3.314 | 42015684.418 | 0.809 | 6703159.624 |
| HEAVY_RUC | Heavy RUC volume | 10 | H1-H12 | 33 | 33 | 3.412 | 3.321 | 42913127.291 | 0.968 | 8284598.715 |
| HEAVY_RUC | Heavy RUC volume | 11 | H1-H12 | 32 | 32 | 3.428 | 3.325 | 42293191.426 | 1.189 | 10597388.253 |
| HEAVY_RUC | Heavy RUC volume | 12 | H1-H12 | 31 | 31 | 3.399 | 3.292 | 42091300.309 | 1.446 | 13194024.182 |
| HEAVY_RUC | Heavy RUC volume | 13 | H13+ | 30 | 30 | 3.294 | 3.194 | 40770806.995 | 1.679 | 15576930.670 |
| HEAVY_RUC | Heavy RUC volume | 14 | H13+ | 29 | 29 | 3.223 | 3.132 | 40955951.322 | 1.815 | 16973625.240 |
| HEAVY_RUC | Heavy RUC volume | 15 | H13+ | 28 | 28 | 3.284 | 3.176 | 41584954.858 | 2.022 | 19106987.312 |
| HEAVY_RUC | Heavy RUC volume | 16 | H13+ | 27 | 27 | 3.514 | 3.418 | 42772373.962 | 2.272 | 21670965.405 |
| HEAVY_RUC | Heavy RUC volume | 17 | H13+ | 26 | 26 | 3.930 | 3.819 | 48160460.276 | 2.439 | 23100757.872 |
| HEAVY_RUC | Heavy RUC volume | 18 | H13+ | 25 | 25 | 4.382 | 4.272 | 50715106.755 | 2.548 | 24139865.711 |
| HEAVY_RUC | Heavy RUC volume | 19 | H13+ | 24 | 24 | 4.425 | 4.287 | 55709454.575 | 2.723 | 25521867.604 |
| HEAVY_RUC | Heavy RUC volume | 20 | H13+ | 23 | 23 | 4.426 | 4.288 | 54534843.770 | 2.721 | 25502905.147 |
| LIGHT_RUC | Light RUC volume | 1 | H1-H12 | 30 | 30 | 7.387 | 7.373 | 335256562.194 | 0.823 | -8859629.251 |
| LIGHT_RUC | Light RUC volume | 2 | H1-H12 | 29 | 29 | 9.708 | 9.833 | 424101259.629 | 1.984 | 16656252.401 |
| LIGHT_RUC | Light RUC volume | 3 | H1-H12 | 28 | 28 | 8.647 | 8.914 | 385706611.652 | 2.166 | 32258682.459 |
| LIGHT_RUC | Light RUC volume | 4 | H1-H12 | 27 | 27 | 8.009 | 7.985 | 304963513.717 | 2.899 | 65500987.062 |
| LIGHT_RUC | Light RUC volume | 5 | H1-H12 | 26 | 26 | 9.236 | 9.135 | 344946931.776 | 3.803 | 79839079.929 |
| LIGHT_RUC | Light RUC volume | 6 | H1-H12 | 25 | 25 | 10.031 | 9.899 | 378784652.351 | 4.064 | 83453406.118 |
| LIGHT_RUC | Light RUC volume | 7 | H1-H12 | 24 | 24 | 11.053 | 10.995 | 404055162.522 | 4.462 | 93037971.011 |
| LIGHT_RUC | Light RUC volume | 8 | H1-H12 | 23 | 23 | 11.350 | 11.376 | 421792510.129 | 4.344 | 87028290.978 |
| LIGHT_RUC | Light RUC volume | 9 | H1-H12 | 22 | 22 | 11.011 | 11.042 | 409568877.633 | 4.690 | 100226591.252 |
| LIGHT_RUC | Light RUC volume | 10 | H1-H12 | 21 | 21 | 10.756 | 10.701 | 411608597.400 | 4.694 | 101717008.346 |
| LIGHT_RUC | Light RUC volume | 11 | H1-H12 | 20 | 20 | 11.910 | 11.924 | 445071874.507 | 4.535 | 88281191.988 |
| LIGHT_RUC | Light RUC volume | 12 | H1-H12 | 19 | 19 | 12.295 | 12.142 | 437737188.902 | 5.059 | 102094218.606 |
| LIGHT_RUC | Light RUC volume | 13 | H13+ | 18 | 18 | 13.869 | 13.445 | 476068437.481 | 6.898 | 149738805.427 |
| LIGHT_RUC | Light RUC volume | 14 | H13+ | 17 | 17 | 13.537 | 12.937 | 490021342.436 | 7.812 | 177446862.078 |
| LIGHT_RUC | Light RUC volume | 15 | H13+ | 16 | 16 | 13.062 | 12.360 | 480699216.788 | 7.652 | 172491657.665 |
| LIGHT_RUC | Light RUC volume | 16 | H13+ | 15 | 15 | 15.350 | 14.118 | 566071681.985 | 9.419 | 208005038.361 |
| LIGHT_RUC | Light RUC volume | 17 | H13+ | 14 | 14 | 15.890 | 14.226 | 571439421.044 | 12.894 | 320092238.074 |
| LIGHT_RUC | Light RUC volume | 18 | H13+ | 13 | 13 | 16.006 | 14.180 | 580246811.950 | 13.401 | 332753213.854 |
| LIGHT_RUC | Light RUC volume | 19 | H13+ | 12 | 12 | 16.937 | 14.929 | 598851595.168 | 14.052 | 344978054.781 |
| LIGHT_RUC | Light RUC volume | 20 | H13+ | 11 | 11 | 19.822 | 17.747 | 667849970.453 | 17.242 | 430305575.189 |
| PED | PED VKT per capita | 1 | H1-H12 | 56 | 56 | 1.087 | 1.059 | 24.570 | -0.100 | -1.649 |
| PED | PED VKT per capita | 2 | H1-H12 | 55 | 55 | 1.483 | 1.440 | 34.888 | 0.067 | 0.813 |
| PED | PED VKT per capita | 3 | H1-H12 | 54 | 54 | 1.676 | 1.624 | 41.141 | 0.275 | 3.881 |
| PED | PED VKT per capita | 4 | H1-H12 | 53 | 53 | 1.955 | 1.891 | 47.264 | 0.490 | 7.062 |
| PED | PED VKT per capita | 5 | H1-H12 | 52 | 52 | 2.350 | 2.276 | 54.306 | 0.661 | 9.495 |
| PED | PED VKT per capita | 6 | H1-H12 | 51 | 51 | 2.598 | 2.518 | 59.263 | 0.770 | 11.062 |
| PED | PED VKT per capita | 7 | H1-H12 | 50 | 50 | 2.818 | 2.731 | 64.602 | 0.879 | 12.645 |
| PED | PED VKT per capita | 8 | H1-H12 | 49 | 49 | 3.092 | 2.994 | 70.387 | 1.000 | 14.358 |
| PED | PED VKT per capita | 9 | H1-H12 | 48 | 48 | 3.515 | 3.403 | 76.801 | 1.169 | 16.744 |
| PED | PED VKT per capita | 10 | H1-H12 | 47 | 47 | 3.826 | 3.702 | 82.770 | 1.371 | 19.621 |
| PED | PED VKT per capita | 11 | H1-H12 | 46 | 46 | 4.085 | 3.949 | 87.042 | 1.598 | 22.970 |
| PED | PED VKT per capita | 12 | H1-H12 | 45 | 45 | 4.307 | 4.164 | 90.225 | 1.792 | 25.830 |
| PED | PED VKT per capita | 13 | H13+ | 44 | 44 | 4.581 | 4.433 | 94.319 | 2.026 | 29.276 |
| PED | PED VKT per capita | 14 | H13+ | 43 | 43 | 4.794 | 4.643 | 97.849 | 2.281 | 33.032 |
| PED | PED VKT per capita | 15 | H13+ | 42 | 42 | 5.029 | 4.876 | 100.868 | 2.599 | 37.808 |
| PED | PED VKT per capita | 16 | H13+ | 41 | 41 | 5.175 | 5.024 | 101.982 | 2.899 | 42.402 |
| PED | PED VKT per capita | 17 | H13+ | 40 | 40 | 5.302 | 5.155 | 103.393 | 3.240 | 47.587 |
| PED | PED VKT per capita | 18 | H13+ | 39 | 39 | 5.547 | 5.399 | 105.559 | 3.569 | 52.564 |
| PED | PED VKT per capita | 19 | H13+ | 38 | 38 | 5.785 | 5.636 | 107.451 | 3.939 | 58.212 |
| PED | PED VKT per capita | 20 | H13+ | 37 | 37 | 5.986 | 5.835 | 108.865 | 4.311 | 63.895 |

## June-year metrics by horizon scope

Only June years whose four quarters all come from one origin are scored.

| stream | stream_label | horizon_scope | n_june_years | annual_mape_pct | annual_signed_bias_pct | cumulative_signed_error_units | cumulative_actual_units | cumulative_signed_error_pct |
|---|---|---|---|---|---|---|---|---|
| HEAVY_RUC | Heavy RUC volume | H1-H12 | 78 | 2.584 | 0.449 | 1302225361.313 | 313732918794.000 | 0.415 |
| HEAVY_RUC | Heavy RUC volume | H13+ | 52 | 3.130 | 1.831 | 3801207095.298 | 210029971112.000 | 1.810 |
| LIGHT_RUC | Light RUC volume | H1-H12 | 51 | 8.230 | 4.028 | 21216443767.876 | 616254649561.000 | 3.443 |
| LIGHT_RUC | Light RUC volume | H13+ | 28 | 10.067 | 9.193 | 27976905019.886 | 340039410000.000 | 8.228 |
| PED | PED VKT per capita | H1-H12 | 109 | 2.580 | 0.943 | 6021.600 | 698249.940 | 0.862 |
| PED | PED VKT per capita | H13+ | 80 | 4.873 | 3.010 | 14203.169 | 507802.949 | 2.797 |

## Reading guidance

* H1-H12 reproduces the governed evidence grid's supported range.
* H13+ is the zone the Revenue Outlook relies on for FY2029 onward and
  which the committed evidence pack does not score.
* A forecast-vintage evaluation is not possible from this repository:
  archived driver vintages are not held, so real forward error will be
  at least this large once driver-forecast error is added.
