# Clean-environment CI: baseline vs P0 branch

Baseline run 30228519139 on unmodified main (8431c61): 36 failed, 572 passed.
P0 branch run 30226687382 (a04e4b6): 36 failed, 615 passed.

Introduced by P0 (in P0, not in baseline): 0
Fixed by P0 (in baseline, not in P0): 0
Identical pre-existing failures: 36

## Every failure, present in BOTH runs

- `tests/test_cone_landscape_validation.py::test_candidate_landscape_default_mode_is_not_full_raw`
- `tests/test_cone_landscape_validation.py::test_candidate_landscape_has_distribution_sample`
- `tests/test_cone_landscape_validation.py::test_candidate_landscape_has_finalists`
- `tests/test_cone_landscape_validation.py::test_candidate_landscape_has_frontier_and_top_cluster_by_stream`
- `tests/test_cone_landscape_validation.py::test_candidate_landscape_has_schiff_benchmarks`
- `tests/test_cone_landscape_validation.py::test_candidate_landscape_is_capped`
- `tests/test_cone_landscape_validation.py::test_candidate_landscape_roles_are_populated`
- `tests/test_curated_data.py::test_candidate_landscape_sample_has_expected_roles`
- `tests/test_curated_data.py::test_candidate_landscape_sample_is_capped`
- `tests/test_curated_data.py::test_curated_data_latest_values`
- `tests/test_curated_data.py::test_ensemble_composition_positive_weights`
- `tests/test_curated_data.py::test_no_stale_autogluon_finalist_values`
- `tests/test_curated_data.py::test_pure_schiff_filter_excludes_residuals_and_blends`
- `tests/test_curated_data.py::test_stress_horizon_has_expected_buckets`
- `tests/test_ensemble_composition_validation.py::test_component_lookup_contains_full_names`
- `tests/test_ensemble_composition_validation.py::test_ensemble_component_labels_short`
- `tests/test_ensemble_composition_validation.py::test_ensemble_composition_has_all_streams`
- `tests/test_ensemble_composition_validation.py::test_ensemble_hover_is_readable`
- `tests/test_ensemble_composition_validation.py::test_ensemble_weights_are_positive`
- `tests/test_fuel_price_scenario.py::test_append_creates_three_distinct_idempotent_traces_with_exact_replay_values_and_annual_bridge`
- `tests/test_light_ruc_reproducibility_pack.py::test_light_ruc_reproducibility_validator_passes`
- `tests/test_light_ruc_reproducibility_pack.py::test_ped_inner_hpo_weights_are_grouped_by_source_file`
- `tests/test_net_revenue_timing_comparison.py::test_base_original_timing_reconciles_to_default_dashboard_hover_benchmarks`
- `tests/test_no_stale_finalist_values.py::test_current_finalist_models_are_static_convex_top18_arbitration_winners`
- `tests/test_no_stale_finalist_values.py::test_stale_autogluon_values_are_not_current_finalists`
- `tests/test_recursive_audit_log.py::test_recursive_audit_entries_are_verified_not_pending`
- `tests/test_recursive_audit_log.py::test_recursive_audit_loop_numbers_are_contiguous`
- `tests/test_recursive_audit_log.py::test_recursive_audit_screenshot_evidence_paths_exist`
- `tests/test_schiff_purity.py::test_pure_schiff_excludes_blends`
- `tests/test_schiff_purity.py::test_pure_schiff_excludes_residuals`
- `tests/test_schiff_purity.py::test_pure_schiff_excludes_solvers`
- `tests/test_schiff_purity.py::test_schiff_benchmark_page_uses_pure_schiff_only`
- `tests/test_stress_horizon_validation.py::test_light_ruc_2022_23_watchpoint_visible`
- `tests/test_stress_horizon_validation.py::test_stress_chart_hover_is_readable`
- `tests/test_stress_horizon_validation.py::test_stress_horizon_has_expected_buckets`
- `tests/test_visual_artifacts.py::test_page_screenshots_exist`

## Classification

- 32 failures: missing gitignored scratch under artifacts/. 28 of these are
  now recoverable in CI by running scripts/regenerate_curated_data_from_pack.py;
  the remaining 4 need developer-local scratch that cannot be rebuilt and
  carry the requires_local_scratch marker.
- 2 failures: Windows/Linux path-role classification, fixed on this branch
  by provenance_basename() normalising the separator before taking a basename.
- 2 failures: governed replay numerical divergence. See
  docs/REPLAY_PARITY_INVESTIGATION.md. Open; tolerances untouched.

