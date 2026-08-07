# Test-suite profile

- executed tests: **1910**  (skipped 53)
- failures/errors: **0**
- total measured test time: **41.8 min** (2506s)

## Concentration

| share of runtime | slowest N tests | as % of all executed tests |
| --- | --- | --- |
| 50% | 10 | 0.5% |
| 75% | 59 | 3.1% |
| 90% | 168 | 8.8% |

## Slowest files

| file | tests | total | share |
| --- | --- | --- | --- |
| `tests/test_view_invariant_sweep.py` | 10 | 735s | 29.3% |
| `tests/test_revenue_outlook_policy_runtime.py` | 52 | 264s | 10.5% |
| `tests/test_revenue_outlook_vfm_envelope.py` | 38 | 140s | 5.6% |
| `tests/test_fuel_price_scenario.py` | 32 | 131s | 5.2% |
| `tests/test_revenue_outlook_replay_cache.py` | 25 | 130s | 5.2% |
| `tests/test_streamlit_smoke.py` | 39 | 91s | 3.7% |
| `tests/test_scenario_comparison.py` | 26 | 85s | 3.4% |
| `tests/test_view_performance_caches.py` | 12 | 84s | 3.4% |
| `tests/test_revenue_outlook_ped_activity_2050.py` | 34 | 64s | 2.6% |
| `tests/test_quarterly_disaggregation.py` | 13 | 59s | 2.4% |
| `tests/test_revenue_source_app_views.py` | 26 | 57s | 2.3% |
| `tests/test_revenue_source_pack.py` | 22 | 45s | 1.8% |
| `tests/test_vfm_long_run_composition.py` | 96 | 40s | 1.6% |
| `tests/test_fleet_mix.py` | 11 | 38s | 1.5% |
| `tests/test_official_vintage_role_independence.py` | 28 | 37s | 1.5% |
| `tests/test_revenue_outlook.py` | 20 | 36s | 1.4% |
| `tests/test_engine_switcher.py` | 13 | 34s | 1.4% |
| `tests/test_revenue_outlook_excel_extract.py` | 17 | 34s | 1.3% |
| `tests/test_revenue_outlook_ui_slim_2050.py` | 47 | 34s | 1.3% |
| `tests/test_forecast_runner.py` | 21 | 29s | 1.2% |

## Slowest individual tests

| seconds | file | test |
| --- | --- | --- |
| 377.4 | `tests/test_view_invariant_sweep.py` | `test_actuals_are_immutable_under_every_sensitivity[ar1]` |
| 356.9 | `tests/test_view_invariant_sweep.py` | `test_actuals_are_immutable_under_every_sensitivity[ensemble]` |
| 121.7 | `tests/test_revenue_outlook_policy_runtime.py` | `test_every_materialised_state_equals_the_reference_pipeline[ar1]` |
| 119.4 | `tests/test_revenue_outlook_policy_runtime.py` | `test_every_materialised_state_equals_the_reference_pipeline[ensemble]` |
| 57.6 | `tests/test_quarterly_disaggregation.py` | `test_delayed_base_and_iran_net_revenue_quarters_reconcile_exactly_to_june_years` |
| 56.4 | `tests/test_revenue_outlook_replay_cache.py` | `test_replay_cache_matches_reference_exactly[ensemble]` |
| 55.4 | `tests/test_fuel_price_scenario.py` | `test_fixed_finalist_replay_preserves_base_and_orders_governed_conflict_paths` |
| 49.6 | `tests/test_revenue_outlook_replay_cache.py` | `test_replay_cache_matches_reference_exactly[ar1]` |
| 48.4 | `tests/test_fuel_price_scenario.py` | `test_ar1_pack_replays_twelve_paths_and_retains_source_lineage` |
| 47.0 | `tests/test_view_performance_caches.py` | `test_current_and_mbu_policy_nine_state_matrix_keeps_fuel_on_current_scope` |
| 36.4 | `tests/test_official_vintage_role_independence.py` | `test_each_combination_records_its_own_roles[BEFU26-BEFU26]` |
| 24.8 | `tests/test_revenue_outlook_vfm_envelope.py` | `test_the_selected_official_comparator_cannot_alter_the_current_vfm_band` |
| 24.1 | `tests/test_eruc_transition.py` | `test_eruc_view_footprint_and_cascade_on_real_pack` |
| 22.6 | `tests/test_scenario_comparison.py` | `test_current_and_mbu26_uplift_switches_are_independent` |
| 22.4 | `tests/test_revenue_outlook_vfm_envelope.py` | `test_returning_to_the_original_controls_returns_the_original_band` |
| 20.8 | `tests/test_revenue_outlook_vfm_envelope.py` | `test_the_current_policy_selection_moves_the_band_and_is_applied_once` |
| 18.8 | `tests/test_streamlit_smoke.py` | `test_revenue_outlook_compare_mode_renders_pt_and_freight_for_scenario_b` |
| 18.2 | `tests/test_fleet_mix.py` | `test_dashboard_fleet_preserves_light_and_heavy_class_pools` |
| 18.2 | `tests/test_streamlit_smoke.py` | `test_revenue_outlook_compare_mode_keeps_lever_state_for_downstream` |
| 16.2 | `tests/test_view_performance_caches.py` | `test_cone_band_is_uptake_key_invariant` |
| 16.1 | `tests/test_anchored_shape_conflict_convergence.py` | `test_conflict_paths_are_present_and_differ_inside_the_window` |
| 15.6 | `tests/test_revenue_source_app_views.py` | `test_revenue_source_every_series_valid_control_permutation_has_governed_traces` |
| 14.7 | `tests/test_revenue_chart_layers.py` | `test_the_figure_draws_bands_beneath_every_line` |
| 13.0 | `tests/test_revenue_outlook_vfm_envelope.py` | `test_both_engines_produce_the_same_presentation_contract` |
| 12.7 | `tests/test_revenue_outlook_vfm_envelope.py` | `test_the_envelope_is_absent_unless_its_layer_is_selected` |
| 12.4 | `tests/test_revenue_outlook_vfm_envelope.py` | `test_the_selected_long_run_schedule_enters_the_band_identity` |
| 12.3 | `tests/test_anchored_shape_preview_behaviour.py` | `test_the_selection_is_not_a_no_op` |
| 11.3 | `tests/test_streamlit_smoke.py` | `test_revenue_outlook_activity_opens_policy_levers` |
| 11.1 | `tests/test_revenue_outlook.py` | `test_ped_bridge_modes_materialize_raw_optimized_and_reconcile` |
| 10.8 | `tests/test_vfm_long_run_composition.py` | `test_all_three_bases_share_one_light_pool[2031]` |