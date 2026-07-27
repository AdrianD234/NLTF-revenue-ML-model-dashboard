# GDP sign-guard binding register

Every quarter where the governed structural overlay clipped the fitted
GDP factor. The guards are a governance overlay on a fitted model, not a
re-estimation, so what matters is whether they are precautionary or
doing substantial work.

## Acceptance

| severity | guard_type | rule | n_bindings | max_abs_forecast_delta_pct | status | detail |
|---|---|---|---|---|---|---|
| base | any | no binding should be possible | 0 | 0 | passed | Base is the reference the overlay is built from; a binding there would mean the reference itself was clipped. |
| low | identity | explained or zero | 126 | 0.188001 | explained | Definitional, not a model pathology. The scenario requires that where a quarter's GDP input equals Base, the GDP factor is exactly 1. The fitted replay carries recursive lag persistence from earlier stressed quarters, so its ratio drifts off 1 after the conflict path has already converged back to Base. The guard restores the identity the scenario definition demands. |
| low | downside_sign | zero unexpected bindings | 6 | 0.227134 | review_required | 6 wrong-sign bindings inside the Low stress window. Model pathology correction. A lower GDP input produced a HIGHER fitted activity factor - a wrong-sign out-of-distribution response. The guard caps it at no-change rather than reversing it, so the overlay never lets a downside scenario mechanically raise activity. |
| medium | any | retained as governed protection; disclose and quantify | 132 | 0.463269 | disclosed | 132 bindings, of which 9 are wrong-sign; 0 move the forecast by at least 0.5%; maximum 0.4633%; cumulative revenue-equivalent -85.9 $m. |
| high | any | retained as governed protection; disclose and quantify | 114 | 0.509457 | disclosed | 114 bindings, of which 42 are wrong-sign; 3 move the forecast by at least 0.5%; maximum 0.5095%; cumulative revenue-equivalent -109.4 $m. |

## Summary by severity, stream and reason

| severity | stream | guard_reason | n_bindings | first_quarter | last_quarter | max_abs_clip_amount | max_abs_forecast_delta_pct | cumulative_revenue_equivalent_nzd_m |
|---|---|---|---|---|---|---|---|---|
| high | HEAVY_RUC | identity_gdp_input_forces_identity_factor | 72 | 2031Q1 | 2036Q4 | 0.0003313 | 0.033119 | -2.23836 |
| high | HEAVY_RUC | positive_response_to_lower_gdp_capped_at_identity | 36 | 2028Q1 | 2030Q4 | 0.00512066 | 0.509457 | -93.1837 |
| high | PED | positive_response_to_lower_gdp_capped_at_identity | 6 | 2029Q2 | 2029Q3 | 0.0013363 | 0.133452 | -13.9914 |
| low | HEAVY_RUC | identity_gdp_input_forces_identity_factor | 81 | 2027Q2 | 2033Q4 | 0.00188355 | 0.188001 | -12.8856 |
| low | HEAVY_RUC | positive_response_to_lower_gdp_capped_at_identity | 6 | 2026Q4 | 2027Q1 | 0.00227651 | 0.227134 | -9.98367 |
| low | PED | identity_gdp_input_forces_identity_factor | 45 | 2027Q2 | 2032Q1 | 0.00137853 | 0.138043 | 39.6046 |
| medium | HEAVY_RUC | identity_gdp_input_forces_identity_factor | 84 | 2028Q2 | 2035Q1 | 0.00465425 | 0.463269 | -32.9648 |
| medium | HEAVY_RUC | positive_response_to_lower_gdp_capped_at_identity | 6 | 2027Q4 | 2028Q1 | 0.00454923 | 0.452863 | -21.1031 |
| medium | PED | identity_gdp_input_forces_identity_factor | 39 | 2028Q2 | 2032Q1 | 0.00138043 | 0.137853 | -31.4691 |
| medium | PED | positive_response_to_lower_gdp_capped_at_identity | 3 | 2028Q1 | 2028Q1 | 5.47486e-05 | 0.00547456 | -0.3281 |

Total bindings: 378.

## Every binding

