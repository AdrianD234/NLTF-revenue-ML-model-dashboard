# Governed pack reproducibility — Phase A clean-room probe

Probe of every governed pack at `ac1895da9a517a0040c363b6077ae37e603ee9a0`
(origin/main), each in a fresh disposable clone inside the `nltf-ci:local`
Python 3.11 container: snapshot committed pack -> authoritative build 1 ->
value-level compare -> build 2 -> idempotency compare -> planner status.
Driver: `ci/probe_governed_pack_reproducibility.sh`;
comparator: `ci/pack_reproducibility_harness.py`.

Committed packs were built on Windows / Python 3.13.5 / numpy 2.4.6, so the
committed-vs-rebuild comparison crosses environments; each pack's own
documented numerical contract (quarterly display: ~1e-13 relative across
platforms; policy/replay tests: atol=1e-9) is the yardstick, and nothing is
normalised or suppressed - every differing cell is recorded in
`pack_value_differences.parquet` with its magnitude.

## Verdict

**The uncertainty mismatch is isolated.** Exactly one governed-value
movement exists across all four packs: `light_petrol_vkt` FY2031-FY2050 in
the offline uncertainty pack - 20 of 1,000 rows, all six band columns moved
by one rigid factor 1.014895961 (max abs 521.8 on `upper80`, 508.99 on
`central`), matching docs/FOLLOW_UP_PED_R2_DRIFT.md exactly. Every other
difference in any pack is cross-environment float noise inside the repo's
structural closure contract (atol 1e-9 + rtol 1e-12*|x|): at or below
7.3e-12 absolute (policy runtime, uncertainty non-affected rows), 1.13e-10
(quarterly display, whose manifest documents exactly this cross-platform
behaviour), and 2.2e-16 relative on the replay cache's forecast columns.
The single exception outside that contract is the replay cache's
`stored_replay_max_delta` column (288 cells, max 9.54e-07): the builder's
own recorded measurement of replay closure, environment-dependent by
construction and not a forecast, revenue or governed value - every
governed forecast column has zero outside-contract cells.

Every builder is **byte-idempotent** in-container (build 1 vs build 2
identical for all files in all four packs), and the planner reported every
pack `ok` on the committed tree before any build.

## Per-pack matrix

### replay_cache

- probe_sha: ac1895da9a517a0040c363b6077ae37e603ee9a0
- environment: nltf-ci:local (Docker, Python 3.11, Linux); committed packs built on Windows/Python 3.13.5
- files_compared: 72
- committed_vs_build1_class: value_movement
- governed_value_movement_files: 0
- governed_value_movement_list: none
- governed_first_divergence: none
- governed_movement_rows_by_series: {'': 11578, 'heavy_ruc_net_km': 2708, 'light_ruc_net_km': 8}
- float_noise_files_inside_structural_contract: 32
- replay_closure_diagnostic_files: ar1/frames/fuel.replay.future_forecasts.parquet (stored_replay_max_delta only, 144 cells, max 9.537e-07); ensemble/frames/fuel.replay.future_forecasts.parquet (stored_replay_max_delta only, 144 cells, max 9.537e-07)
- max_abs_diff_any_frame: 9.5367431640625e-07
- serialization_only_files: 0
- manifest_changes: ar1/manifest.json:value_movement; ensemble/manifest.json:value_movement
- build1_vs_build2_class: identical
- status_on_committed_tree: ok
- status_after_rebuilds: ok
- planner_cascade_after_rebuild: policy_runtime, databricks_bundle

### quarterly_display

- probe_sha: ac1895da9a517a0040c363b6077ae37e603ee9a0
- environment: nltf-ci:local (Docker, Python 3.11, Linux); committed packs built on Windows/Python 3.13.5
- files_compared: 8
- committed_vs_build1_class: value_movement
- governed_value_movement_files: 0
- governed_value_movement_list: none
- governed_first_divergence: none
- governed_movement_rows_by_series: none
- float_noise_files_inside_structural_contract: 2
- replay_closure_diagnostic_files: none
- max_abs_diff_any_frame: 1.127773430198431e-10
- serialization_only_files: 0
- manifest_changes: none
- build1_vs_build2_class: identical
- status_on_committed_tree: ok
- status_after_rebuilds: ok
- planner_cascade_after_rebuild: none

### uncertainty

- probe_sha: ac1895da9a517a0040c363b6077ae37e603ee9a0
- environment: nltf-ci:local (Docker, Python 3.11, Linux); committed packs built on Windows/Python 3.13.5
- files_compared: 3
- committed_vs_build1_class: value_movement
- governed_value_movement_files: 1
- governed_value_movement_list: uncertainty_band_rows.parquet
- governed_first_divergence: uncertainty_band_rows.parquet @ {'column': 'central', 'row_index': 5, 'series_id': 'light_ruc_net_km', 'FY': 2026, 'period': 'FY2026', 'engine': 'ensemble'}
- governed_movement_rows_by_series: {'light_petrol_vkt': 120}
- float_noise_files_inside_structural_contract: 1
- replay_closure_diagnostic_files: none
- max_abs_diff_any_frame: 521.8057540320733
- serialization_only_files: 0
- manifest_changes: manifest.json:serialization_only
- build1_vs_build2_class: identical
- status_on_committed_tree: ok
- status_after_rebuilds: ok
- planner_cascade_after_rebuild: policy_runtime, databricks_bundle

### policy_runtime

- probe_sha: ac1895da9a517a0040c363b6077ae37e603ee9a0
- environment: nltf-ci:local (Docker, Python 3.11, Linux); committed packs built on Windows/Python 3.13.5
- files_compared: 202
- committed_vs_build1_class: value_movement
- governed_value_movement_files: 0
- governed_value_movement_list: none
- governed_first_divergence: none
- governed_movement_rows_by_series: none
- float_noise_files_inside_structural_contract: 170
- replay_closure_diagnostic_files: none
- max_abs_diff_any_frame: 7.275957614183426e-12
- serialization_only_files: 0
- manifest_changes: ar1/manifest.json:value_movement; ensemble/manifest.json:value_movement
- build1_vs_build2_class: identical
- status_on_committed_tree: ok
- status_after_rebuilds: ok
- planner_cascade_after_rebuild: none

## Notes

- Manifest differences are provenance/serialization: `source_main_sha` and
  `build_environment` record where the rebuild ran, and per-file hash maps
  track the float-noise byte changes. None of them is a governed value.
- The planner cascade fired correctly after the uncertainty and replay
  rebuilds (`policy_runtime` -> stale, `databricks_bundle` -> affected),
  because the policy-runtime digest chains those manifests by content.
- Raw per-pack probe outputs are under `raw_phase_a/`.
