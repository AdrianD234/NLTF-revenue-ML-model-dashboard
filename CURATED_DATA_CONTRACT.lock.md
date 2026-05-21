# CURATED_DATA_CONTRACT.lock.md

This file defines the compressed data pack for the Stage 1 Model Governance Dashboard.

The dashboard must prefer `artifacts/curated_data/` for normal rendering and must not load every raw candidate or prediction row by default.

## Curated files

### `finalist_accuracy.csv`

Required columns:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `source_family`
- `model_kind`
- `feature_set`
- `quarterly_mape`
- `annual_mape`
- `quarterly_bias_pct`
- `governance_score`
- `finalist_role`

One row per recommended latest finalist, plus optional reference rows only where clearly labelled.

### `pdf_comparison.csv`

Required columns:

- `stream`
- `stream_label`
- `latest_quarterly_mape`
- `pdf_quarterly_mape`
- `quarterly_difference_pp`
- `latest_annual_mape`
- `pdf_annual_mape`
- `annual_difference_pp`
- `interpretation`

### `candidate_landscape_sample.csv`

Required columns:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `source_family`
- `model_kind`
- `feature_set`
- `quarterly_mape`
- `annual_mape`
- `quarterly_bias_pct`
- `governance_score`
- `candidate_role`
- `plot_marker`
- `plot_size`
- `include_reason`
- `is_recommended_finalist`
- `is_pure_schiff`
- `is_pdf_reference`
- `is_frontier`
- `is_top_quarterly`
- `is_top_annual`
- `is_distribution_sample`

This file is curated and capped. It must not include every raw candidate by default.

### `schiff_benchmark.csv`

Required columns:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `quarterly_mape`
- `annual_mape`
- `quarterly_bias_pct`
- `benchmark_role`
- `purity_flag`

Only pure structural Schiff rows may be treated as Schiff benchmarks. Residual-correction models, fixed blends, solver ensembles, and Schiff-residual challengers are not pure Schiff benchmarks.

### `stress_horizon.csv`

Required columns:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `stress_bucket`
- `mape`
- `stress_type`

Expected buckets where source data allows:

- `1-4 qtrs`
- `5-8 qtrs`
- `9-12 qtrs`
- `2024+`
- `2022-23`
- `Annual`

### `ensemble_composition.csv`

Required columns:

- `stream`
- `stream_label`
- `ensemble`
- `ensemble_short`
- `component_model`
- `component_short`
- `weight`
- `weight_label`
- `component_rank`
- `method`
- `role`

Use positive weights only for management charts. If a finalist resolves to one component, label the fallback clearly and do not present it as artificial placeholder data.

### `annual_predictions_selected.csv`

Required columns:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `june_year`
- `actual`
- `pred`
- `error_pct`
- `abs_error_pct`
- `selected_role`

### `quarterly_predictions_selected.csv`

Required where quarterly predictions exist locally. Include only selected finalist, pure Schiff, and important comparator models.

Required columns:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `origin`
- `target_period`
- `horizon`
- `actual`
- `pred`
- `error_pct`
- `abs_error_pct`
- `horizon_bucket`
- `selected_role`

If quarterly predictions are missing, the dashboard must hide quarter-level forecast charts and explain that this selected subset is needed.