| severity | scenario_name | stream | quarter | raw_gdp_model_factor | guarded_gdp_model_factor | clip_amount | guard_reason | forecast_delta | forecast_delta_pct | revenue_equivalent_delta_nzd_m |
|---|---|---|---|---|---|---|---|---|---|---|
| high | middle_east_high | HEAVY_RUC | 2028Q1 | 1.0012 | 1 | -0.00119659 | positive_response_to_lower_gdp_capped_at_identity | -1.21338e+06 | -0.119516 | -1.32656 |
| high | middle_east_high | HEAVY_RUC | 2028Q2 | 1.00512 | 1 | -0.00512066 | positive_response_to_lower_gdp_capped_at_identity | -5.08854e+06 | -0.509457 | -5.65472 |
| high | middle_east_high | HEAVY_RUC | 2028Q3 | 1.00439 | 1 | -0.0043918 | positive_response_to_lower_gdp_capped_at_identity | -4.44153e+06 | -0.43726 | -4.85337 |
| high | middle_east_high | HEAVY_RUC | 2028Q4 | 1.00402 | 1 | -0.00402462 | positive_response_to_lower_gdp_capped_at_identity | -4.31493e+06 | -0.400849 | -4.44922 |
| high | middle_east_high | HEAVY_RUC | 2029Q1 | 1.00357 | 1 | -0.00356653 | positive_response_to_lower_gdp_capped_at_identity | -3.72144e+06 | -0.355386 | -3.94461 |
| high | middle_east_high | HEAVY_RUC | 2029Q2 | 1.00294 | 1 | -0.00293704 | positive_response_to_lower_gdp_capped_at_identity | -2.99216e+06 | -0.292844 | -3.25042 |
| high | middle_east_high | HEAVY_RUC | 2029Q3 | 1.00209 | 1 | -0.0020859 | positive_response_to_lower_gdp_capped_at_identity | -2.15581e+06 | -0.208156 | -2.31043 |
| high | middle_east_high | HEAVY_RUC | 2029Q4 | 1.00153 | 1 | -0.00153295 | positive_response_to_lower_gdp_capped_at_identity | -1.67435e+06 | -0.15306 | -1.69889 |
| high | middle_east_high | HEAVY_RUC | 2030Q1 | 1.00118 | 1 | -0.00117556 | positive_response_to_lower_gdp_capped_at_identity | -1.24645e+06 | -0.117418 | -1.30328 |
| high | middle_east_high | HEAVY_RUC | 2030Q2 | 1.0009 | 1 | -0.000898579 | positive_response_to_lower_gdp_capped_at_identity | -928314 | -0.0897772 | -0.996482 |
| high | middle_east_high | HEAVY_RUC | 2030Q3 | 1.00065 | 1 | -0.000651512 | positive_response_to_lower_gdp_capped_at_identity | -681726 | -0.0651087 | -0.722675 |
| high | middle_east_high | HEAVY_RUC | 2030Q4 | 1.0005 | 1 | -0.000496296 | positive_response_to_lower_gdp_capped_at_identity | -547944 | -0.049605 | -0.550591 |
| high | middle_east_high | HEAVY_RUC | 2031Q1 | 1.00033 | 1 | -0.0003313 | identity_gdp_input_forces_identity_factor | -354626 | -0.033119 | -0.367605 |
| high | middle_east_high | HEAVY_RUC | 2031Q2 | 1.00018 | 1 | -0.000177565 | identity_gdp_input_forces_identity_factor | -185077 | -0.0177533 | -0.197053 |
| high | middle_east_high | HEAVY_RUC | 2031Q3 | 1.0001 | 1 | -9.55036e-05 | identity_gdp_input_forces_identity_factor | -100681 | -0.00954945 | -0.105994 |
| high | middle_east_high | HEAVY_RUC | 2031Q4 | 1.00004 | 1 | -4.22364e-05 | identity_gdp_input_forces_identity_factor | -46984.3 | -0.00422346 | -0.0468783 |
| high | middle_east_high | HEAVY_RUC | 2032Q1 | 1.00001 | 1 | -1.4058e-05 | identity_gdp_input_forces_identity_factor | -15146.9 | -0.00140578 | -0.0156035 |
| high | middle_east_high | HEAVY_RUC | 2032Q2 | 1.00001 | 1 | -6.17405e-06 | identity_gdp_input_forces_identity_factor | -6472.43 | -0.000617402 | -0.00685285 |
| high | middle_east_high | HEAVY_RUC | 2032Q3 | 1 | 1 | -3.23259e-06 | identity_gdp_input_forces_identity_factor | -3429.51 | -0.000323258 | -0.003588 |
| high | middle_east_high | HEAVY_RUC | 2032Q4 | 1 | 1 | -1.39441e-06 | identity_gdp_input_forces_identity_factor | -1560.59 | -0.000139441 | -0.00154772 |
| high | middle_east_high | HEAVY_RUC | 2033Q1 | 1 | 1 | -4.89875e-07 | identity_gdp_input_forces_identity_factor | -531.238 | -4.89875e-05 | -0.000543737 |
| high | middle_east_high | HEAVY_RUC | 2033Q2 | 1 | 1 | -2.17391e-07 | identity_gdp_input_forces_identity_factor | -229.384 | -2.17391e-05 | -0.000241293 |
| high | middle_east_high | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.12264e-07 | identity_gdp_input_forces_identity_factor | -119.901 | -1.12264e-05 | -0.000124608 |
| high | middle_east_high | HEAVY_RUC | 2033Q4 | 1 | 1 | -4.77401e-08 | identity_gdp_input_forces_identity_factor | -53.7705 | -4.77401e-06 | -5.29892e-05 |
| high | middle_east_high | HEAVY_RUC | 2034Q1 | 1 | 1 | -1.72351e-08 | identity_gdp_input_forces_identity_factor | -18.8209 | -1.72351e-06 | -1.91301e-05 |
| high | middle_east_high | HEAVY_RUC | 2034Q2 | 1 | 1 | -7.6724e-09 | identity_gdp_input_forces_identity_factor | -8.15257 | -7.6724e-07 | -8.51598e-06 |
| high | middle_east_high | HEAVY_RUC | 2034Q3 | 1 | 1 | -3.884e-09 | identity_gdp_input_forces_identity_factor | -4.1764 | -3.884e-07 | -4.31105e-06 |
| high | middle_east_high | HEAVY_RUC | 2034Q4 | 1 | 1 | -1.63647e-09 | identity_gdp_input_forces_identity_factor | -1.85544 | -1.63647e-07 | -1.8164e-06 |
| high | middle_east_high | HEAVY_RUC | 2035Q1 | 1 | 1 | -6.04492e-10 | identity_gdp_input_forces_identity_factor | -0.664345 | -6.04491e-08 | -6.70955e-07 |
| high | middle_east_high | HEAVY_RUC | 2035Q2 | 1 | 1 | -2.70348e-10 | identity_gdp_input_forces_identity_factor | -0.289005 | -2.70348e-08 | -3.00073e-07 |
| high | middle_east_high | HEAVY_RUC | 2035Q3 | 1 | 1 | -1.34244e-10 | identity_gdp_input_forces_identity_factor | -0.145207 | -1.34244e-08 | -1.49004e-07 |
| high | middle_east_high | HEAVY_RUC | 2035Q4 | 1 | 1 | -5.62317e-11 | identity_gdp_input_forces_identity_factor | -0.0641317 | -5.62317e-09 | -6.24144e-08 |
| high | middle_east_high | HEAVY_RUC | 2036Q1 | 1 | 1 | -2.11859e-11 | identity_gdp_input_forces_identity_factor | -0.0234156 | -2.11859e-09 | -2.35153e-08 |
| high | middle_east_high | HEAVY_RUC | 2036Q2 | 1 | 1 | -9.50817e-12 | identity_gdp_input_forces_identity_factor | -0.0102203 | -9.5082e-10 | -1.05536e-08 |
| high | middle_east_high | HEAVY_RUC | 2036Q3 | 1 | 1 | -4.63851e-12 | identity_gdp_input_forces_identity_factor | -0.00504446 | -4.6386e-10 | -5.14861e-09 |
| high | middle_east_high | HEAVY_RUC | 2036Q4 | 1 | 1 | -1.93578e-12 | identity_gdp_input_forces_identity_factor | -0.00221944 | -1.93577e-10 | -2.14861e-09 |
| high | middle_east_high | PED | 2029Q2 | 1.00134 | 1 | -0.0013363 | positive_response_to_lower_gdp_capped_at_identity | -2.02354 | -0.133452 | -2.666 |
| high | middle_east_high | PED | 2029Q3 | 1.001 | 1 | -0.00100104 | positive_response_to_lower_gdp_capped_at_identity | -1.52411 | -0.100004 | -1.99781 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q1 | 1.0012 | 1 | -0.00119659 | positive_response_to_lower_gdp_capped_at_identity | -1.21338e+06 | -0.119516 | -1.32656 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q2 | 1.00512 | 1 | -0.00512066 | positive_response_to_lower_gdp_capped_at_identity | -5.08854e+06 | -0.509457 | -5.65472 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q3 | 1.00439 | 1 | -0.0043918 | positive_response_to_lower_gdp_capped_at_identity | -4.44153e+06 | -0.43726 | -4.85337 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q4 | 1.00402 | 1 | -0.00402462 | positive_response_to_lower_gdp_capped_at_identity | -4.31493e+06 | -0.400849 | -4.44922 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q1 | 1.00357 | 1 | -0.00356653 | positive_response_to_lower_gdp_capped_at_identity | -3.72144e+06 | -0.355386 | -3.94461 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q2 | 1.00294 | 1 | -0.00293704 | positive_response_to_lower_gdp_capped_at_identity | -2.99216e+06 | -0.292844 | -3.25042 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q3 | 1.00209 | 1 | -0.0020859 | positive_response_to_lower_gdp_capped_at_identity | -2.15581e+06 | -0.208156 | -2.31043 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q4 | 1.00153 | 1 | -0.00153295 | positive_response_to_lower_gdp_capped_at_identity | -1.67435e+06 | -0.15306 | -1.69889 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q1 | 1.00118 | 1 | -0.00117556 | positive_response_to_lower_gdp_capped_at_identity | -1.24645e+06 | -0.117418 | -1.30328 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q2 | 1.0009 | 1 | -0.000898579 | positive_response_to_lower_gdp_capped_at_identity | -928314 | -0.0897772 | -0.996482 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q3 | 1.00065 | 1 | -0.000651512 | positive_response_to_lower_gdp_capped_at_identity | -681726 | -0.0651087 | -0.722675 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q4 | 1.0005 | 1 | -0.000496296 | positive_response_to_lower_gdp_capped_at_identity | -547944 | -0.049605 | -0.550591 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q1 | 1.00033 | 1 | -0.0003313 | identity_gdp_input_forces_identity_factor | -354626 | -0.033119 | -0.367605 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q2 | 1.00018 | 1 | -0.000177565 | identity_gdp_input_forces_identity_factor | -185077 | -0.0177533 | -0.197053 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q3 | 1.0001 | 1 | -9.55036e-05 | identity_gdp_input_forces_identity_factor | -100681 | -0.00954945 | -0.105994 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q4 | 1.00004 | 1 | -4.22364e-05 | identity_gdp_input_forces_identity_factor | -46984.3 | -0.00422346 | -0.0468783 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q1 | 1.00001 | 1 | -1.4058e-05 | identity_gdp_input_forces_identity_factor | -15146.9 | -0.00140578 | -0.0156035 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q2 | 1.00001 | 1 | -6.17405e-06 | identity_gdp_input_forces_identity_factor | -6472.43 | -0.000617402 | -0.00685285 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q3 | 1 | 1 | -3.23259e-06 | identity_gdp_input_forces_identity_factor | -3429.51 | -0.000323258 | -0.003588 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q4 | 1 | 1 | -1.39441e-06 | identity_gdp_input_forces_identity_factor | -1560.59 | -0.000139441 | -0.00154772 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q1 | 1 | 1 | -4.89875e-07 | identity_gdp_input_forces_identity_factor | -531.238 | -4.89875e-05 | -0.000543737 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q2 | 1 | 1 | -2.17391e-07 | identity_gdp_input_forces_identity_factor | -229.384 | -2.17391e-05 | -0.000241293 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.12264e-07 | identity_gdp_input_forces_identity_factor | -119.901 | -1.12264e-05 | -0.000124608 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q4 | 1 | 1 | -4.77401e-08 | identity_gdp_input_forces_identity_factor | -53.7705 | -4.77401e-06 | -5.29892e-05 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q1 | 1 | 1 | -1.72351e-08 | identity_gdp_input_forces_identity_factor | -18.8209 | -1.72351e-06 | -1.91301e-05 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q2 | 1 | 1 | -7.6724e-09 | identity_gdp_input_forces_identity_factor | -8.15257 | -7.6724e-07 | -8.51598e-06 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q3 | 1 | 1 | -3.884e-09 | identity_gdp_input_forces_identity_factor | -4.1764 | -3.884e-07 | -4.31105e-06 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q4 | 1 | 1 | -1.63647e-09 | identity_gdp_input_forces_identity_factor | -1.85544 | -1.63647e-07 | -1.8164e-06 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q1 | 1 | 1 | -6.04492e-10 | identity_gdp_input_forces_identity_factor | -0.664345 | -6.04491e-08 | -6.70955e-07 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q2 | 1 | 1 | -2.70348e-10 | identity_gdp_input_forces_identity_factor | -0.289005 | -2.70348e-08 | -3.00073e-07 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q3 | 1 | 1 | -1.34244e-10 | identity_gdp_input_forces_identity_factor | -0.145207 | -1.34244e-08 | -1.49004e-07 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q4 | 1 | 1 | -5.62317e-11 | identity_gdp_input_forces_identity_factor | -0.0641317 | -5.62317e-09 | -6.24144e-08 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q1 | 1 | 1 | -2.11859e-11 | identity_gdp_input_forces_identity_factor | -0.0234156 | -2.11859e-09 | -2.35153e-08 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q2 | 1 | 1 | -9.50817e-12 | identity_gdp_input_forces_identity_factor | -0.0102203 | -9.5082e-10 | -1.05536e-08 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q3 | 1 | 1 | -4.63851e-12 | identity_gdp_input_forces_identity_factor | -0.00504446 | -4.6386e-10 | -5.14861e-09 |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q4 | 1 | 1 | -1.93578e-12 | identity_gdp_input_forces_identity_factor | -0.00221944 | -1.93577e-10 | -2.14861e-09 |
| high | middle_east_high__12c_delay_6m | PED | 2029Q2 | 1.00134 | 1 | -0.0013363 | positive_response_to_lower_gdp_capped_at_identity | -2.02354 | -0.133452 | -2.666 |
| high | middle_east_high__12c_delay_6m | PED | 2029Q3 | 1.001 | 1 | -0.00100104 | positive_response_to_lower_gdp_capped_at_identity | -1.52411 | -0.100004 | -1.99781 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q1 | 1.0012 | 1 | -0.00119659 | positive_response_to_lower_gdp_capped_at_identity | -1.21643e+06 | -0.119516 | -1.32656 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q2 | 1.00512 | 1 | -0.00512066 | positive_response_to_lower_gdp_capped_at_identity | -5.10221e+06 | -0.509457 | -5.65472 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q3 | 1.00439 | 1 | -0.0043918 | positive_response_to_lower_gdp_capped_at_identity | -4.45413e+06 | -0.43726 | -4.85337 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q4 | 1.00402 | 1 | -0.00402462 | positive_response_to_lower_gdp_capped_at_identity | -4.32777e+06 | -0.400849 | -4.44922 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q1 | 1.00357 | 1 | -0.00356653 | positive_response_to_lower_gdp_capped_at_identity | -3.73246e+06 | -0.355386 | -3.94461 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q2 | 1.00294 | 1 | -0.00293704 | positive_response_to_lower_gdp_capped_at_identity | -3.00131e+06 | -0.292844 | -3.25042 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q3 | 1.00209 | 1 | -0.0020859 | positive_response_to_lower_gdp_capped_at_identity | -2.16256e+06 | -0.208156 | -2.31043 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q4 | 1.00153 | 1 | -0.00153295 | positive_response_to_lower_gdp_capped_at_identity | -1.67969e+06 | -0.15306 | -1.69889 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q1 | 1.00118 | 1 | -0.00117556 | positive_response_to_lower_gdp_capped_at_identity | -1.25033e+06 | -0.117418 | -1.30328 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q2 | 1.0009 | 1 | -0.000898579 | positive_response_to_lower_gdp_capped_at_identity | -931248 | -0.0897772 | -0.996482 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q3 | 1.00065 | 1 | -0.000651512 | positive_response_to_lower_gdp_capped_at_identity | -683901 | -0.0651087 | -0.722675 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q4 | 1.0005 | 1 | -0.000496296 | positive_response_to_lower_gdp_capped_at_identity | -549709 | -0.049605 | -0.550591 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q1 | 1.00033 | 1 | -0.0003313 | identity_gdp_input_forces_identity_factor | -355722 | -0.033119 | -0.367605 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q2 | 1.00018 | 1 | -0.000177565 | identity_gdp_input_forces_identity_factor | -185649 | -0.0177533 | -0.197053 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q3 | 1.0001 | 1 | -9.55036e-05 | identity_gdp_input_forces_identity_factor | -100681 | -0.00954945 | -0.105994 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q4 | 1.00004 | 1 | -4.22364e-05 | identity_gdp_input_forces_identity_factor | -46984.3 | -0.00422346 | -0.0468783 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q1 | 1.00001 | 1 | -1.4058e-05 | identity_gdp_input_forces_identity_factor | -15146.9 | -0.00140578 | -0.0156035 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q2 | 1.00001 | 1 | -6.17405e-06 | identity_gdp_input_forces_identity_factor | -6472.43 | -0.000617402 | -0.00685285 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q3 | 1 | 1 | -3.23259e-06 | identity_gdp_input_forces_identity_factor | -3429.51 | -0.000323258 | -0.003588 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q4 | 1 | 1 | -1.39441e-06 | identity_gdp_input_forces_identity_factor | -1560.59 | -0.000139441 | -0.00154772 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q1 | 1 | 1 | -4.89875e-07 | identity_gdp_input_forces_identity_factor | -531.238 | -4.89875e-05 | -0.000543737 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q2 | 1 | 1 | -2.17391e-07 | identity_gdp_input_forces_identity_factor | -229.384 | -2.17391e-05 | -0.000241293 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.12264e-07 | identity_gdp_input_forces_identity_factor | -119.901 | -1.12264e-05 | -0.000124608 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q4 | 1 | 1 | -4.77401e-08 | identity_gdp_input_forces_identity_factor | -53.7705 | -4.77401e-06 | -5.29892e-05 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q1 | 1 | 1 | -1.72351e-08 | identity_gdp_input_forces_identity_factor | -18.8209 | -1.72351e-06 | -1.91301e-05 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q2 | 1 | 1 | -7.6724e-09 | identity_gdp_input_forces_identity_factor | -8.15257 | -7.6724e-07 | -8.51598e-06 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q3 | 1 | 1 | -3.884e-09 | identity_gdp_input_forces_identity_factor | -4.1764 | -3.884e-07 | -4.31105e-06 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q4 | 1 | 1 | -1.63647e-09 | identity_gdp_input_forces_identity_factor | -1.85544 | -1.63647e-07 | -1.8164e-06 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q1 | 1 | 1 | -6.04492e-10 | identity_gdp_input_forces_identity_factor | -0.664345 | -6.04491e-08 | -6.70955e-07 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q2 | 1 | 1 | -2.70348e-10 | identity_gdp_input_forces_identity_factor | -0.289005 | -2.70348e-08 | -3.00073e-07 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q3 | 1 | 1 | -1.34244e-10 | identity_gdp_input_forces_identity_factor | -0.145207 | -1.34244e-08 | -1.49004e-07 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q4 | 1 | 1 | -5.62317e-11 | identity_gdp_input_forces_identity_factor | -0.0641317 | -5.62317e-09 | -6.24144e-08 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q1 | 1 | 1 | -2.11859e-11 | identity_gdp_input_forces_identity_factor | -0.0234156 | -2.11859e-09 | -2.35153e-08 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q2 | 1 | 1 | -9.50817e-12 | identity_gdp_input_forces_identity_factor | -0.0102203 | -9.5082e-10 | -1.05536e-08 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q3 | 1 | 1 | -4.63851e-12 | identity_gdp_input_forces_identity_factor | -0.00504446 | -4.6386e-10 | -5.14861e-09 |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q4 | 1 | 1 | -1.93578e-12 | identity_gdp_input_forces_identity_factor | -0.00221944 | -1.93577e-10 | -2.14861e-09 |
| high | middle_east_high__12c_no_uplift | PED | 2029Q2 | 1.00134 | 1 | -0.0013363 | positive_response_to_lower_gdp_capped_at_identity | -2.03496 | -0.133452 | -2.666 |
| high | middle_east_high__12c_no_uplift | PED | 2029Q3 | 1.001 | 1 | -0.00100104 | positive_response_to_lower_gdp_capped_at_identity | -1.53278 | -0.100004 | -1.99781 |
| low | middle_east_low | HEAVY_RUC | 2026Q4 | 1.00228 | 1 | -0.00227651 | positive_response_to_lower_gdp_capped_at_identity | -2.41984e+06 | -0.227134 | -2.52108 |
| low | middle_east_low | HEAVY_RUC | 2027Q1 | 1.00073 | 1 | -0.000727421 | positive_response_to_lower_gdp_capped_at_identity | -753803 | -0.0726892 | -0.806814 |
| low | middle_east_low | HEAVY_RUC | 2027Q2 | 1.00082 | 1 | -0.000824261 | identity_gdp_input_forces_identity_factor | -828598 | -0.0823583 | -0.914136 |
| low | middle_east_low | HEAVY_RUC | 2027Q3 | 1.00188 | 1 | -0.00188355 | identity_gdp_input_forces_identity_factor | -1.91859e+06 | -0.188001 | -2.08672 |
| low | middle_east_low | HEAVY_RUC | 2027Q4 | 1.00075 | 1 | -0.000745769 | identity_gdp_input_forces_identity_factor | -802132 | -0.0745213 | -0.827149 |
| low | middle_east_low | HEAVY_RUC | 2028Q1 | 1.00023 | 1 | -0.000229598 | identity_gdp_input_forces_identity_factor | -239439 | -0.0229545 | -0.254784 |
| low | middle_east_low | HEAVY_RUC | 2028Q2 | 1.00009 | 1 | -9.13792e-05 | identity_gdp_input_forces_identity_factor | -92807.9 | -0.00913709 | -0.101417 |
| low | middle_east_low | HEAVY_RUC | 2028Q3 | 1.00006 | 1 | -6.0907e-05 | identity_gdp_input_forces_identity_factor | -62646.3 | -0.00609032 | -0.0675996 |
| low | middle_east_low | HEAVY_RUC | 2028Q4 | 1.00002 | 1 | -2.48245e-05 | identity_gdp_input_forces_identity_factor | -26954 | -0.00248238 | -0.0275532 |
| low | middle_east_low | HEAVY_RUC | 2029Q1 | 1.00001 | 1 | -7.52518e-06 | identity_gdp_input_forces_identity_factor | -7924.15 | -0.000752512 | -0.00835251 |
| low | middle_east_low | HEAVY_RUC | 2029Q2 | 1 | 1 | -3.32747e-06 | identity_gdp_input_forces_identity_factor | -3411.86 | -0.000332746 | -0.00369331 |
| low | middle_east_low | HEAVY_RUC | 2029Q3 | 1 | 1 | -2.0736e-06 | identity_gdp_input_forces_identity_factor | -2153.03 | -0.000207359 | -0.00230159 |
| low | middle_east_low | HEAVY_RUC | 2029Q4 | 1 | 1 | -8.50645e-07 | identity_gdp_input_forces_identity_factor | -932.125 | -8.50644e-05 | -0.000944173 |
| low | middle_east_low | HEAVY_RUC | 2030Q1 | 1 | 1 | -2.64428e-07 | identity_gdp_input_forces_identity_factor | -280.894 | -2.64428e-05 | -0.000293502 |
| low | middle_east_low | HEAVY_RUC | 2030Q2 | 1 | 1 | -1.20833e-07 | identity_gdp_input_forces_identity_factor | -124.947 | -1.20833e-05 | -0.000134118 |
| low | middle_east_low | HEAVY_RUC | 2030Q3 | 1 | 1 | -7.09904e-08 | identity_gdp_input_forces_identity_factor | -74.3169 | -7.09904e-06 | -7.87958e-05 |
| low | middle_east_low | HEAVY_RUC | 2030Q4 | 1 | 1 | -2.89638e-08 | identity_gdp_input_forces_identity_factor | -31.978 | -2.89638e-06 | -3.21484e-05 |
| low | middle_east_low | HEAVY_RUC | 2031Q1 | 1 | 1 | -9.31027e-09 | identity_gdp_input_forces_identity_factor | -9.96578 | -9.31027e-07 | -1.03339e-05 |
| low | middle_east_low | HEAVY_RUC | 2031Q2 | 1 | 1 | -4.33016e-09 | identity_gdp_input_forces_identity_factor | -4.51336 | -4.33016e-07 | -4.80626e-06 |
| low | middle_east_low | HEAVY_RUC | 2031Q3 | 1 | 1 | -2.44078e-09 | identity_gdp_input_forces_identity_factor | -2.57309 | -2.44078e-07 | -2.70914e-06 |
| low | middle_east_low | HEAVY_RUC | 2031Q4 | 1 | 1 | -9.89366e-10 | identity_gdp_input_forces_identity_factor | -1.10058 | -9.89366e-08 | -1.09815e-06 |
| low | middle_east_low | HEAVY_RUC | 2032Q1 | 1 | 1 | -3.29418e-10 | identity_gdp_input_forces_identity_factor | -0.354934 | -3.29418e-08 | -3.65638e-07 |
| low | middle_east_low | HEAVY_RUC | 2032Q2 | 1 | 1 | -1.54599e-10 | identity_gdp_input_forces_identity_factor | -0.16207 | -1.54599e-08 | -1.71597e-07 |
| low | middle_east_low | HEAVY_RUC | 2032Q3 | 1 | 1 | -8.3938e-11 | identity_gdp_input_forces_identity_factor | -0.0890514 | -8.3938e-09 | -9.3167e-08 |
| low | middle_east_low | HEAVY_RUC | 2032Q4 | 1 | 1 | -3.38358e-11 | identity_gdp_input_forces_identity_factor | -0.0378683 | -3.38358e-09 | -3.7556e-08 |
| low | middle_east_low | HEAVY_RUC | 2033Q1 | 1 | 1 | -1.16329e-11 | identity_gdp_input_forces_identity_factor | -0.0126152 | -1.1633e-09 | -1.2912e-08 |
| low | middle_east_low | HEAVY_RUC | 2033Q2 | 1 | 1 | -5.48628e-12 | identity_gdp_input_forces_identity_factor | -0.00578892 | -5.48626e-10 | -6.08947e-09 |
| low | middle_east_low | HEAVY_RUC | 2033Q3 | 1 | 1 | -2.88436e-12 | identity_gdp_input_forces_identity_factor | -0.00308061 | -2.8844e-10 | -3.20154e-09 |
| low | middle_east_low | HEAVY_RUC | 2033Q4 | 1 | 1 | -1.16041e-12 | identity_gdp_input_forces_identity_factor | -0.00130701 | -1.16043e-10 | -1.28802e-09 |
| low | middle_east_low | PED | 2027Q2 | 0.9988 | 1 | 0.00119997 | identity_gdp_input_forces_identity_factor | 1.82923 | 0.120141 | 2.4001 |
| low | middle_east_low | PED | 2027Q3 | 0.999946 | 1 | 5.42344e-05 | identity_gdp_input_forces_identity_factor | 0.0830638 | 0.00542373 | 0.108351 |
| low | middle_east_low | PED | 2027Q4 | 1.00009 | 1 | -9.24272e-05 | identity_gdp_input_forces_identity_factor | -0.142972 | -0.00924186 | -0.184627 |
| low | middle_east_low | PED | 2028Q1 | 1.00007 | 1 | -7.10911e-05 | identity_gdp_input_forces_identity_factor | -0.109023 | -0.00710861 | -0.142011 |
| low | middle_east_low | PED | 2028Q2 | 1.00014 | 1 | -0.000143594 | identity_gdp_input_forces_identity_factor | -0.21941 | -0.0143574 | -0.286821 |
| low | middle_east_low | PED | 2029Q3 | 0.998664 | 1 | 0.00133573 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133752 | 2.672 |
| low | middle_east_low | PED | 2029Q4 | 0.998621 | 1 | 0.00137853 | identity_gdp_input_forces_identity_factor | 2.12522 | 0.138043 | 2.75772 |
| low | middle_east_low | PED | 2030Q1 | 0.998663 | 1 | 0.00133702 | identity_gdp_input_forces_identity_factor | 2.04234 | 0.133881 | 2.67457 |
| low | middle_east_low | PED | 2030Q2 | 0.998662 | 1 | 0.00133772 | identity_gdp_input_forces_identity_factor | 2.03542 | 0.133951 | 2.67598 |
| low | middle_east_low | PED | 2030Q3 | 0.998663 | 1 | 0.00133744 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133923 | 2.67542 |
| low | middle_east_low | PED | 2031Q1 | 1.00019 | 1 | -0.000190168 | identity_gdp_input_forces_identity_factor | -0.290852 | -0.0190132 | -0.379831 |
| low | middle_east_low | PED | 2031Q2 | 1.00024 | 1 | -0.000241456 | identity_gdp_input_forces_identity_factor | -0.367672 | -0.0241398 | -0.482247 |
| low | middle_east_low | PED | 2031Q3 | 1.00024 | 1 | -0.00024151 | identity_gdp_input_forces_identity_factor | -0.368935 | -0.0241451 | -0.482354 |
| low | middle_east_low | PED | 2031Q4 | 1.00024 | 1 | -0.000241076 | identity_gdp_input_forces_identity_factor | -0.371277 | -0.0241018 | -0.481489 |
| low | middle_east_low | PED | 2032Q1 | 1.00016 | 1 | -0.000161834 | identity_gdp_input_forces_identity_factor | -0.246832 | -0.0161808 | -0.323248 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2026Q4 | 1.00228 | 1 | -0.00227651 | positive_response_to_lower_gdp_capped_at_identity | -2.41984e+06 | -0.227134 | -2.52108 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q1 | 1.00073 | 1 | -0.000727421 | positive_response_to_lower_gdp_capped_at_identity | -756457 | -0.0726892 | -0.806814 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q2 | 1.00082 | 1 | -0.000824261 | identity_gdp_input_forces_identity_factor | -831528 | -0.0823583 | -0.914136 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q3 | 1.00188 | 1 | -0.00188355 | identity_gdp_input_forces_identity_factor | -1.91859e+06 | -0.188001 | -2.08672 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q4 | 1.00075 | 1 | -0.000745769 | identity_gdp_input_forces_identity_factor | -802132 | -0.0745213 | -0.827149 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q1 | 1.00023 | 1 | -0.000229598 | identity_gdp_input_forces_identity_factor | -239439 | -0.0229545 | -0.254784 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q2 | 1.00009 | 1 | -9.13792e-05 | identity_gdp_input_forces_identity_factor | -92807.9 | -0.00913709 | -0.101417 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q3 | 1.00006 | 1 | -6.0907e-05 | identity_gdp_input_forces_identity_factor | -62646.3 | -0.00609032 | -0.0675996 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q4 | 1.00002 | 1 | -2.48245e-05 | identity_gdp_input_forces_identity_factor | -26954 | -0.00248238 | -0.0275532 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q1 | 1.00001 | 1 | -7.52518e-06 | identity_gdp_input_forces_identity_factor | -7924.15 | -0.000752512 | -0.00835251 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q2 | 1 | 1 | -3.32747e-06 | identity_gdp_input_forces_identity_factor | -3411.86 | -0.000332746 | -0.00369331 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q3 | 1 | 1 | -2.0736e-06 | identity_gdp_input_forces_identity_factor | -2153.03 | -0.000207359 | -0.00230159 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q4 | 1 | 1 | -8.50645e-07 | identity_gdp_input_forces_identity_factor | -932.125 | -8.50644e-05 | -0.000944173 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q1 | 1 | 1 | -2.64428e-07 | identity_gdp_input_forces_identity_factor | -280.894 | -2.64428e-05 | -0.000293502 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q2 | 1 | 1 | -1.20833e-07 | identity_gdp_input_forces_identity_factor | -124.947 | -1.20833e-05 | -0.000134118 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q3 | 1 | 1 | -7.09904e-08 | identity_gdp_input_forces_identity_factor | -74.3169 | -7.09904e-06 | -7.87958e-05 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q4 | 1 | 1 | -2.89638e-08 | identity_gdp_input_forces_identity_factor | -31.978 | -2.89638e-06 | -3.21484e-05 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q1 | 1 | 1 | -9.31027e-09 | identity_gdp_input_forces_identity_factor | -9.96578 | -9.31027e-07 | -1.03339e-05 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q2 | 1 | 1 | -4.33016e-09 | identity_gdp_input_forces_identity_factor | -4.51336 | -4.33016e-07 | -4.80626e-06 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q3 | 1 | 1 | -2.44078e-09 | identity_gdp_input_forces_identity_factor | -2.57309 | -2.44078e-07 | -2.70914e-06 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q4 | 1 | 1 | -9.89366e-10 | identity_gdp_input_forces_identity_factor | -1.10058 | -9.89366e-08 | -1.09815e-06 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q1 | 1 | 1 | -3.29418e-10 | identity_gdp_input_forces_identity_factor | -0.354934 | -3.29418e-08 | -3.65638e-07 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q2 | 1 | 1 | -1.54599e-10 | identity_gdp_input_forces_identity_factor | -0.16207 | -1.54599e-08 | -1.71597e-07 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q3 | 1 | 1 | -8.3938e-11 | identity_gdp_input_forces_identity_factor | -0.0890514 | -8.3938e-09 | -9.3167e-08 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q4 | 1 | 1 | -3.38358e-11 | identity_gdp_input_forces_identity_factor | -0.0378683 | -3.38358e-09 | -3.7556e-08 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q1 | 1 | 1 | -1.16329e-11 | identity_gdp_input_forces_identity_factor | -0.0126152 | -1.1633e-09 | -1.2912e-08 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q2 | 1 | 1 | -5.48628e-12 | identity_gdp_input_forces_identity_factor | -0.00578892 | -5.48626e-10 | -6.08947e-09 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q3 | 1 | 1 | -2.88436e-12 | identity_gdp_input_forces_identity_factor | -0.00308061 | -2.8844e-10 | -3.20154e-09 |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q4 | 1 | 1 | -1.16041e-12 | identity_gdp_input_forces_identity_factor | -0.00130701 | -1.16043e-10 | -1.28802e-09 |
| low | middle_east_low__12c_delay_6m | PED | 2027Q2 | 0.9988 | 1 | 0.00119997 | identity_gdp_input_forces_identity_factor | 1.84029 | 0.120141 | 2.4001 |
| low | middle_east_low__12c_delay_6m | PED | 2027Q3 | 0.999946 | 1 | 5.42344e-05 | identity_gdp_input_forces_identity_factor | 0.0830638 | 0.00542373 | 0.108351 |
| low | middle_east_low__12c_delay_6m | PED | 2027Q4 | 1.00009 | 1 | -9.24272e-05 | identity_gdp_input_forces_identity_factor | -0.142972 | -0.00924186 | -0.184627 |
| low | middle_east_low__12c_delay_6m | PED | 2028Q1 | 1.00007 | 1 | -7.10911e-05 | identity_gdp_input_forces_identity_factor | -0.109023 | -0.00710861 | -0.142011 |
| low | middle_east_low__12c_delay_6m | PED | 2028Q2 | 1.00014 | 1 | -0.000143594 | identity_gdp_input_forces_identity_factor | -0.21941 | -0.0143574 | -0.286821 |
| low | middle_east_low__12c_delay_6m | PED | 2029Q3 | 0.998664 | 1 | 0.00133573 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133752 | 2.672 |
| low | middle_east_low__12c_delay_6m | PED | 2029Q4 | 0.998621 | 1 | 0.00137853 | identity_gdp_input_forces_identity_factor | 2.12522 | 0.138043 | 2.75772 |
| low | middle_east_low__12c_delay_6m | PED | 2030Q1 | 0.998663 | 1 | 0.00133702 | identity_gdp_input_forces_identity_factor | 2.04234 | 0.133881 | 2.67457 |
| low | middle_east_low__12c_delay_6m | PED | 2030Q2 | 0.998662 | 1 | 0.00133772 | identity_gdp_input_forces_identity_factor | 2.03542 | 0.133951 | 2.67598 |
| low | middle_east_low__12c_delay_6m | PED | 2030Q3 | 0.998663 | 1 | 0.00133744 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133923 | 2.67542 |
| low | middle_east_low__12c_delay_6m | PED | 2031Q1 | 1.00019 | 1 | -0.000190168 | identity_gdp_input_forces_identity_factor | -0.290852 | -0.0190132 | -0.379831 |
| low | middle_east_low__12c_delay_6m | PED | 2031Q2 | 1.00024 | 1 | -0.000241456 | identity_gdp_input_forces_identity_factor | -0.367672 | -0.0241398 | -0.482247 |
| low | middle_east_low__12c_delay_6m | PED | 2031Q3 | 1.00024 | 1 | -0.00024151 | identity_gdp_input_forces_identity_factor | -0.368935 | -0.0241451 | -0.482354 |
| low | middle_east_low__12c_delay_6m | PED | 2031Q4 | 1.00024 | 1 | -0.000241076 | identity_gdp_input_forces_identity_factor | -0.371277 | -0.0241018 | -0.481489 |
| low | middle_east_low__12c_delay_6m | PED | 2032Q1 | 1.00016 | 1 | -0.000161834 | identity_gdp_input_forces_identity_factor | -0.246832 | -0.0161808 | -0.323248 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2026Q4 | 1.00228 | 1 | -0.00227651 | positive_response_to_lower_gdp_capped_at_identity | -2.41984e+06 | -0.227134 | -2.52108 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q1 | 1.00073 | 1 | -0.000727421 | positive_response_to_lower_gdp_capped_at_identity | -756457 | -0.0726892 | -0.806814 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q2 | 1.00082 | 1 | -0.000824261 | identity_gdp_input_forces_identity_factor | -831528 | -0.0823583 | -0.914136 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q3 | 1.00188 | 1 | -0.00188355 | identity_gdp_input_forces_identity_factor | -1.92541e+06 | -0.188001 | -2.08672 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q4 | 1.00075 | 1 | -0.000745769 | identity_gdp_input_forces_identity_factor | -804995 | -0.0745213 | -0.827149 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q1 | 1.00023 | 1 | -0.000229598 | identity_gdp_input_forces_identity_factor | -240238 | -0.0229545 | -0.254784 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q2 | 1.00009 | 1 | -9.13792e-05 | identity_gdp_input_forces_identity_factor | -93119.1 | -0.00913709 | -0.101417 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q3 | 1.00006 | 1 | -6.0907e-05 | identity_gdp_input_forces_identity_factor | -62857.3 | -0.00609032 | -0.0675996 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q4 | 1.00002 | 1 | -2.48245e-05 | identity_gdp_input_forces_identity_factor | -27045.2 | -0.00248238 | -0.0275532 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q1 | 1.00001 | 1 | -7.52518e-06 | identity_gdp_input_forces_identity_factor | -7949.92 | -0.000752512 | -0.00835251 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q2 | 1 | 1 | -3.32747e-06 | identity_gdp_input_forces_identity_factor | -3423.01 | -0.000332746 | -0.00369331 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q3 | 1 | 1 | -2.0736e-06 | identity_gdp_input_forces_identity_factor | -2160.1 | -0.000207359 | -0.00230159 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q4 | 1 | 1 | -8.50645e-07 | identity_gdp_input_forces_identity_factor | -935.2 | -8.50644e-05 | -0.000944173 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q1 | 1 | 1 | -2.64428e-07 | identity_gdp_input_forces_identity_factor | -281.785 | -2.64428e-05 | -0.000293502 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q2 | 1 | 1 | -1.20833e-07 | identity_gdp_input_forces_identity_factor | -125.345 | -1.20833e-05 | -0.000134118 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q3 | 1 | 1 | -7.09904e-08 | identity_gdp_input_forces_identity_factor | -74.5552 | -7.09904e-06 | -7.87958e-05 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q4 | 1 | 1 | -2.89638e-08 | identity_gdp_input_forces_identity_factor | -32.081 | -2.89638e-06 | -3.21484e-05 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q1 | 1 | 1 | -9.31027e-09 | identity_gdp_input_forces_identity_factor | -9.99658 | -9.31027e-07 | -1.03339e-05 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q2 | 1 | 1 | -4.33016e-09 | identity_gdp_input_forces_identity_factor | -4.52731 | -4.33016e-07 | -4.80626e-06 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q3 | 1 | 1 | -2.44078e-09 | identity_gdp_input_forces_identity_factor | -2.57309 | -2.44078e-07 | -2.70914e-06 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q4 | 1 | 1 | -9.89366e-10 | identity_gdp_input_forces_identity_factor | -1.10058 | -9.89366e-08 | -1.09815e-06 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q1 | 1 | 1 | -3.29418e-10 | identity_gdp_input_forces_identity_factor | -0.354934 | -3.29418e-08 | -3.65638e-07 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q2 | 1 | 1 | -1.54599e-10 | identity_gdp_input_forces_identity_factor | -0.16207 | -1.54599e-08 | -1.71597e-07 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q3 | 1 | 1 | -8.3938e-11 | identity_gdp_input_forces_identity_factor | -0.0890514 | -8.3938e-09 | -9.3167e-08 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q4 | 1 | 1 | -3.38358e-11 | identity_gdp_input_forces_identity_factor | -0.0378683 | -3.38358e-09 | -3.7556e-08 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q1 | 1 | 1 | -1.16329e-11 | identity_gdp_input_forces_identity_factor | -0.0126152 | -1.1633e-09 | -1.2912e-08 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q2 | 1 | 1 | -5.48628e-12 | identity_gdp_input_forces_identity_factor | -0.00578892 | -5.48626e-10 | -6.08947e-09 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q3 | 1 | 1 | -2.88436e-12 | identity_gdp_input_forces_identity_factor | -0.00308061 | -2.8844e-10 | -3.20154e-09 |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q4 | 1 | 1 | -1.16041e-12 | identity_gdp_input_forces_identity_factor | -0.00130701 | -1.16043e-10 | -1.28802e-09 |
| low | middle_east_low__12c_no_uplift | PED | 2027Q2 | 0.9988 | 1 | 0.00119997 | identity_gdp_input_forces_identity_factor | 1.84029 | 0.120141 | 2.4001 |
| low | middle_east_low__12c_no_uplift | PED | 2027Q3 | 0.999946 | 1 | 5.42344e-05 | identity_gdp_input_forces_identity_factor | 0.0835641 | 0.00542373 | 0.108351 |
| low | middle_east_low__12c_no_uplift | PED | 2027Q4 | 1.00009 | 1 | -9.24272e-05 | identity_gdp_input_forces_identity_factor | -0.14383 | -0.00924186 | -0.184627 |
| low | middle_east_low__12c_no_uplift | PED | 2028Q1 | 1.00007 | 1 | -7.10911e-05 | identity_gdp_input_forces_identity_factor | -0.109676 | -0.00710861 | -0.142011 |
| low | middle_east_low__12c_no_uplift | PED | 2028Q2 | 1.00014 | 1 | -0.000143594 | identity_gdp_input_forces_identity_factor | -0.220718 | -0.0143574 | -0.286821 |
| low | middle_east_low__12c_no_uplift | PED | 2029Q3 | 0.998664 | 1 | 0.00133573 | identity_gdp_input_forces_identity_factor | 2.05438 | 0.133752 | 2.672 |
| low | middle_east_low__12c_no_uplift | PED | 2029Q4 | 0.998621 | 1 | 0.00137853 | identity_gdp_input_forces_identity_factor | 2.13763 | 0.138043 | 2.75772 |
| low | middle_east_low__12c_no_uplift | PED | 2030Q1 | 0.998663 | 1 | 0.00133702 | identity_gdp_input_forces_identity_factor | 2.05422 | 0.133881 | 2.67457 |
| low | middle_east_low__12c_no_uplift | PED | 2030Q2 | 0.998662 | 1 | 0.00133772 | identity_gdp_input_forces_identity_factor | 2.04723 | 0.133951 | 2.67598 |
| low | middle_east_low__12c_no_uplift | PED | 2030Q3 | 0.998663 | 1 | 0.00133744 | identity_gdp_input_forces_identity_factor | 2.05422 | 0.133923 | 2.67542 |
| low | middle_east_low__12c_no_uplift | PED | 2031Q1 | 1.00019 | 1 | -0.000190168 | identity_gdp_input_forces_identity_factor | -0.292523 | -0.0190132 | -0.379831 |
| low | middle_east_low__12c_no_uplift | PED | 2031Q2 | 1.00024 | 1 | -0.000241456 | identity_gdp_input_forces_identity_factor | -0.369777 | -0.0241398 | -0.482247 |
| low | middle_east_low__12c_no_uplift | PED | 2031Q3 | 1.00024 | 1 | -0.00024151 | identity_gdp_input_forces_identity_factor | -0.368935 | -0.0241451 | -0.482354 |
| low | middle_east_low__12c_no_uplift | PED | 2031Q4 | 1.00024 | 1 | -0.000241076 | identity_gdp_input_forces_identity_factor | -0.371277 | -0.0241018 | -0.481489 |
| low | middle_east_low__12c_no_uplift | PED | 2032Q1 | 1.00016 | 1 | -0.000161834 | identity_gdp_input_forces_identity_factor | -0.246832 | -0.0161808 | -0.323248 |
| medium | middle_east_medium | HEAVY_RUC | 2027Q4 | 1.00181 | 1 | -0.0018122 | positive_response_to_lower_gdp_capped_at_identity | -1.93101e+06 | -0.180892 | -2.00782 |
| medium | middle_east_medium | HEAVY_RUC | 2028Q1 | 1.00455 | 1 | -0.00454923 | positive_response_to_lower_gdp_capped_at_identity | -4.74421e+06 | -0.452863 | -5.02655 |
| medium | middle_east_medium | HEAVY_RUC | 2028Q2 | 1.00465 | 1 | -0.00465425 | identity_gdp_input_forces_identity_factor | -4.72702e+06 | -0.463269 | -5.14206 |
| medium | middle_east_medium | HEAVY_RUC | 2028Q3 | 1.0026 | 1 | -0.0025987 | identity_gdp_input_forces_identity_factor | -2.67291e+06 | -0.259197 | -2.87695 |
| medium | middle_east_medium | HEAVY_RUC | 2028Q4 | 1.00162 | 1 | -0.00161756 | identity_gdp_input_forces_identity_factor | -1.75631e+06 | -0.161494 | -1.79251 |
| medium | middle_east_medium | HEAVY_RUC | 2029Q1 | 1.00069 | 1 | -0.000687164 | identity_gdp_input_forces_identity_factor | -723597 | -0.0686692 | -0.762194 |
| medium | middle_east_medium | HEAVY_RUC | 2029Q2 | 1.00019 | 1 | -0.000192813 | identity_gdp_input_forces_identity_factor | -197704 | -0.0192776 | -0.213972 |
| medium | middle_east_medium | HEAVY_RUC | 2029Q3 | 1.00009 | 1 | -9.12137e-05 | identity_gdp_input_forces_identity_factor | -94707.8 | -0.00912054 | -0.101233 |
| medium | middle_east_medium | HEAVY_RUC | 2029Q4 | 1.00005 | 1 | -5.41745e-05 | identity_gdp_input_forces_identity_factor | -59363.7 | -0.00541715 | -0.0601277 |
| medium | middle_east_medium | HEAVY_RUC | 2030Q1 | 1.00002 | 1 | -2.22489e-05 | identity_gdp_input_forces_identity_factor | -23634.3 | -0.00222484 | -0.0246946 |
| medium | middle_east_medium | HEAVY_RUC | 2030Q2 | 1.00001 | 1 | -6.76794e-06 | identity_gdp_input_forces_identity_factor | -6998.38 | -0.00067679 | -0.00751203 |
| medium | middle_east_medium | HEAVY_RUC | 2030Q3 | 1 | 1 | -3.24058e-06 | identity_gdp_input_forces_identity_factor | -3392.43 | -0.000324057 | -0.00359687 |
| medium | middle_east_medium | HEAVY_RUC | 2030Q4 | 1 | 1 | -1.87241e-06 | identity_gdp_input_forces_identity_factor | -2067.27 | -0.000187241 | -0.00207828 |
| medium | middle_east_medium | HEAVY_RUC | 2031Q1 | 1 | 1 | -7.54795e-07 | identity_gdp_input_forces_identity_factor | -807.938 | -7.54794e-05 | -0.000837784 |
| medium | middle_east_medium | HEAVY_RUC | 2031Q2 | 1 | 1 | -2.4089e-07 | identity_gdp_input_forces_identity_factor | -251.081 | -2.40889e-05 | -0.000267375 |
| medium | middle_east_medium | HEAVY_RUC | 2031Q3 | 1 | 1 | -1.15655e-07 | identity_gdp_input_forces_identity_factor | -121.924 | -1.15655e-05 | -0.000128371 |
| medium | middle_east_medium | HEAVY_RUC | 2031Q4 | 1 | 1 | -6.44945e-08 | identity_gdp_input_forces_identity_factor | -71.7444 | -6.44945e-06 | -7.15857e-05 |
| medium | middle_east_medium | HEAVY_RUC | 2032Q1 | 1 | 1 | -2.57549e-08 | identity_gdp_input_forces_identity_factor | -27.7498 | -2.57549e-06 | -2.85867e-05 |
| medium | middle_east_medium | HEAVY_RUC | 2032Q2 | 1 | 1 | -8.55656e-09 | identity_gdp_input_forces_identity_factor | -8.97007 | -8.55655e-07 | -9.49735e-06 |
| medium | middle_east_medium | HEAVY_RUC | 2032Q3 | 1 | 1 | -4.11119e-09 | identity_gdp_input_forces_identity_factor | -4.36164 | -4.11119e-07 | -4.56322e-06 |
| medium | middle_east_medium | HEAVY_RUC | 2032Q4 | 1 | 1 | -2.21801e-09 | identity_gdp_input_forces_identity_factor | -2.48235 | -2.21801e-07 | -2.46188e-06 |
| medium | middle_east_medium | HEAVY_RUC | 2033Q1 | 1 | 1 | -8.80012e-10 | identity_gdp_input_forces_identity_factor | -0.954316 | -8.80012e-08 | -9.76769e-07 |
| medium | middle_east_medium | HEAVY_RUC | 2033Q2 | 1 | 1 | -3.02855e-10 | identity_gdp_input_forces_identity_factor | -0.319563 | -3.02855e-08 | -3.36154e-07 |
| medium | middle_east_medium | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.45577e-10 | identity_gdp_input_forces_identity_factor | -0.155479 | -1.45577e-08 | -1.61583e-07 |
| medium | middle_east_medium | HEAVY_RUC | 2033Q4 | 1 | 1 | -7.62648e-11 | identity_gdp_input_forces_identity_factor | -0.0858984 | -7.62649e-09 | -8.46502e-08 |
| medium | middle_east_medium | HEAVY_RUC | 2034Q1 | 1 | 1 | -3.01599e-11 | identity_gdp_input_forces_identity_factor | -0.0329349 | -3.01598e-09 | -3.34759e-08 |
| medium | middle_east_medium | HEAVY_RUC | 2034Q2 | 1 | 1 | -1.07048e-11 | identity_gdp_input_forces_identity_factor | -0.0113747 | -1.07048e-09 | -1.18818e-08 |
| medium | middle_east_medium | HEAVY_RUC | 2034Q3 | 1 | 1 | -5.13944e-12 | identity_gdp_input_forces_identity_factor | -0.0055263 | -5.13939e-10 | -5.70447e-09 |
| medium | middle_east_medium | HEAVY_RUC | 2034Q4 | 1 | 1 | -2.62035e-12 | identity_gdp_input_forces_identity_factor | -0.00297093 | -2.62032e-10 | -2.90843e-09 |
| medium | middle_east_medium | HEAVY_RUC | 2035Q1 | 1 | 1 | -1.03473e-12 | identity_gdp_input_forces_identity_factor | -0.00113726 | -1.0348e-10 | -1.14857e-09 |
| medium | middle_east_medium | PED | 2028Q1 | 1.00005 | 1 | -5.47486e-05 | positive_response_to_lower_gdp_capped_at_identity | -0.083961 | -0.00547456 | -0.109367 |
| medium | middle_east_medium | PED | 2028Q2 | 0.999543 | 1 | 0.000457243 | identity_gdp_input_forces_identity_factor | 0.69866 | 0.0457452 | 0.913864 |
| medium | middle_east_medium | PED | 2028Q3 | 1.00013 | 1 | -0.000129983 | identity_gdp_input_forces_identity_factor | -0.199374 | -0.0129967 | -0.259638 |
| medium | middle_east_medium | PED | 2028Q4 | 0.999928 | 1 | 7.20831e-05 | identity_gdp_input_forces_identity_factor | 0.111531 | 0.00720882 | 0.144013 |
| medium | middle_east_medium | PED | 2029Q3 | 1.00134 | 1 | -0.00133752 | identity_gdp_input_forces_identity_factor | -2.04514 | -0.133573 | -2.66843 |
| medium | middle_east_medium | PED | 2029Q4 | 1.00138 | 1 | -0.00138043 | identity_gdp_input_forces_identity_factor | -2.12816 | -0.137853 | -2.75392 |
| medium | middle_east_medium | PED | 2030Q1 | 1.00134 | 1 | -0.00133881 | identity_gdp_input_forces_identity_factor | -2.04507 | -0.133702 | -2.671 |
| medium | middle_east_medium | PED | 2030Q2 | 1.00134 | 1 | -0.00133951 | identity_gdp_input_forces_identity_factor | -2.03815 | -0.133772 | -2.6724 |
| medium | middle_east_medium | PED | 2030Q3 | 1.00134 | 1 | -0.00133923 | identity_gdp_input_forces_identity_factor | -2.04515 | -0.133744 | -2.67184 |
| medium | middle_east_medium | PED | 2031Q1 | 0.99981 | 1 | 0.000190132 | identity_gdp_input_forces_identity_factor | 0.290797 | 0.0190168 | 0.379903 |
| medium | middle_east_medium | PED | 2031Q2 | 0.999759 | 1 | 0.000241398 | identity_gdp_input_forces_identity_factor | 0.367584 | 0.0241456 | 0.482364 |
| medium | middle_east_medium | PED | 2031Q3 | 0.999759 | 1 | 0.000241451 | identity_gdp_input_forces_identity_factor | 0.368846 | 0.024151 | 0.48247 |
| medium | middle_east_medium | PED | 2031Q4 | 0.999759 | 1 | 0.000241018 | identity_gdp_input_forces_identity_factor | 0.371187 | 0.0241076 | 0.481605 |
| medium | middle_east_medium | PED | 2032Q1 | 0.999838 | 1 | 0.000161808 | identity_gdp_input_forces_identity_factor | 0.246792 | 0.0161834 | 0.3233 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2027Q4 | 1.00181 | 1 | -0.0018122 | positive_response_to_lower_gdp_capped_at_identity | -1.93101e+06 | -0.180892 | -2.00782 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q1 | 1.00455 | 1 | -0.00454923 | positive_response_to_lower_gdp_capped_at_identity | -4.74421e+06 | -0.452863 | -5.02655 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q2 | 1.00465 | 1 | -0.00465425 | identity_gdp_input_forces_identity_factor | -4.72702e+06 | -0.463269 | -5.14206 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q3 | 1.0026 | 1 | -0.0025987 | identity_gdp_input_forces_identity_factor | -2.67291e+06 | -0.259197 | -2.87695 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q4 | 1.00162 | 1 | -0.00161756 | identity_gdp_input_forces_identity_factor | -1.75631e+06 | -0.161494 | -1.79251 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q1 | 1.00069 | 1 | -0.000687164 | identity_gdp_input_forces_identity_factor | -723597 | -0.0686692 | -0.762194 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q2 | 1.00019 | 1 | -0.000192813 | identity_gdp_input_forces_identity_factor | -197704 | -0.0192776 | -0.213972 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q3 | 1.00009 | 1 | -9.12137e-05 | identity_gdp_input_forces_identity_factor | -94707.8 | -0.00912054 | -0.101233 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q4 | 1.00005 | 1 | -5.41745e-05 | identity_gdp_input_forces_identity_factor | -59363.7 | -0.00541715 | -0.0601277 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q1 | 1.00002 | 1 | -2.22489e-05 | identity_gdp_input_forces_identity_factor | -23634.3 | -0.00222484 | -0.0246946 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q2 | 1.00001 | 1 | -6.76794e-06 | identity_gdp_input_forces_identity_factor | -6998.38 | -0.00067679 | -0.00751203 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q3 | 1 | 1 | -3.24058e-06 | identity_gdp_input_forces_identity_factor | -3392.43 | -0.000324057 | -0.00359687 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q4 | 1 | 1 | -1.87241e-06 | identity_gdp_input_forces_identity_factor | -2067.27 | -0.000187241 | -0.00207828 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q1 | 1 | 1 | -7.54795e-07 | identity_gdp_input_forces_identity_factor | -807.938 | -7.54794e-05 | -0.000837784 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q2 | 1 | 1 | -2.4089e-07 | identity_gdp_input_forces_identity_factor | -251.081 | -2.40889e-05 | -0.000267375 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q3 | 1 | 1 | -1.15655e-07 | identity_gdp_input_forces_identity_factor | -121.924 | -1.15655e-05 | -0.000128371 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q4 | 1 | 1 | -6.44945e-08 | identity_gdp_input_forces_identity_factor | -71.7444 | -6.44945e-06 | -7.15857e-05 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q1 | 1 | 1 | -2.57549e-08 | identity_gdp_input_forces_identity_factor | -27.7498 | -2.57549e-06 | -2.85867e-05 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q2 | 1 | 1 | -8.55656e-09 | identity_gdp_input_forces_identity_factor | -8.97007 | -8.55655e-07 | -9.49735e-06 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q3 | 1 | 1 | -4.11119e-09 | identity_gdp_input_forces_identity_factor | -4.36164 | -4.11119e-07 | -4.56322e-06 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q4 | 1 | 1 | -2.21801e-09 | identity_gdp_input_forces_identity_factor | -2.48235 | -2.21801e-07 | -2.46188e-06 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q1 | 1 | 1 | -8.80012e-10 | identity_gdp_input_forces_identity_factor | -0.954316 | -8.80012e-08 | -9.76769e-07 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q2 | 1 | 1 | -3.02855e-10 | identity_gdp_input_forces_identity_factor | -0.319563 | -3.02855e-08 | -3.36154e-07 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.45577e-10 | identity_gdp_input_forces_identity_factor | -0.155479 | -1.45577e-08 | -1.61583e-07 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q4 | 1 | 1 | -7.62648e-11 | identity_gdp_input_forces_identity_factor | -0.0858984 | -7.62649e-09 | -8.46502e-08 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q1 | 1 | 1 | -3.01599e-11 | identity_gdp_input_forces_identity_factor | -0.0329349 | -3.01598e-09 | -3.34759e-08 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q2 | 1 | 1 | -1.07048e-11 | identity_gdp_input_forces_identity_factor | -0.0113747 | -1.07048e-09 | -1.18818e-08 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q3 | 1 | 1 | -5.13944e-12 | identity_gdp_input_forces_identity_factor | -0.0055263 | -5.13939e-10 | -5.70447e-09 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q4 | 1 | 1 | -2.62035e-12 | identity_gdp_input_forces_identity_factor | -0.00297093 | -2.62032e-10 | -2.90843e-09 |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2035Q1 | 1 | 1 | -1.03473e-12 | identity_gdp_input_forces_identity_factor | -0.00113726 | -1.0348e-10 | -1.14857e-09 |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q1 | 1.00005 | 1 | -5.47486e-05 | positive_response_to_lower_gdp_capped_at_identity | -0.083961 | -0.00547456 | -0.109367 |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q2 | 0.999543 | 1 | 0.000457243 | identity_gdp_input_forces_identity_factor | 0.69866 | 0.0457452 | 0.913864 |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q3 | 1.00013 | 1 | -0.000129983 | identity_gdp_input_forces_identity_factor | -0.199374 | -0.0129967 | -0.259638 |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q4 | 0.999928 | 1 | 7.20831e-05 | identity_gdp_input_forces_identity_factor | 0.111531 | 0.00720882 | 0.144013 |
| medium | middle_east_medium__12c_delay_6m | PED | 2029Q3 | 1.00134 | 1 | -0.00133752 | identity_gdp_input_forces_identity_factor | -2.04514 | -0.133573 | -2.66843 |
| medium | middle_east_medium__12c_delay_6m | PED | 2029Q4 | 1.00138 | 1 | -0.00138043 | identity_gdp_input_forces_identity_factor | -2.12816 | -0.137853 | -2.75392 |
| medium | middle_east_medium__12c_delay_6m | PED | 2030Q1 | 1.00134 | 1 | -0.00133881 | identity_gdp_input_forces_identity_factor | -2.04507 | -0.133702 | -2.671 |
| medium | middle_east_medium__12c_delay_6m | PED | 2030Q2 | 1.00134 | 1 | -0.00133951 | identity_gdp_input_forces_identity_factor | -2.03815 | -0.133772 | -2.6724 |
| medium | middle_east_medium__12c_delay_6m | PED | 2030Q3 | 1.00134 | 1 | -0.00133923 | identity_gdp_input_forces_identity_factor | -2.04515 | -0.133744 | -2.67184 |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q1 | 0.99981 | 1 | 0.000190132 | identity_gdp_input_forces_identity_factor | 0.290797 | 0.0190168 | 0.379903 |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q2 | 0.999759 | 1 | 0.000241398 | identity_gdp_input_forces_identity_factor | 0.367584 | 0.0241456 | 0.482364 |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q3 | 0.999759 | 1 | 0.000241451 | identity_gdp_input_forces_identity_factor | 0.368846 | 0.024151 | 0.48247 |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q4 | 0.999759 | 1 | 0.000241018 | identity_gdp_input_forces_identity_factor | 0.371187 | 0.0241076 | 0.481605 |
| medium | middle_east_medium__12c_delay_6m | PED | 2032Q1 | 0.999838 | 1 | 0.000161808 | identity_gdp_input_forces_identity_factor | 0.246792 | 0.0161834 | 0.3233 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2027Q4 | 1.00181 | 1 | -0.0018122 | positive_response_to_lower_gdp_capped_at_identity | -1.93728e+06 | -0.180892 | -2.00782 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q1 | 1.00455 | 1 | -0.00454923 | positive_response_to_lower_gdp_capped_at_identity | -4.76005e+06 | -0.452863 | -5.02655 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q2 | 1.00465 | 1 | -0.00465425 | identity_gdp_input_forces_identity_factor | -4.74287e+06 | -0.463269 | -5.14206 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q3 | 1.0026 | 1 | -0.0025987 | identity_gdp_input_forces_identity_factor | -2.68192e+06 | -0.259197 | -2.87695 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q4 | 1.00162 | 1 | -0.00161756 | identity_gdp_input_forces_identity_factor | -1.76226e+06 | -0.161494 | -1.79251 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q1 | 1.00069 | 1 | -0.000687164 | identity_gdp_input_forces_identity_factor | -725949 | -0.0686692 | -0.762194 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q2 | 1.00019 | 1 | -0.000192813 | identity_gdp_input_forces_identity_factor | -198349 | -0.0192776 | -0.213972 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q3 | 1.00009 | 1 | -9.12137e-05 | identity_gdp_input_forces_identity_factor | -95018.7 | -0.00912054 | -0.101233 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q4 | 1.00005 | 1 | -5.41745e-05 | identity_gdp_input_forces_identity_factor | -59559.5 | -0.00541715 | -0.0601277 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q1 | 1.00002 | 1 | -2.22489e-05 | identity_gdp_input_forces_identity_factor | -23709.3 | -0.00222484 | -0.0246946 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q2 | 1.00001 | 1 | -6.76794e-06 | identity_gdp_input_forces_identity_factor | -7020.7 | -0.00067679 | -0.00751203 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q3 | 1 | 1 | -3.24058e-06 | identity_gdp_input_forces_identity_factor | -3403.31 | -0.000324057 | -0.00359687 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q4 | 1 | 1 | -1.87241e-06 | identity_gdp_input_forces_identity_factor | -2073.93 | -0.000187241 | -0.00207828 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q1 | 1 | 1 | -7.54795e-07 | identity_gdp_input_forces_identity_factor | -810.435 | -7.54794e-05 | -0.000837784 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q2 | 1 | 1 | -2.4089e-07 | identity_gdp_input_forces_identity_factor | -251.857 | -2.40889e-05 | -0.000267375 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q3 | 1 | 1 | -1.15655e-07 | identity_gdp_input_forces_identity_factor | -121.924 | -1.15655e-05 | -0.000128371 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q4 | 1 | 1 | -6.44945e-08 | identity_gdp_input_forces_identity_factor | -71.7444 | -6.44945e-06 | -7.15857e-05 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q1 | 1 | 1 | -2.57549e-08 | identity_gdp_input_forces_identity_factor | -27.7498 | -2.57549e-06 | -2.85867e-05 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q2 | 1 | 1 | -8.55656e-09 | identity_gdp_input_forces_identity_factor | -8.97007 | -8.55655e-07 | -9.49735e-06 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q3 | 1 | 1 | -4.11119e-09 | identity_gdp_input_forces_identity_factor | -4.36164 | -4.11119e-07 | -4.56322e-06 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q4 | 1 | 1 | -2.21801e-09 | identity_gdp_input_forces_identity_factor | -2.48235 | -2.21801e-07 | -2.46188e-06 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q1 | 1 | 1 | -8.80012e-10 | identity_gdp_input_forces_identity_factor | -0.954316 | -8.80012e-08 | -9.76769e-07 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q2 | 1 | 1 | -3.02855e-10 | identity_gdp_input_forces_identity_factor | -0.319563 | -3.02855e-08 | -3.36154e-07 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.45577e-10 | identity_gdp_input_forces_identity_factor | -0.155479 | -1.45577e-08 | -1.61583e-07 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q4 | 1 | 1 | -7.62648e-11 | identity_gdp_input_forces_identity_factor | -0.0858984 | -7.62649e-09 | -8.46502e-08 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q1 | 1 | 1 | -3.01599e-11 | identity_gdp_input_forces_identity_factor | -0.0329349 | -3.01598e-09 | -3.34759e-08 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q2 | 1 | 1 | -1.07048e-11 | identity_gdp_input_forces_identity_factor | -0.0113747 | -1.07048e-09 | -1.18818e-08 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q3 | 1 | 1 | -5.13944e-12 | identity_gdp_input_forces_identity_factor | -0.0055263 | -5.13939e-10 | -5.70447e-09 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q4 | 1 | 1 | -2.62035e-12 | identity_gdp_input_forces_identity_factor | -0.00297093 | -2.62032e-10 | -2.90843e-09 |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2035Q1 | 1 | 1 | -1.03473e-12 | identity_gdp_input_forces_identity_factor | -0.00113726 | -1.0348e-10 | -1.14857e-09 |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q1 | 1.00005 | 1 | -5.47486e-05 | positive_response_to_lower_gdp_capped_at_identity | -0.0844632 | -0.00547456 | -0.109367 |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q2 | 0.999543 | 1 | 0.000457243 | identity_gdp_input_forces_identity_factor | 0.702825 | 0.0457452 | 0.913864 |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q3 | 1.00013 | 1 | -0.000129983 | identity_gdp_input_forces_identity_factor | -0.200558 | -0.0129967 | -0.259638 |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q4 | 0.999928 | 1 | 7.20831e-05 | identity_gdp_input_forces_identity_factor | 0.112191 | 0.00720882 | 0.144013 |
| medium | middle_east_medium__12c_no_uplift | PED | 2029Q3 | 1.00134 | 1 | -0.00133752 | identity_gdp_input_forces_identity_factor | -2.05713 | -0.133573 | -2.66843 |
| medium | middle_east_medium__12c_no_uplift | PED | 2029Q4 | 1.00138 | 1 | -0.00138043 | identity_gdp_input_forces_identity_factor | -2.14059 | -0.137853 | -2.75392 |
| medium | middle_east_medium__12c_no_uplift | PED | 2030Q1 | 1.00134 | 1 | -0.00133881 | identity_gdp_input_forces_identity_factor | -2.05697 | -0.133702 | -2.671 |
| medium | middle_east_medium__12c_no_uplift | PED | 2030Q2 | 1.00134 | 1 | -0.00133951 | identity_gdp_input_forces_identity_factor | -2.04997 | -0.133772 | -2.6724 |
| medium | middle_east_medium__12c_no_uplift | PED | 2030Q3 | 1.00134 | 1 | -0.00133923 | identity_gdp_input_forces_identity_factor | -2.05697 | -0.133744 | -2.67184 |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q1 | 0.99981 | 1 | 0.000190132 | identity_gdp_input_forces_identity_factor | 0.292467 | 0.0190168 | 0.379903 |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q2 | 0.999759 | 1 | 0.000241398 | identity_gdp_input_forces_identity_factor | 0.369688 | 0.0241456 | 0.482364 |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q3 | 0.999759 | 1 | 0.000241451 | identity_gdp_input_forces_identity_factor | 0.368846 | 0.024151 | 0.48247 |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q4 | 0.999759 | 1 | 0.000241018 | identity_gdp_input_forces_identity_factor | 0.371187 | 0.0241076 | 0.481605 |
| medium | middle_east_medium__12c_no_uplift | PED | 2032Q1 | 0.999838 | 1 | 0.000161808 | identity_gdp_input_forces_identity_factor | 0.246792 | 0.0161834 | 0.3233 |

## The two guard types mean different things

**`identity_gdp_input_forces_identity_factor`** - Definitional, not a model pathology. The scenario requires that where a quarter's GDP input equals Base, the GDP factor is exactly 1. The fitted replay carries recursive lag persistence from earlier stressed quarters, so its ratio drifts off 1 after the conflict path has already converged back to Base. The guard restores the identity the scenario definition demands.

**`positive_response_to_lower_gdp_capped_at_identity`** - Model pathology correction. A lower GDP input produced a HIGHER fitted activity factor - a wrong-sign out-of-distribution response. The guard caps it at no-change rather than reversing it, so the overlay never lets a downside scenario mechanically raise activity.

The identity guard binding often is therefore expected behaviour once a
conflict path converges back to Base, and its frequency tracks how long
the fitted lag structure carries persistence. The wrong-sign guard is the
one that indicates the fitted model being used outside its estimation
range, and it is the count worth watching.

Revenue-equivalent figures use guard-induced percentage change in stream activity applied to governed FY2025 revenue for that stream; indicative materiality scale, not a revenue forecast.

