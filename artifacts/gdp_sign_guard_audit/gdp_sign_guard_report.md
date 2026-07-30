# GDP sign-guard binding register

Every quarter where the governed structural overlay clipped the fitted
GDP factor. The guards are a governance overlay on a fitted model, not a
re-estimation, so what matters is whether they are precautionary or
doing substantial work.

## Acceptance

| severity | guard_type | rule | n_bindings | max_abs_forecast_delta_pct | status | detail |
|---|---|---|---|---|---|---|
| base | any | no binding should be possible | 0 | 0 | passed | Base is the reference the overlay is built from; a binding there would mean the reference itself was clipped. |
| low | identity | explained or zero | 126 | 0.188009 | explained | Definitional, not a model pathology. The scenario requires that where a quarter's GDP input equals Base, the GDP factor is exactly 1. The fitted replay carries recursive lag persistence from earlier stressed quarters, so its ratio drifts off 1 after the conflict path has already converged back to Base. The guard restores the identity the scenario definition demands. |
| low | downside_sign | zero unexpected bindings; each explicitly disposed | 6 | 0.226663 | accepted_expected_guard | 6 wrong-sign bindings inside the Low stress window (2026Q4-2027Q1), maximum impact 0.2267%, cumulative revenue-equivalent -8.95 $m. 6/6 satisfy the economic monotonicity invariant after guarding. Model pathology correction. A lower GDP input produced a HIGHER fitted activity factor - a wrong-sign out-of-distribution response. The guard caps it at no-change rather than reversing it, so the overlay never lets a downside scenario mechanically raise activity. |
| medium | any | retained as governed protection; disclose and quantify | 132 | 0.463435 | disclosed | 132 bindings, of which 9 are wrong-sign; 0 move the forecast by at least 0.5%; maximum 0.4634%; cumulative revenue-equivalent -85.8 $m. |
| high | any | retained as governed protection; disclose and quantify | 108 | 0.478131 | disclosed | 108 bindings, of which 36 are wrong-sign; 0 move the forecast by at least 0.5%; maximum 0.4781%; cumulative revenue-equivalent -73.6 $m. |

## Summary by severity, stream and reason

| severity | stream | guard_reason | n_bindings | first_quarter | last_quarter | max_abs_clip_amount | max_abs_forecast_delta_pct | cumulative_revenue_equivalent_nzd_m |
|---|---|---|---|---|---|---|---|---|
| high | HEAVY_RUC | identity_gdp_input_forces_identity_factor | 72 | 2031Q1 | 2036Q4 | 0.00222024 | 0.222518 | 15.3509 |
| high | HEAVY_RUC | positive_response_to_lower_gdp_capped_at_identity | 30 | 2028Q2 | 2030Q4 | 0.00480429 | 0.478131 | -74.9395 |
| high | PED | positive_response_to_lower_gdp_capped_at_identity | 6 | 2029Q2 | 2029Q3 | 0.0013363 | 0.133452 | -13.9914 |
| low | HEAVY_RUC | identity_gdp_input_forces_identity_factor | 81 | 2027Q2 | 2033Q4 | 0.00188363 | 0.188009 | -13.3108 |
| low | HEAVY_RUC | positive_response_to_lower_gdp_capped_at_identity | 6 | 2026Q4 | 2027Q1 | 0.00227178 | 0.226663 | -8.94689 |
| low | PED | identity_gdp_input_forces_identity_factor | 45 | 2027Q2 | 2032Q1 | 0.00137853 | 0.138043 | 39.6046 |
| medium | HEAVY_RUC | identity_gdp_input_forces_identity_factor | 84 | 2028Q2 | 2035Q1 | 0.00465593 | 0.463435 | -32.9144 |
| medium | HEAVY_RUC | positive_response_to_lower_gdp_capped_at_identity | 6 | 2027Q4 | 2028Q1 | 0.00455262 | 0.453198 | -21.1143 |
| medium | PED | identity_gdp_input_forces_identity_factor | 39 | 2028Q2 | 2032Q1 | 0.00138043 | 0.137853 | -31.4691 |
| medium | PED | positive_response_to_lower_gdp_capped_at_identity | 3 | 2028Q1 | 2028Q1 | 5.47486e-05 | 0.00547456 | -0.3281 |

Total bindings: 372.

## Low wrong-sign bindings, individually disposed

These are the bindings that indicate the fitted model responding with the
wrong sign, as distinct from the definitional identity restorations. Each
is listed in full with its disposition.

| scenario_name | stream | quarter | responding_model | input_gdp_level_factor | price_response_factor | raw_gdp_model_factor | guarded_gdp_model_factor | clip_amount | base_at_same_price_forecast | guarded_forecast | base_vs_scenario_direction | monotonicity_holds | forecast_delta_pct | revenue_equivalent_delta_nzd_m | disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| middle_east_low | HEAVY_RUC | 2026Q4 | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | 0.997925 | 0.996234 | 1.00227 | 1 | -0.00227178 | 1.06333e+09 | 1.06333e+09 | scenario_equals_base_at_identity | True | -0.226663 | -2.51585 | accepted_expected_guard |
| middle_east_low | HEAVY_RUC | 2027Q1 | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | 0.999429 | 1 | 1.00042 | 1 | -0.000420419 | 1.0384e+09 | 1.0384e+09 | scenario_equals_base_at_identity | True | -0.0420242 | -0.466448 | accepted_expected_guard |
| middle_east_low__12c_delay_6m | HEAVY_RUC | 2026Q4 | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | 0.997925 | 0.996234 | 1.00227 | 1 | -0.00227178 | 1.06333e+09 | 1.06333e+09 | scenario_equals_base_at_identity | True | -0.226663 | -2.51585 | accepted_expected_guard |
| middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q1 | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | 0.999429 | 1.00352 | 1.00042 | 1 | -0.000420419 | 1.04206e+09 | 1.04206e+09 | scenario_equals_base_at_identity | True | -0.0420242 | -0.466448 | accepted_expected_guard |
| middle_east_low__12c_no_uplift | HEAVY_RUC | 2026Q4 | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | 0.997925 | 0.996234 | 1.00227 | 1 | -0.00227178 | 1.06333e+09 | 1.06333e+09 | scenario_equals_base_at_identity | True | -0.226663 | -2.51585 | accepted_expected_guard |
| middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q1 | HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4 | 0.999429 | 1.00352 | 1.00042 | 1 | -0.000420419 | 1.04206e+09 | 1.04206e+09 | scenario_equals_base_at_identity | True | -0.0420242 | -0.466448 | accepted_expected_guard |

## Every binding

| severity | scenario_name | stream | quarter | raw_gdp_model_factor | guarded_gdp_model_factor | clip_amount | guard_reason | forecast_delta | forecast_delta_pct | revenue_equivalent_delta_nzd_m | disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|
| high | middle_east_high | HEAVY_RUC | 2028Q2 | 1.0048 | 1 | -0.00480429 | positive_response_to_lower_gdp_capped_at_identity | -4.77413e+06 | -0.478131 | -5.30702 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2028Q3 | 1.00443 | 1 | -0.00443228 | positive_response_to_lower_gdp_capped_at_identity | -4.48246e+06 | -0.441272 | -4.8979 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2028Q4 | 1.00402 | 1 | -0.00402462 | positive_response_to_lower_gdp_capped_at_identity | -4.31493e+06 | -0.400849 | -4.44922 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2029Q1 | 1.00121 | 1 | -0.00121196 | positive_response_to_lower_gdp_capped_at_identity | -1.2646e+06 | -0.121049 | -1.34358 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2029Q2 | 1.00264 | 1 | -0.00263597 | positive_response_to_lower_gdp_capped_at_identity | -2.68544e+06 | -0.262904 | -2.9181 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2029Q3 | 1.00215 | 1 | -0.00214691 | positive_response_to_lower_gdp_capped_at_identity | -2.21887e+06 | -0.214231 | -2.37786 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2029Q4 | 1.00153 | 1 | -0.00153295 | positive_response_to_lower_gdp_capped_at_identity | -1.67435e+06 | -0.15306 | -1.69889 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2030Q2 | 1.00061 | 1 | -0.000605673 | positive_response_to_lower_gdp_capped_at_identity | -625716 | -0.0605307 | -0.67186 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2030Q3 | 1.00069 | 1 | -0.000689525 | positive_response_to_lower_gdp_capped_at_identity | -721503 | -0.068905 | -0.764812 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2030Q4 | 1.0005 | 1 | -0.000496296 | positive_response_to_lower_gdp_capped_at_identity | -547944 | -0.049605 | -0.550591 | accepted_expected_guard |
| high | middle_east_high | HEAVY_RUC | 2031Q1 | 0.998102 | 1 | 0.0018976 | identity_gdp_input_forces_identity_factor | 2.03121e+06 | 0.190121 | 2.11025 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2031Q2 | 0.999891 | 1 | 0.000108655 | identity_gdp_input_forces_identity_factor | 113251 | 0.0108666 | 0.120614 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2031Q3 | 1.00015 | 1 | -0.000151941 | identity_gdp_input_forces_identity_factor | -160177 | -0.0151918 | -0.168621 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2031Q4 | 1.00004 | 1 | -4.22364e-05 | identity_gdp_input_forces_identity_factor | -46984.3 | -0.00422346 | -0.0468783 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2032Q1 | 0.99778 | 1 | 0.00222024 | identity_gdp_input_forces_identity_factor | 2.39221e+06 | 0.222518 | 2.46984 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2032Q2 | 1.00001 | 1 | -1.22579e-05 | identity_gdp_input_forces_identity_factor | -12850.3 | -0.00122578 | -0.0136055 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2032Q3 | 1 | 1 | -3.23259e-06 | identity_gdp_input_forces_identity_factor | -3429.51 | -0.000323258 | -0.003588 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2032Q4 | 1 | 1 | -1.39441e-06 | identity_gdp_input_forces_identity_factor | -1560.59 | -0.000139441 | -0.00154772 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2033Q1 | 0.999414 | 1 | 0.000586143 | identity_gdp_input_forces_identity_factor | 635634 | 0.0586486 | 0.650971 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2033Q2 | 1 | 1 | -2.17391e-07 | identity_gdp_input_forces_identity_factor | -229.384 | -2.17391e-05 | -0.000241293 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.12264e-07 | identity_gdp_input_forces_identity_factor | -119.901 | -1.12264e-05 | -0.000124608 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2033Q4 | 1 | 1 | -4.77401e-08 | identity_gdp_input_forces_identity_factor | -53.7705 | -4.77401e-06 | -5.29892e-05 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2034Q1 | 1 | 1 | -1.72351e-08 | identity_gdp_input_forces_identity_factor | -18.8209 | -1.72351e-06 | -1.91301e-05 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2034Q2 | 1 | 1 | -7.6724e-09 | identity_gdp_input_forces_identity_factor | -8.15257 | -7.6724e-07 | -8.51598e-06 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2034Q3 | 1 | 1 | -3.884e-09 | identity_gdp_input_forces_identity_factor | -4.1764 | -3.884e-07 | -4.31105e-06 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2034Q4 | 1 | 1 | -1.63647e-09 | identity_gdp_input_forces_identity_factor | -1.85544 | -1.63647e-07 | -1.8164e-06 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2035Q1 | 1 | 1 | -6.04489e-10 | identity_gdp_input_forces_identity_factor | -0.664342 | -6.04489e-08 | -6.70952e-07 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2035Q2 | 1 | 1 | -2.70348e-10 | identity_gdp_input_forces_identity_factor | -0.289005 | -2.70348e-08 | -3.00073e-07 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2035Q3 | 1 | 1 | -1.34244e-10 | identity_gdp_input_forces_identity_factor | -0.145207 | -1.34244e-08 | -1.49004e-07 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2035Q4 | 1 | 1 | -5.62317e-11 | identity_gdp_input_forces_identity_factor | -0.0641317 | -5.62317e-09 | -6.24144e-08 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2036Q1 | 1 | 1 | -2.11859e-11 | identity_gdp_input_forces_identity_factor | -0.0234156 | -2.11859e-09 | -2.35153e-08 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2036Q2 | 1 | 1 | -9.50817e-12 | identity_gdp_input_forces_identity_factor | -0.0102203 | -9.5082e-10 | -1.05536e-08 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2036Q3 | 1 | 1 | -4.63851e-12 | identity_gdp_input_forces_identity_factor | -0.00504446 | -4.6386e-10 | -5.14861e-09 | accepted_definitional_restoration |
| high | middle_east_high | HEAVY_RUC | 2036Q4 | 1 | 1 | -1.93578e-12 | identity_gdp_input_forces_identity_factor | -0.00221944 | -1.93577e-10 | -2.14861e-09 | accepted_definitional_restoration |
| high | middle_east_high | PED | 2029Q2 | 1.00134 | 1 | -0.0013363 | positive_response_to_lower_gdp_capped_at_identity | -2.02354 | -0.133452 | -2.666 | accepted_expected_guard |
| high | middle_east_high | PED | 2029Q3 | 1.001 | 1 | -0.00100104 | positive_response_to_lower_gdp_capped_at_identity | -1.52411 | -0.100004 | -1.99781 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q2 | 1.0048 | 1 | -0.00480429 | positive_response_to_lower_gdp_capped_at_identity | -4.77413e+06 | -0.478131 | -5.30702 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q3 | 1.00443 | 1 | -0.00443228 | positive_response_to_lower_gdp_capped_at_identity | -4.48246e+06 | -0.441272 | -4.8979 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2028Q4 | 1.00402 | 1 | -0.00402462 | positive_response_to_lower_gdp_capped_at_identity | -4.31493e+06 | -0.400849 | -4.44922 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q1 | 1.00121 | 1 | -0.00121196 | positive_response_to_lower_gdp_capped_at_identity | -1.2646e+06 | -0.121049 | -1.34358 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q2 | 1.00264 | 1 | -0.00263597 | positive_response_to_lower_gdp_capped_at_identity | -2.68544e+06 | -0.262904 | -2.9181 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q3 | 1.00215 | 1 | -0.00214691 | positive_response_to_lower_gdp_capped_at_identity | -2.21887e+06 | -0.214231 | -2.37786 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2029Q4 | 1.00153 | 1 | -0.00153295 | positive_response_to_lower_gdp_capped_at_identity | -1.67435e+06 | -0.15306 | -1.69889 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q2 | 1.00061 | 1 | -0.000605673 | positive_response_to_lower_gdp_capped_at_identity | -625716 | -0.0605307 | -0.67186 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q3 | 1.00069 | 1 | -0.000689525 | positive_response_to_lower_gdp_capped_at_identity | -721503 | -0.068905 | -0.764812 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2030Q4 | 1.0005 | 1 | -0.000496296 | positive_response_to_lower_gdp_capped_at_identity | -547944 | -0.049605 | -0.550591 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q1 | 0.998102 | 1 | 0.0018976 | identity_gdp_input_forces_identity_factor | 2.03121e+06 | 0.190121 | 2.11025 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q2 | 0.999891 | 1 | 0.000108655 | identity_gdp_input_forces_identity_factor | 113251 | 0.0108666 | 0.120614 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q3 | 1.00015 | 1 | -0.000151941 | identity_gdp_input_forces_identity_factor | -160177 | -0.0151918 | -0.168621 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2031Q4 | 1.00004 | 1 | -4.22364e-05 | identity_gdp_input_forces_identity_factor | -46984.3 | -0.00422346 | -0.0468783 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q1 | 0.99778 | 1 | 0.00222024 | identity_gdp_input_forces_identity_factor | 2.39221e+06 | 0.222518 | 2.46984 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q2 | 1.00001 | 1 | -1.22579e-05 | identity_gdp_input_forces_identity_factor | -12850.3 | -0.00122578 | -0.0136055 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q3 | 1 | 1 | -3.23259e-06 | identity_gdp_input_forces_identity_factor | -3429.51 | -0.000323258 | -0.003588 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2032Q4 | 1 | 1 | -1.39441e-06 | identity_gdp_input_forces_identity_factor | -1560.59 | -0.000139441 | -0.00154772 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q1 | 0.999414 | 1 | 0.000586143 | identity_gdp_input_forces_identity_factor | 635634 | 0.0586486 | 0.650971 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q2 | 1 | 1 | -2.17391e-07 | identity_gdp_input_forces_identity_factor | -229.384 | -2.17391e-05 | -0.000241293 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.12264e-07 | identity_gdp_input_forces_identity_factor | -119.901 | -1.12264e-05 | -0.000124608 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2033Q4 | 1 | 1 | -4.77401e-08 | identity_gdp_input_forces_identity_factor | -53.7705 | -4.77401e-06 | -5.29892e-05 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q1 | 1 | 1 | -1.72351e-08 | identity_gdp_input_forces_identity_factor | -18.8209 | -1.72351e-06 | -1.91301e-05 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q2 | 1 | 1 | -7.6724e-09 | identity_gdp_input_forces_identity_factor | -8.15257 | -7.6724e-07 | -8.51598e-06 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q3 | 1 | 1 | -3.884e-09 | identity_gdp_input_forces_identity_factor | -4.1764 | -3.884e-07 | -4.31105e-06 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2034Q4 | 1 | 1 | -1.63647e-09 | identity_gdp_input_forces_identity_factor | -1.85544 | -1.63647e-07 | -1.8164e-06 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q1 | 1 | 1 | -6.04489e-10 | identity_gdp_input_forces_identity_factor | -0.664342 | -6.04489e-08 | -6.70952e-07 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q2 | 1 | 1 | -2.70348e-10 | identity_gdp_input_forces_identity_factor | -0.289005 | -2.70348e-08 | -3.00073e-07 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q3 | 1 | 1 | -1.34244e-10 | identity_gdp_input_forces_identity_factor | -0.145207 | -1.34244e-08 | -1.49004e-07 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2035Q4 | 1 | 1 | -5.62317e-11 | identity_gdp_input_forces_identity_factor | -0.0641317 | -5.62317e-09 | -6.24144e-08 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q1 | 1 | 1 | -2.11859e-11 | identity_gdp_input_forces_identity_factor | -0.0234156 | -2.11859e-09 | -2.35153e-08 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q2 | 1 | 1 | -9.50817e-12 | identity_gdp_input_forces_identity_factor | -0.0102203 | -9.5082e-10 | -1.05536e-08 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q3 | 1 | 1 | -4.63851e-12 | identity_gdp_input_forces_identity_factor | -0.00504446 | -4.6386e-10 | -5.14861e-09 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | HEAVY_RUC | 2036Q4 | 1 | 1 | -1.93578e-12 | identity_gdp_input_forces_identity_factor | -0.00221944 | -1.93577e-10 | -2.14861e-09 | accepted_definitional_restoration |
| high | middle_east_high__12c_delay_6m | PED | 2029Q2 | 1.00134 | 1 | -0.0013363 | positive_response_to_lower_gdp_capped_at_identity | -2.02354 | -0.133452 | -2.666 | accepted_expected_guard |
| high | middle_east_high__12c_delay_6m | PED | 2029Q3 | 1.001 | 1 | -0.00100104 | positive_response_to_lower_gdp_capped_at_identity | -1.52411 | -0.100004 | -1.99781 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q2 | 1.0048 | 1 | -0.00480429 | positive_response_to_lower_gdp_capped_at_identity | -4.78695e+06 | -0.478131 | -5.30702 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q3 | 1.00443 | 1 | -0.00443228 | positive_response_to_lower_gdp_capped_at_identity | -4.49517e+06 | -0.441272 | -4.8979 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2028Q4 | 1.00402 | 1 | -0.00402462 | positive_response_to_lower_gdp_capped_at_identity | -4.32777e+06 | -0.400849 | -4.44922 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q1 | 1.00121 | 1 | -0.00121196 | positive_response_to_lower_gdp_capped_at_identity | -1.26834e+06 | -0.121049 | -1.34358 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q2 | 1.00264 | 1 | -0.00263597 | positive_response_to_lower_gdp_capped_at_identity | -2.69366e+06 | -0.262904 | -2.9181 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q3 | 1.00215 | 1 | -0.00214691 | positive_response_to_lower_gdp_capped_at_identity | -2.22582e+06 | -0.214231 | -2.37786 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2029Q4 | 1.00153 | 1 | -0.00153295 | positive_response_to_lower_gdp_capped_at_identity | -1.67969e+06 | -0.15306 | -1.69889 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q2 | 1.00061 | 1 | -0.000605673 | positive_response_to_lower_gdp_capped_at_identity | -627693 | -0.0605307 | -0.67186 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q3 | 1.00069 | 1 | -0.000689525 | positive_response_to_lower_gdp_capped_at_identity | -723805 | -0.068905 | -0.764812 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2030Q4 | 1.0005 | 1 | -0.000496296 | positive_response_to_lower_gdp_capped_at_identity | -549709 | -0.049605 | -0.550591 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q1 | 0.998102 | 1 | 0.0018976 | identity_gdp_input_forces_identity_factor | 2.03748e+06 | 0.190121 | 2.11025 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q2 | 0.999891 | 1 | 0.000108655 | identity_gdp_input_forces_identity_factor | 113601 | 0.0108666 | 0.120614 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q3 | 1.00015 | 1 | -0.000151941 | identity_gdp_input_forces_identity_factor | -160177 | -0.0151918 | -0.168621 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2031Q4 | 1.00004 | 1 | -4.22364e-05 | identity_gdp_input_forces_identity_factor | -46984.3 | -0.00422346 | -0.0468783 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q1 | 0.99778 | 1 | 0.00222024 | identity_gdp_input_forces_identity_factor | 2.39221e+06 | 0.222518 | 2.46984 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q2 | 1.00001 | 1 | -1.22579e-05 | identity_gdp_input_forces_identity_factor | -12850.3 | -0.00122578 | -0.0136055 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q3 | 1 | 1 | -3.23259e-06 | identity_gdp_input_forces_identity_factor | -3429.51 | -0.000323258 | -0.003588 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2032Q4 | 1 | 1 | -1.39441e-06 | identity_gdp_input_forces_identity_factor | -1560.59 | -0.000139441 | -0.00154772 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q1 | 0.999414 | 1 | 0.000586143 | identity_gdp_input_forces_identity_factor | 635634 | 0.0586486 | 0.650971 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q2 | 1 | 1 | -2.17391e-07 | identity_gdp_input_forces_identity_factor | -229.384 | -2.17391e-05 | -0.000241293 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.12264e-07 | identity_gdp_input_forces_identity_factor | -119.901 | -1.12264e-05 | -0.000124608 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2033Q4 | 1 | 1 | -4.77401e-08 | identity_gdp_input_forces_identity_factor | -53.7705 | -4.77401e-06 | -5.29892e-05 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q1 | 1 | 1 | -1.72351e-08 | identity_gdp_input_forces_identity_factor | -18.8209 | -1.72351e-06 | -1.91301e-05 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q2 | 1 | 1 | -7.6724e-09 | identity_gdp_input_forces_identity_factor | -8.15257 | -7.6724e-07 | -8.51598e-06 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q3 | 1 | 1 | -3.884e-09 | identity_gdp_input_forces_identity_factor | -4.1764 | -3.884e-07 | -4.31105e-06 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2034Q4 | 1 | 1 | -1.63647e-09 | identity_gdp_input_forces_identity_factor | -1.85544 | -1.63647e-07 | -1.8164e-06 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q1 | 1 | 1 | -6.04489e-10 | identity_gdp_input_forces_identity_factor | -0.664342 | -6.04489e-08 | -6.70952e-07 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q2 | 1 | 1 | -2.70348e-10 | identity_gdp_input_forces_identity_factor | -0.289005 | -2.70348e-08 | -3.00073e-07 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q3 | 1 | 1 | -1.34244e-10 | identity_gdp_input_forces_identity_factor | -0.145207 | -1.34244e-08 | -1.49004e-07 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2035Q4 | 1 | 1 | -5.62317e-11 | identity_gdp_input_forces_identity_factor | -0.0641317 | -5.62317e-09 | -6.24144e-08 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q1 | 1 | 1 | -2.11859e-11 | identity_gdp_input_forces_identity_factor | -0.0234156 | -2.11859e-09 | -2.35153e-08 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q2 | 1 | 1 | -9.50817e-12 | identity_gdp_input_forces_identity_factor | -0.0102203 | -9.5082e-10 | -1.05536e-08 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q3 | 1 | 1 | -4.63851e-12 | identity_gdp_input_forces_identity_factor | -0.00504446 | -4.6386e-10 | -5.14861e-09 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | HEAVY_RUC | 2036Q4 | 1 | 1 | -1.93578e-12 | identity_gdp_input_forces_identity_factor | -0.00221944 | -1.93577e-10 | -2.14861e-09 | accepted_definitional_restoration |
| high | middle_east_high__12c_no_uplift | PED | 2029Q2 | 1.00134 | 1 | -0.0013363 | positive_response_to_lower_gdp_capped_at_identity | -2.03496 | -0.133452 | -2.666 | accepted_expected_guard |
| high | middle_east_high__12c_no_uplift | PED | 2029Q3 | 1.001 | 1 | -0.00100104 | positive_response_to_lower_gdp_capped_at_identity | -1.53278 | -0.100004 | -1.99781 | accepted_expected_guard |
| low | middle_east_low | HEAVY_RUC | 2026Q4 | 1.00227 | 1 | -0.00227178 | positive_response_to_lower_gdp_capped_at_identity | -2.41564e+06 | -0.226663 | -2.51585 | accepted_expected_guard |
| low | middle_east_low | HEAVY_RUC | 2027Q1 | 1.00042 | 1 | -0.000420419 | positive_response_to_lower_gdp_capped_at_identity | -436564 | -0.0420242 | -0.466448 | accepted_expected_guard |
| low | middle_east_low | HEAVY_RUC | 2027Q2 | 1.00106 | 1 | -0.00106283 | identity_gdp_input_forces_identity_factor | -1.06842e+06 | -0.10617 | -1.17843 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2027Q3 | 1.00188 | 1 | -0.00188363 | identity_gdp_input_forces_identity_factor | -1.91863e+06 | -0.188009 | -2.0868 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2027Q4 | 1.00077 | 1 | -0.000766776 | identity_gdp_input_forces_identity_factor | -824727 | -0.0766189 | -0.850432 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2028Q1 | 1.00023 | 1 | -0.000229061 | identity_gdp_input_forces_identity_factor | -239023 | -0.0229009 | -0.254188 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2028Q2 | 0.99996 | 1 | 3.95595e-05 | identity_gdp_input_forces_identity_factor | 40177.8 | 0.0039561 | 0.0439108 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2028Q3 | 1.00006 | 1 | -6.09073e-05 | identity_gdp_input_forces_identity_factor | -62646.6 | -0.00609036 | -0.0676 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2028Q4 | 1.00002 | 1 | -2.48246e-05 | identity_gdp_input_forces_identity_factor | -26954.1 | -0.0024824 | -0.0275534 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2029Q1 | 1.00001 | 1 | -7.52059e-06 | identity_gdp_input_forces_identity_factor | -7919.32 | -0.000752053 | -0.00834741 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2029Q2 | 1 | 1 | -3.32747e-06 | identity_gdp_input_forces_identity_factor | -3411.86 | -0.000332746 | -0.00369331 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2029Q3 | 1 | 1 | -2.0736e-06 | identity_gdp_input_forces_identity_factor | -2153.03 | -0.000207359 | -0.00230159 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2029Q4 | 1 | 1 | -8.50645e-07 | identity_gdp_input_forces_identity_factor | -932.125 | -8.50644e-05 | -0.000944173 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2030Q1 | 1 | 1 | -2.64428e-07 | identity_gdp_input_forces_identity_factor | -280.894 | -2.64428e-05 | -0.000293502 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2030Q2 | 1 | 1 | -1.20833e-07 | identity_gdp_input_forces_identity_factor | -124.947 | -1.20833e-05 | -0.000134118 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2030Q3 | 1 | 1 | -7.09904e-08 | identity_gdp_input_forces_identity_factor | -74.3169 | -7.09904e-06 | -7.87958e-05 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2030Q4 | 1 | 1 | -2.89638e-08 | identity_gdp_input_forces_identity_factor | -31.978 | -2.89638e-06 | -3.21484e-05 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2031Q1 | 1 | 1 | -9.31028e-09 | identity_gdp_input_forces_identity_factor | -9.96578 | -9.31028e-07 | -1.03339e-05 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2031Q2 | 1 | 1 | -4.33016e-09 | identity_gdp_input_forces_identity_factor | -4.51335 | -4.33016e-07 | -4.80626e-06 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2031Q3 | 1 | 1 | -2.44078e-09 | identity_gdp_input_forces_identity_factor | -2.57309 | -2.44078e-07 | -2.70914e-06 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2031Q4 | 1 | 1 | -9.89366e-10 | identity_gdp_input_forces_identity_factor | -1.10058 | -9.89366e-08 | -1.09815e-06 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2032Q1 | 1 | 1 | -3.29416e-10 | identity_gdp_input_forces_identity_factor | -0.354931 | -3.29416e-08 | -3.65635e-07 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2032Q2 | 1 | 1 | -1.54599e-10 | identity_gdp_input_forces_identity_factor | -0.16207 | -1.54599e-08 | -1.71597e-07 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2032Q3 | 1 | 1 | -8.3938e-11 | identity_gdp_input_forces_identity_factor | -0.0890514 | -8.3938e-09 | -9.3167e-08 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2032Q4 | 1 | 1 | -3.3836e-11 | identity_gdp_input_forces_identity_factor | -0.0378685 | -3.3836e-09 | -3.75563e-08 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2033Q1 | 1 | 1 | -1.16329e-11 | identity_gdp_input_forces_identity_factor | -0.0126152 | -1.1633e-09 | -1.2912e-08 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2033Q2 | 1 | 1 | -5.48628e-12 | identity_gdp_input_forces_identity_factor | -0.00578892 | -5.48626e-10 | -6.08947e-09 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2033Q3 | 1 | 1 | -2.8868e-12 | identity_gdp_input_forces_identity_factor | -0.00308323 | -2.88685e-10 | -3.20426e-09 | accepted_definitional_restoration |
| low | middle_east_low | HEAVY_RUC | 2033Q4 | 1 | 1 | -1.16018e-12 | identity_gdp_input_forces_identity_factor | -0.00130677 | -1.16022e-10 | -1.28778e-09 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2027Q2 | 0.9988 | 1 | 0.00119997 | identity_gdp_input_forces_identity_factor | 1.82923 | 0.120141 | 2.4001 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2027Q3 | 0.999946 | 1 | 5.42344e-05 | identity_gdp_input_forces_identity_factor | 0.0830638 | 0.00542373 | 0.108351 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2027Q4 | 1.00009 | 1 | -9.24272e-05 | identity_gdp_input_forces_identity_factor | -0.142972 | -0.00924186 | -0.184627 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2028Q1 | 1.00007 | 1 | -7.10911e-05 | identity_gdp_input_forces_identity_factor | -0.109023 | -0.00710861 | -0.142011 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2028Q2 | 1.00014 | 1 | -0.000143594 | identity_gdp_input_forces_identity_factor | -0.21941 | -0.0143574 | -0.286821 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2029Q3 | 0.998664 | 1 | 0.00133573 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133752 | 2.672 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2029Q4 | 0.998621 | 1 | 0.00137853 | identity_gdp_input_forces_identity_factor | 2.12522 | 0.138043 | 2.75772 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2030Q1 | 0.998663 | 1 | 0.00133702 | identity_gdp_input_forces_identity_factor | 2.04234 | 0.133881 | 2.67457 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2030Q2 | 0.998662 | 1 | 0.00133772 | identity_gdp_input_forces_identity_factor | 2.03542 | 0.133951 | 2.67598 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2030Q3 | 0.998663 | 1 | 0.00133744 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133923 | 2.67542 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2031Q1 | 1.00019 | 1 | -0.000190168 | identity_gdp_input_forces_identity_factor | -0.290852 | -0.0190132 | -0.379831 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2031Q2 | 1.00024 | 1 | -0.000241456 | identity_gdp_input_forces_identity_factor | -0.367672 | -0.0241398 | -0.482247 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2031Q3 | 1.00024 | 1 | -0.00024151 | identity_gdp_input_forces_identity_factor | -0.368935 | -0.0241451 | -0.482354 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2031Q4 | 1.00024 | 1 | -0.000241076 | identity_gdp_input_forces_identity_factor | -0.371277 | -0.0241018 | -0.481489 | accepted_definitional_restoration |
| low | middle_east_low | PED | 2032Q1 | 1.00016 | 1 | -0.000161834 | identity_gdp_input_forces_identity_factor | -0.246832 | -0.0161808 | -0.323248 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2026Q4 | 1.00227 | 1 | -0.00227178 | positive_response_to_lower_gdp_capped_at_identity | -2.41564e+06 | -0.226663 | -2.51585 | accepted_expected_guard |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q1 | 1.00042 | 1 | -0.000420419 | positive_response_to_lower_gdp_capped_at_identity | -438100 | -0.0420242 | -0.466448 | accepted_expected_guard |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q2 | 1.00106 | 1 | -0.00106283 | identity_gdp_input_forces_identity_factor | -1.07219e+06 | -0.10617 | -1.17843 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q3 | 1.00188 | 1 | -0.00188363 | identity_gdp_input_forces_identity_factor | -1.91863e+06 | -0.188009 | -2.0868 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2027Q4 | 1.00077 | 1 | -0.000766776 | identity_gdp_input_forces_identity_factor | -824727 | -0.0766189 | -0.850432 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q1 | 1.00023 | 1 | -0.000229061 | identity_gdp_input_forces_identity_factor | -239023 | -0.0229009 | -0.254188 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q2 | 0.99996 | 1 | 3.95595e-05 | identity_gdp_input_forces_identity_factor | 40177.8 | 0.0039561 | 0.0439108 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q3 | 1.00006 | 1 | -6.09073e-05 | identity_gdp_input_forces_identity_factor | -62646.6 | -0.00609036 | -0.0676 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2028Q4 | 1.00002 | 1 | -2.48246e-05 | identity_gdp_input_forces_identity_factor | -26954.1 | -0.0024824 | -0.0275534 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q1 | 1.00001 | 1 | -7.52059e-06 | identity_gdp_input_forces_identity_factor | -7919.32 | -0.000752053 | -0.00834741 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q2 | 1 | 1 | -3.32747e-06 | identity_gdp_input_forces_identity_factor | -3411.86 | -0.000332746 | -0.00369331 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q3 | 1 | 1 | -2.0736e-06 | identity_gdp_input_forces_identity_factor | -2153.03 | -0.000207359 | -0.00230159 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2029Q4 | 1 | 1 | -8.50645e-07 | identity_gdp_input_forces_identity_factor | -932.125 | -8.50644e-05 | -0.000944173 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q1 | 1 | 1 | -2.64428e-07 | identity_gdp_input_forces_identity_factor | -280.894 | -2.64428e-05 | -0.000293502 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q2 | 1 | 1 | -1.20833e-07 | identity_gdp_input_forces_identity_factor | -124.947 | -1.20833e-05 | -0.000134118 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q3 | 1 | 1 | -7.09904e-08 | identity_gdp_input_forces_identity_factor | -74.3169 | -7.09904e-06 | -7.87958e-05 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2030Q4 | 1 | 1 | -2.89638e-08 | identity_gdp_input_forces_identity_factor | -31.978 | -2.89638e-06 | -3.21484e-05 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q1 | 1 | 1 | -9.31028e-09 | identity_gdp_input_forces_identity_factor | -9.96578 | -9.31028e-07 | -1.03339e-05 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q2 | 1 | 1 | -4.33016e-09 | identity_gdp_input_forces_identity_factor | -4.51335 | -4.33016e-07 | -4.80626e-06 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q3 | 1 | 1 | -2.44078e-09 | identity_gdp_input_forces_identity_factor | -2.57309 | -2.44078e-07 | -2.70914e-06 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2031Q4 | 1 | 1 | -9.89366e-10 | identity_gdp_input_forces_identity_factor | -1.10058 | -9.89366e-08 | -1.09815e-06 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q1 | 1 | 1 | -3.29416e-10 | identity_gdp_input_forces_identity_factor | -0.354931 | -3.29416e-08 | -3.65635e-07 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q2 | 1 | 1 | -1.54599e-10 | identity_gdp_input_forces_identity_factor | -0.16207 | -1.54599e-08 | -1.71597e-07 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q3 | 1 | 1 | -8.3938e-11 | identity_gdp_input_forces_identity_factor | -0.0890514 | -8.3938e-09 | -9.3167e-08 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2032Q4 | 1 | 1 | -3.3836e-11 | identity_gdp_input_forces_identity_factor | -0.0378685 | -3.3836e-09 | -3.75563e-08 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q1 | 1 | 1 | -1.16329e-11 | identity_gdp_input_forces_identity_factor | -0.0126152 | -1.1633e-09 | -1.2912e-08 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q2 | 1 | 1 | -5.48628e-12 | identity_gdp_input_forces_identity_factor | -0.00578892 | -5.48626e-10 | -6.08947e-09 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q3 | 1 | 1 | -2.8868e-12 | identity_gdp_input_forces_identity_factor | -0.00308323 | -2.88685e-10 | -3.20426e-09 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | HEAVY_RUC | 2033Q4 | 1 | 1 | -1.16018e-12 | identity_gdp_input_forces_identity_factor | -0.00130677 | -1.16022e-10 | -1.28778e-09 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2027Q2 | 0.9988 | 1 | 0.00119997 | identity_gdp_input_forces_identity_factor | 1.84029 | 0.120141 | 2.4001 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2027Q3 | 0.999946 | 1 | 5.42344e-05 | identity_gdp_input_forces_identity_factor | 0.0830638 | 0.00542373 | 0.108351 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2027Q4 | 1.00009 | 1 | -9.24272e-05 | identity_gdp_input_forces_identity_factor | -0.142972 | -0.00924186 | -0.184627 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2028Q1 | 1.00007 | 1 | -7.10911e-05 | identity_gdp_input_forces_identity_factor | -0.109023 | -0.00710861 | -0.142011 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2028Q2 | 1.00014 | 1 | -0.000143594 | identity_gdp_input_forces_identity_factor | -0.21941 | -0.0143574 | -0.286821 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2029Q3 | 0.998664 | 1 | 0.00133573 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133752 | 2.672 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2029Q4 | 0.998621 | 1 | 0.00137853 | identity_gdp_input_forces_identity_factor | 2.12522 | 0.138043 | 2.75772 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2030Q1 | 0.998663 | 1 | 0.00133702 | identity_gdp_input_forces_identity_factor | 2.04234 | 0.133881 | 2.67457 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2030Q2 | 0.998662 | 1 | 0.00133772 | identity_gdp_input_forces_identity_factor | 2.03542 | 0.133951 | 2.67598 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2030Q3 | 0.998663 | 1 | 0.00133744 | identity_gdp_input_forces_identity_factor | 2.04241 | 0.133923 | 2.67542 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2031Q1 | 1.00019 | 1 | -0.000190168 | identity_gdp_input_forces_identity_factor | -0.290852 | -0.0190132 | -0.379831 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2031Q2 | 1.00024 | 1 | -0.000241456 | identity_gdp_input_forces_identity_factor | -0.367672 | -0.0241398 | -0.482247 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2031Q3 | 1.00024 | 1 | -0.00024151 | identity_gdp_input_forces_identity_factor | -0.368935 | -0.0241451 | -0.482354 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2031Q4 | 1.00024 | 1 | -0.000241076 | identity_gdp_input_forces_identity_factor | -0.371277 | -0.0241018 | -0.481489 | accepted_definitional_restoration |
| low | middle_east_low__12c_delay_6m | PED | 2032Q1 | 1.00016 | 1 | -0.000161834 | identity_gdp_input_forces_identity_factor | -0.246832 | -0.0161808 | -0.323248 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2026Q4 | 1.00227 | 1 | -0.00227178 | positive_response_to_lower_gdp_capped_at_identity | -2.41564e+06 | -0.226663 | -2.51585 | accepted_expected_guard |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q1 | 1.00042 | 1 | -0.000420419 | positive_response_to_lower_gdp_capped_at_identity | -438100 | -0.0420242 | -0.466448 | accepted_expected_guard |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q2 | 1.00106 | 1 | -0.00106283 | identity_gdp_input_forces_identity_factor | -1.07219e+06 | -0.10617 | -1.17843 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q3 | 1.00188 | 1 | -0.00188363 | identity_gdp_input_forces_identity_factor | -1.92544e+06 | -0.188009 | -2.0868 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2027Q4 | 1.00077 | 1 | -0.000766776 | identity_gdp_input_forces_identity_factor | -827671 | -0.0766189 | -0.850432 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q1 | 1.00023 | 1 | -0.000229061 | identity_gdp_input_forces_identity_factor | -239820 | -0.0229009 | -0.254188 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q2 | 0.99996 | 1 | 3.95595e-05 | identity_gdp_input_forces_identity_factor | 40312.5 | 0.0039561 | 0.0439108 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q3 | 1.00006 | 1 | -6.09073e-05 | identity_gdp_input_forces_identity_factor | -62857.7 | -0.00609036 | -0.0676 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2028Q4 | 1.00002 | 1 | -2.48246e-05 | identity_gdp_input_forces_identity_factor | -27045.4 | -0.0024824 | -0.0275534 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q1 | 1.00001 | 1 | -7.52059e-06 | identity_gdp_input_forces_identity_factor | -7945.06 | -0.000752053 | -0.00834741 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q2 | 1 | 1 | -3.32747e-06 | identity_gdp_input_forces_identity_factor | -3423 | -0.000332746 | -0.00369331 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q3 | 1 | 1 | -2.0736e-06 | identity_gdp_input_forces_identity_factor | -2160.1 | -0.000207359 | -0.00230159 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2029Q4 | 1 | 1 | -8.50645e-07 | identity_gdp_input_forces_identity_factor | -935.2 | -8.50644e-05 | -0.000944173 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q1 | 1 | 1 | -2.64428e-07 | identity_gdp_input_forces_identity_factor | -281.785 | -2.64428e-05 | -0.000293502 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q2 | 1 | 1 | -1.20833e-07 | identity_gdp_input_forces_identity_factor | -125.345 | -1.20833e-05 | -0.000134118 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q3 | 1 | 1 | -7.09904e-08 | identity_gdp_input_forces_identity_factor | -74.5552 | -7.09904e-06 | -7.87958e-05 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2030Q4 | 1 | 1 | -2.89638e-08 | identity_gdp_input_forces_identity_factor | -32.081 | -2.89638e-06 | -3.21484e-05 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q1 | 1 | 1 | -9.31028e-09 | identity_gdp_input_forces_identity_factor | -9.99658 | -9.31028e-07 | -1.03339e-05 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q2 | 1 | 1 | -4.33016e-09 | identity_gdp_input_forces_identity_factor | -4.52731 | -4.33016e-07 | -4.80626e-06 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q3 | 1 | 1 | -2.44078e-09 | identity_gdp_input_forces_identity_factor | -2.57309 | -2.44078e-07 | -2.70914e-06 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2031Q4 | 1 | 1 | -9.89366e-10 | identity_gdp_input_forces_identity_factor | -1.10058 | -9.89366e-08 | -1.09815e-06 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q1 | 1 | 1 | -3.29416e-10 | identity_gdp_input_forces_identity_factor | -0.354931 | -3.29416e-08 | -3.65635e-07 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q2 | 1 | 1 | -1.54599e-10 | identity_gdp_input_forces_identity_factor | -0.16207 | -1.54599e-08 | -1.71597e-07 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q3 | 1 | 1 | -8.3938e-11 | identity_gdp_input_forces_identity_factor | -0.0890514 | -8.3938e-09 | -9.3167e-08 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2032Q4 | 1 | 1 | -3.3836e-11 | identity_gdp_input_forces_identity_factor | -0.0378685 | -3.3836e-09 | -3.75563e-08 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q1 | 1 | 1 | -1.16329e-11 | identity_gdp_input_forces_identity_factor | -0.0126152 | -1.1633e-09 | -1.2912e-08 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q2 | 1 | 1 | -5.48628e-12 | identity_gdp_input_forces_identity_factor | -0.00578892 | -5.48626e-10 | -6.08947e-09 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q3 | 1 | 1 | -2.8868e-12 | identity_gdp_input_forces_identity_factor | -0.00308323 | -2.88685e-10 | -3.20426e-09 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | HEAVY_RUC | 2033Q4 | 1 | 1 | -1.16018e-12 | identity_gdp_input_forces_identity_factor | -0.00130677 | -1.16022e-10 | -1.28778e-09 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2027Q2 | 0.9988 | 1 | 0.00119997 | identity_gdp_input_forces_identity_factor | 1.84029 | 0.120141 | 2.4001 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2027Q3 | 0.999946 | 1 | 5.42344e-05 | identity_gdp_input_forces_identity_factor | 0.0835641 | 0.00542373 | 0.108351 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2027Q4 | 1.00009 | 1 | -9.24272e-05 | identity_gdp_input_forces_identity_factor | -0.14383 | -0.00924186 | -0.184627 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2028Q1 | 1.00007 | 1 | -7.10911e-05 | identity_gdp_input_forces_identity_factor | -0.109676 | -0.00710861 | -0.142011 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2028Q2 | 1.00014 | 1 | -0.000143594 | identity_gdp_input_forces_identity_factor | -0.220718 | -0.0143574 | -0.286821 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2029Q3 | 0.998664 | 1 | 0.00133573 | identity_gdp_input_forces_identity_factor | 2.05438 | 0.133752 | 2.672 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2029Q4 | 0.998621 | 1 | 0.00137853 | identity_gdp_input_forces_identity_factor | 2.13763 | 0.138043 | 2.75772 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2030Q1 | 0.998663 | 1 | 0.00133702 | identity_gdp_input_forces_identity_factor | 2.05422 | 0.133881 | 2.67457 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2030Q2 | 0.998662 | 1 | 0.00133772 | identity_gdp_input_forces_identity_factor | 2.04723 | 0.133951 | 2.67598 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2030Q3 | 0.998663 | 1 | 0.00133744 | identity_gdp_input_forces_identity_factor | 2.05422 | 0.133923 | 2.67542 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2031Q1 | 1.00019 | 1 | -0.000190168 | identity_gdp_input_forces_identity_factor | -0.292523 | -0.0190132 | -0.379831 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2031Q2 | 1.00024 | 1 | -0.000241456 | identity_gdp_input_forces_identity_factor | -0.369777 | -0.0241398 | -0.482247 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2031Q3 | 1.00024 | 1 | -0.00024151 | identity_gdp_input_forces_identity_factor | -0.368935 | -0.0241451 | -0.482354 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2031Q4 | 1.00024 | 1 | -0.000241076 | identity_gdp_input_forces_identity_factor | -0.371277 | -0.0241018 | -0.481489 | accepted_definitional_restoration |
| low | middle_east_low__12c_no_uplift | PED | 2032Q1 | 1.00016 | 1 | -0.000161834 | identity_gdp_input_forces_identity_factor | -0.246832 | -0.0161808 | -0.323248 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2027Q4 | 1.00181 | 1 | -0.0018122 | positive_response_to_lower_gdp_capped_at_identity | -1.93101e+06 | -0.180892 | -2.00782 | accepted_expected_guard |
| medium | middle_east_medium | HEAVY_RUC | 2028Q1 | 1.00455 | 1 | -0.00455262 | positive_response_to_lower_gdp_capped_at_identity | -4.7506e+06 | -0.453198 | -5.03028 | accepted_expected_guard |
| medium | middle_east_medium | HEAVY_RUC | 2028Q2 | 1.00466 | 1 | -0.00465593 | identity_gdp_input_forces_identity_factor | -4.7287e+06 | -0.463435 | -5.1439 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2028Q3 | 1.0026 | 1 | -0.00259883 | identity_gdp_input_forces_identity_factor | -2.67305e+06 | -0.25921 | -2.8771 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2028Q4 | 1.0016 | 1 | -0.00159669 | identity_gdp_input_forces_identity_factor | -1.73366e+06 | -0.159415 | -1.76942 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2029Q1 | 1.00069 | 1 | -0.000685567 | identity_gdp_input_forces_identity_factor | -721915 | -0.0685097 | -0.760424 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2029Q2 | 1.00032 | 1 | -0.000322931 | identity_gdp_input_forces_identity_factor | -331121 | -0.0322827 | -0.358321 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2029Q3 | 1.00009 | 1 | -9.12137e-05 | identity_gdp_input_forces_identity_factor | -94707.8 | -0.00912054 | -0.101233 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2029Q4 | 0.999936 | 1 | 6.43265e-05 | identity_gdp_input_forces_identity_factor | 70488.1 | 0.00643307 | 0.0714039 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2030Q1 | 1.00002 | 1 | -1.61509e-05 | identity_gdp_input_forces_identity_factor | -17156.6 | -0.00161506 | -0.0179264 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2030Q2 | 1.00001 | 1 | -6.76794e-06 | identity_gdp_input_forces_identity_factor | -6998.38 | -0.00067679 | -0.00751203 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2030Q3 | 1 | 1 | -3.24058e-06 | identity_gdp_input_forces_identity_factor | -3392.43 | -0.000324057 | -0.00359687 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2030Q4 | 1 | 1 | -1.87241e-06 | identity_gdp_input_forces_identity_factor | -2067.27 | -0.000187241 | -0.00207828 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2031Q1 | 1 | 1 | -7.54795e-07 | identity_gdp_input_forces_identity_factor | -807.938 | -7.54794e-05 | -0.000837784 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2031Q2 | 1 | 1 | -2.4089e-07 | identity_gdp_input_forces_identity_factor | -251.081 | -2.40889e-05 | -0.000267375 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2031Q3 | 1 | 1 | -1.15655e-07 | identity_gdp_input_forces_identity_factor | -121.924 | -1.15655e-05 | -0.000128371 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2031Q4 | 1 | 1 | -6.44945e-08 | identity_gdp_input_forces_identity_factor | -71.7444 | -6.44945e-06 | -7.15857e-05 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2032Q1 | 1 | 1 | -2.57549e-08 | identity_gdp_input_forces_identity_factor | -27.7498 | -2.57549e-06 | -2.85867e-05 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2032Q2 | 1 | 1 | -8.55656e-09 | identity_gdp_input_forces_identity_factor | -8.97007 | -8.55655e-07 | -9.49735e-06 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2032Q3 | 1 | 1 | -4.11119e-09 | identity_gdp_input_forces_identity_factor | -4.36164 | -4.11119e-07 | -4.56322e-06 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2032Q4 | 1 | 1 | -2.21801e-09 | identity_gdp_input_forces_identity_factor | -2.48235 | -2.21801e-07 | -2.46188e-06 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2033Q1 | 1 | 1 | -8.80015e-10 | identity_gdp_input_forces_identity_factor | -0.954319 | -8.80015e-08 | -9.76772e-07 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2033Q2 | 1 | 1 | -3.02855e-10 | identity_gdp_input_forces_identity_factor | -0.319563 | -3.02855e-08 | -3.36154e-07 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.45577e-10 | identity_gdp_input_forces_identity_factor | -0.155479 | -1.45577e-08 | -1.61583e-07 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2033Q4 | 1 | 1 | -7.6265e-11 | identity_gdp_input_forces_identity_factor | -0.0858986 | -7.62651e-09 | -8.46504e-08 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2034Q1 | 1 | 1 | -3.01599e-11 | identity_gdp_input_forces_identity_factor | -0.0329349 | -3.01598e-09 | -3.34759e-08 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2034Q2 | 1 | 1 | -1.07023e-11 | identity_gdp_input_forces_identity_factor | -0.0113721 | -1.07023e-09 | -1.1879e-08 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2034Q3 | 1 | 1 | -5.13944e-12 | identity_gdp_input_forces_identity_factor | -0.0055263 | -5.13939e-10 | -5.70447e-09 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2034Q4 | 1 | 1 | -2.62035e-12 | identity_gdp_input_forces_identity_factor | -0.00297093 | -2.62032e-10 | -2.90843e-09 | accepted_definitional_restoration |
| medium | middle_east_medium | HEAVY_RUC | 2035Q1 | 1 | 1 | -1.03473e-12 | identity_gdp_input_forces_identity_factor | -0.00113726 | -1.0348e-10 | -1.14857e-09 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2028Q1 | 1.00005 | 1 | -5.47486e-05 | positive_response_to_lower_gdp_capped_at_identity | -0.083961 | -0.00547456 | -0.109367 | accepted_expected_guard |
| medium | middle_east_medium | PED | 2028Q2 | 0.999543 | 1 | 0.000457243 | identity_gdp_input_forces_identity_factor | 0.69866 | 0.0457452 | 0.913864 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2028Q3 | 1.00013 | 1 | -0.000129983 | identity_gdp_input_forces_identity_factor | -0.199374 | -0.0129967 | -0.259638 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2028Q4 | 0.999928 | 1 | 7.20831e-05 | identity_gdp_input_forces_identity_factor | 0.111531 | 0.00720882 | 0.144013 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2029Q3 | 1.00134 | 1 | -0.00133752 | identity_gdp_input_forces_identity_factor | -2.04514 | -0.133573 | -2.66843 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2029Q4 | 1.00138 | 1 | -0.00138043 | identity_gdp_input_forces_identity_factor | -2.12816 | -0.137853 | -2.75392 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2030Q1 | 1.00134 | 1 | -0.00133881 | identity_gdp_input_forces_identity_factor | -2.04507 | -0.133702 | -2.671 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2030Q2 | 1.00134 | 1 | -0.00133951 | identity_gdp_input_forces_identity_factor | -2.03815 | -0.133772 | -2.6724 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2030Q3 | 1.00134 | 1 | -0.00133923 | identity_gdp_input_forces_identity_factor | -2.04515 | -0.133744 | -2.67184 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2031Q1 | 0.99981 | 1 | 0.000190132 | identity_gdp_input_forces_identity_factor | 0.290797 | 0.0190168 | 0.379903 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2031Q2 | 0.999759 | 1 | 0.000241398 | identity_gdp_input_forces_identity_factor | 0.367584 | 0.0241456 | 0.482364 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2031Q3 | 0.999759 | 1 | 0.000241451 | identity_gdp_input_forces_identity_factor | 0.368846 | 0.024151 | 0.48247 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2031Q4 | 0.999759 | 1 | 0.000241018 | identity_gdp_input_forces_identity_factor | 0.371187 | 0.0241076 | 0.481605 | accepted_definitional_restoration |
| medium | middle_east_medium | PED | 2032Q1 | 0.999838 | 1 | 0.000161808 | identity_gdp_input_forces_identity_factor | 0.246792 | 0.0161834 | 0.3233 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2027Q4 | 1.00181 | 1 | -0.0018122 | positive_response_to_lower_gdp_capped_at_identity | -1.93101e+06 | -0.180892 | -2.00782 | accepted_expected_guard |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q1 | 1.00455 | 1 | -0.00455262 | positive_response_to_lower_gdp_capped_at_identity | -4.7506e+06 | -0.453198 | -5.03028 | accepted_expected_guard |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q2 | 1.00466 | 1 | -0.00465593 | identity_gdp_input_forces_identity_factor | -4.7287e+06 | -0.463435 | -5.1439 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q3 | 1.0026 | 1 | -0.00259883 | identity_gdp_input_forces_identity_factor | -2.67305e+06 | -0.25921 | -2.8771 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2028Q4 | 1.0016 | 1 | -0.00159669 | identity_gdp_input_forces_identity_factor | -1.73366e+06 | -0.159415 | -1.76942 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q1 | 1.00069 | 1 | -0.000685567 | identity_gdp_input_forces_identity_factor | -721915 | -0.0685097 | -0.760424 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q2 | 1.00032 | 1 | -0.000322931 | identity_gdp_input_forces_identity_factor | -331121 | -0.0322827 | -0.358321 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q3 | 1.00009 | 1 | -9.12137e-05 | identity_gdp_input_forces_identity_factor | -94707.8 | -0.00912054 | -0.101233 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2029Q4 | 0.999936 | 1 | 6.43265e-05 | identity_gdp_input_forces_identity_factor | 70488.1 | 0.00643307 | 0.0714039 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q1 | 1.00002 | 1 | -1.61509e-05 | identity_gdp_input_forces_identity_factor | -17156.6 | -0.00161506 | -0.0179264 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q2 | 1.00001 | 1 | -6.76794e-06 | identity_gdp_input_forces_identity_factor | -6998.38 | -0.00067679 | -0.00751203 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q3 | 1 | 1 | -3.24058e-06 | identity_gdp_input_forces_identity_factor | -3392.43 | -0.000324057 | -0.00359687 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2030Q4 | 1 | 1 | -1.87241e-06 | identity_gdp_input_forces_identity_factor | -2067.27 | -0.000187241 | -0.00207828 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q1 | 1 | 1 | -7.54795e-07 | identity_gdp_input_forces_identity_factor | -807.938 | -7.54794e-05 | -0.000837784 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q2 | 1 | 1 | -2.4089e-07 | identity_gdp_input_forces_identity_factor | -251.081 | -2.40889e-05 | -0.000267375 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q3 | 1 | 1 | -1.15655e-07 | identity_gdp_input_forces_identity_factor | -121.924 | -1.15655e-05 | -0.000128371 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2031Q4 | 1 | 1 | -6.44945e-08 | identity_gdp_input_forces_identity_factor | -71.7444 | -6.44945e-06 | -7.15857e-05 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q1 | 1 | 1 | -2.57549e-08 | identity_gdp_input_forces_identity_factor | -27.7498 | -2.57549e-06 | -2.85867e-05 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q2 | 1 | 1 | -8.55656e-09 | identity_gdp_input_forces_identity_factor | -8.97007 | -8.55655e-07 | -9.49735e-06 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q3 | 1 | 1 | -4.11119e-09 | identity_gdp_input_forces_identity_factor | -4.36164 | -4.11119e-07 | -4.56322e-06 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2032Q4 | 1 | 1 | -2.21801e-09 | identity_gdp_input_forces_identity_factor | -2.48235 | -2.21801e-07 | -2.46188e-06 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q1 | 1 | 1 | -8.80015e-10 | identity_gdp_input_forces_identity_factor | -0.954319 | -8.80015e-08 | -9.76772e-07 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q2 | 1 | 1 | -3.02855e-10 | identity_gdp_input_forces_identity_factor | -0.319563 | -3.02855e-08 | -3.36154e-07 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.45577e-10 | identity_gdp_input_forces_identity_factor | -0.155479 | -1.45577e-08 | -1.61583e-07 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2033Q4 | 1 | 1 | -7.6265e-11 | identity_gdp_input_forces_identity_factor | -0.0858986 | -7.62651e-09 | -8.46504e-08 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q1 | 1 | 1 | -3.01599e-11 | identity_gdp_input_forces_identity_factor | -0.0329349 | -3.01598e-09 | -3.34759e-08 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q2 | 1 | 1 | -1.07023e-11 | identity_gdp_input_forces_identity_factor | -0.0113721 | -1.07023e-09 | -1.1879e-08 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q3 | 1 | 1 | -5.13944e-12 | identity_gdp_input_forces_identity_factor | -0.0055263 | -5.13939e-10 | -5.70447e-09 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2034Q4 | 1 | 1 | -2.62035e-12 | identity_gdp_input_forces_identity_factor | -0.00297093 | -2.62032e-10 | -2.90843e-09 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | HEAVY_RUC | 2035Q1 | 1 | 1 | -1.03473e-12 | identity_gdp_input_forces_identity_factor | -0.00113726 | -1.0348e-10 | -1.14857e-09 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q1 | 1.00005 | 1 | -5.47486e-05 | positive_response_to_lower_gdp_capped_at_identity | -0.083961 | -0.00547456 | -0.109367 | accepted_expected_guard |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q2 | 0.999543 | 1 | 0.000457243 | identity_gdp_input_forces_identity_factor | 0.69866 | 0.0457452 | 0.913864 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q3 | 1.00013 | 1 | -0.000129983 | identity_gdp_input_forces_identity_factor | -0.199374 | -0.0129967 | -0.259638 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2028Q4 | 0.999928 | 1 | 7.20831e-05 | identity_gdp_input_forces_identity_factor | 0.111531 | 0.00720882 | 0.144013 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2029Q3 | 1.00134 | 1 | -0.00133752 | identity_gdp_input_forces_identity_factor | -2.04514 | -0.133573 | -2.66843 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2029Q4 | 1.00138 | 1 | -0.00138043 | identity_gdp_input_forces_identity_factor | -2.12816 | -0.137853 | -2.75392 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2030Q1 | 1.00134 | 1 | -0.00133881 | identity_gdp_input_forces_identity_factor | -2.04507 | -0.133702 | -2.671 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2030Q2 | 1.00134 | 1 | -0.00133951 | identity_gdp_input_forces_identity_factor | -2.03815 | -0.133772 | -2.6724 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2030Q3 | 1.00134 | 1 | -0.00133923 | identity_gdp_input_forces_identity_factor | -2.04515 | -0.133744 | -2.67184 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q1 | 0.99981 | 1 | 0.000190132 | identity_gdp_input_forces_identity_factor | 0.290797 | 0.0190168 | 0.379903 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q2 | 0.999759 | 1 | 0.000241398 | identity_gdp_input_forces_identity_factor | 0.367584 | 0.0241456 | 0.482364 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q3 | 0.999759 | 1 | 0.000241451 | identity_gdp_input_forces_identity_factor | 0.368846 | 0.024151 | 0.48247 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2031Q4 | 0.999759 | 1 | 0.000241018 | identity_gdp_input_forces_identity_factor | 0.371187 | 0.0241076 | 0.481605 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_delay_6m | PED | 2032Q1 | 0.999838 | 1 | 0.000161808 | identity_gdp_input_forces_identity_factor | 0.246792 | 0.0161834 | 0.3233 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2027Q4 | 1.00181 | 1 | -0.0018122 | positive_response_to_lower_gdp_capped_at_identity | -1.93728e+06 | -0.180892 | -2.00782 | accepted_expected_guard |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q1 | 1.00455 | 1 | -0.00455262 | positive_response_to_lower_gdp_capped_at_identity | -4.76645e+06 | -0.453198 | -5.03028 | accepted_expected_guard |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q2 | 1.00466 | 1 | -0.00465593 | identity_gdp_input_forces_identity_factor | -4.74456e+06 | -0.463435 | -5.1439 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q3 | 1.0026 | 1 | -0.00259883 | identity_gdp_input_forces_identity_factor | -2.68205e+06 | -0.25921 | -2.8771 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2028Q4 | 1.0016 | 1 | -0.00159669 | identity_gdp_input_forces_identity_factor | -1.73953e+06 | -0.159415 | -1.76942 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q1 | 1.00069 | 1 | -0.000685567 | identity_gdp_input_forces_identity_factor | -724262 | -0.0685097 | -0.760424 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q2 | 1.00032 | 1 | -0.000322931 | identity_gdp_input_forces_identity_factor | -332203 | -0.0322827 | -0.358321 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q3 | 1.00009 | 1 | -9.12137e-05 | identity_gdp_input_forces_identity_factor | -95018.7 | -0.00912054 | -0.101233 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2029Q4 | 0.999936 | 1 | 6.43265e-05 | identity_gdp_input_forces_identity_factor | 70720.7 | 0.00643307 | 0.0714039 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q1 | 1.00002 | 1 | -1.61509e-05 | identity_gdp_input_forces_identity_factor | -17211.1 | -0.00161506 | -0.0179264 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q2 | 1.00001 | 1 | -6.76794e-06 | identity_gdp_input_forces_identity_factor | -7020.7 | -0.00067679 | -0.00751203 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q3 | 1 | 1 | -3.24058e-06 | identity_gdp_input_forces_identity_factor | -3403.31 | -0.000324057 | -0.00359687 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2030Q4 | 1 | 1 | -1.87241e-06 | identity_gdp_input_forces_identity_factor | -2073.93 | -0.000187241 | -0.00207828 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q1 | 1 | 1 | -7.54795e-07 | identity_gdp_input_forces_identity_factor | -810.435 | -7.54794e-05 | -0.000837784 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q2 | 1 | 1 | -2.4089e-07 | identity_gdp_input_forces_identity_factor | -251.857 | -2.40889e-05 | -0.000267375 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q3 | 1 | 1 | -1.15655e-07 | identity_gdp_input_forces_identity_factor | -121.924 | -1.15655e-05 | -0.000128371 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2031Q4 | 1 | 1 | -6.44945e-08 | identity_gdp_input_forces_identity_factor | -71.7444 | -6.44945e-06 | -7.15857e-05 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q1 | 1 | 1 | -2.57549e-08 | identity_gdp_input_forces_identity_factor | -27.7498 | -2.57549e-06 | -2.85867e-05 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q2 | 1 | 1 | -8.55656e-09 | identity_gdp_input_forces_identity_factor | -8.97007 | -8.55655e-07 | -9.49735e-06 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q3 | 1 | 1 | -4.11119e-09 | identity_gdp_input_forces_identity_factor | -4.36164 | -4.11119e-07 | -4.56322e-06 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2032Q4 | 1 | 1 | -2.21801e-09 | identity_gdp_input_forces_identity_factor | -2.48235 | -2.21801e-07 | -2.46188e-06 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q1 | 1 | 1 | -8.80015e-10 | identity_gdp_input_forces_identity_factor | -0.954319 | -8.80015e-08 | -9.76772e-07 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q2 | 1 | 1 | -3.02855e-10 | identity_gdp_input_forces_identity_factor | -0.319563 | -3.02855e-08 | -3.36154e-07 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q3 | 1 | 1 | -1.45577e-10 | identity_gdp_input_forces_identity_factor | -0.155479 | -1.45577e-08 | -1.61583e-07 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2033Q4 | 1 | 1 | -7.6265e-11 | identity_gdp_input_forces_identity_factor | -0.0858986 | -7.62651e-09 | -8.46504e-08 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q1 | 1 | 1 | -3.01599e-11 | identity_gdp_input_forces_identity_factor | -0.0329349 | -3.01598e-09 | -3.34759e-08 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q2 | 1 | 1 | -1.07023e-11 | identity_gdp_input_forces_identity_factor | -0.0113721 | -1.07023e-09 | -1.1879e-08 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q3 | 1 | 1 | -5.13944e-12 | identity_gdp_input_forces_identity_factor | -0.0055263 | -5.13939e-10 | -5.70447e-09 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2034Q4 | 1 | 1 | -2.62035e-12 | identity_gdp_input_forces_identity_factor | -0.00297093 | -2.62032e-10 | -2.90843e-09 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | HEAVY_RUC | 2035Q1 | 1 | 1 | -1.03473e-12 | identity_gdp_input_forces_identity_factor | -0.00113726 | -1.0348e-10 | -1.14857e-09 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q1 | 1.00005 | 1 | -5.47486e-05 | positive_response_to_lower_gdp_capped_at_identity | -0.0844632 | -0.00547456 | -0.109367 | accepted_expected_guard |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q2 | 0.999543 | 1 | 0.000457243 | identity_gdp_input_forces_identity_factor | 0.702825 | 0.0457452 | 0.913864 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q3 | 1.00013 | 1 | -0.000129983 | identity_gdp_input_forces_identity_factor | -0.200558 | -0.0129967 | -0.259638 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2028Q4 | 0.999928 | 1 | 7.20831e-05 | identity_gdp_input_forces_identity_factor | 0.112191 | 0.00720882 | 0.144013 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2029Q3 | 1.00134 | 1 | -0.00133752 | identity_gdp_input_forces_identity_factor | -2.05713 | -0.133573 | -2.66843 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2029Q4 | 1.00138 | 1 | -0.00138043 | identity_gdp_input_forces_identity_factor | -2.14059 | -0.137853 | -2.75392 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2030Q1 | 1.00134 | 1 | -0.00133881 | identity_gdp_input_forces_identity_factor | -2.05697 | -0.133702 | -2.671 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2030Q2 | 1.00134 | 1 | -0.00133951 | identity_gdp_input_forces_identity_factor | -2.04997 | -0.133772 | -2.6724 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2030Q3 | 1.00134 | 1 | -0.00133923 | identity_gdp_input_forces_identity_factor | -2.05697 | -0.133744 | -2.67184 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q1 | 0.99981 | 1 | 0.000190132 | identity_gdp_input_forces_identity_factor | 0.292467 | 0.0190168 | 0.379903 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q2 | 0.999759 | 1 | 0.000241398 | identity_gdp_input_forces_identity_factor | 0.369688 | 0.0241456 | 0.482364 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q3 | 0.999759 | 1 | 0.000241451 | identity_gdp_input_forces_identity_factor | 0.368846 | 0.024151 | 0.48247 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2031Q4 | 0.999759 | 1 | 0.000241018 | identity_gdp_input_forces_identity_factor | 0.371187 | 0.0241076 | 0.481605 | accepted_definitional_restoration |
| medium | middle_east_medium__12c_no_uplift | PED | 2032Q1 | 0.999838 | 1 | 0.000161808 | identity_gdp_input_forces_identity_factor | 0.246792 | 0.0161834 | 0.3233 | accepted_definitional_restoration |

## The two guard types mean different things

**`identity_gdp_input_forces_identity_factor`** - Definitional, not a model pathology. The scenario requires that where a quarter's GDP input equals Base, the GDP factor is exactly 1. The fitted replay carries recursive lag persistence from earlier stressed quarters, so its ratio drifts off 1 after the conflict path has already converged back to Base. The guard restores the identity the scenario definition demands.

**`positive_response_to_lower_gdp_capped_at_identity`** - Model pathology correction. A lower GDP input produced a HIGHER fitted activity factor - a wrong-sign out-of-distribution response. The guard caps it at no-change rather than reversing it, so the overlay never lets a downside scenario mechanically raise activity.

The identity guard binding often is therefore expected behaviour once a
conflict path converges back to Base, and its frequency tracks how long
the fitted lag structure carries persistence. The wrong-sign guard is the
one that indicates the fitted model being used outside its estimation
range, and it is the count worth watching.

Revenue-equivalent figures use guard-induced percentage change in stream activity applied to governed FY2025 revenue for that stream; indicative materiality scale, not a revenue forecast.

