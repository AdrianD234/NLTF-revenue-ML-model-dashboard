# Data Contract

The dashboard expects a curated Parquet file named `stage1_curated_candidate_cone.parquet`. Metadata JSON and CSV mirror files are optional audit evidence, not primary runtime data.

## Required Core Fields

The loader can create missing optional columns, but the Parquet pack must carry enough information to identify candidates, finalists, streams, model families, metrics, and governance roles.

Required or strongly expected fields:

- `stream`
- `stream_label`
- `model`
- `model_short`
- `source_family`
- `model_kind`
- `feature_set`
- `quarterly_mape`
- `annual_mape`
- `is_current_recommended`
- `is_pure_schiff`
- `plot_default_include`

## Optional Metric Fields

- `quarterly_bias_pct`
- `annual_bias_pct`
- `quarterly_p90_ape`
- `annual_p90_ape`
- `performance_rank`
- `performance_percentile`
- `performance_decile`
- `selection_score`
- `paired_gain_vs_schiff_pp`
- `paired_win_rate`
- `paired_common_pairs`

## Stress Bucket Aliases

Stress and horizon checks coalesce the first non-null value from these aliases:

| Bucket | Aliases |
| --- | --- |
| `1-4 qtrs` | `stress_1_4_qtrs_mape`, `mape_h01_04`, `h1_4_mape` |
| `5-8 qtrs` | `stress_5_8_qtrs_mape`, `mape_h05_08`, `h5_8_mape` |
| `9-12 qtrs` | `stress_9_12_qtrs_mape`, `mape_h09_12`, `h9_12_mape` |
| `2024+` | `stress_2024plus_mape`, `recent_2024_plus_mape`, `stress_2024_plus_mape` |
| `2022-23` | `stress_2022_23_mape`, `policy_2022_23_mape` |
| `Annual` | `stress_annual_mape`, `annual_mape`, `annual_mape_filled` |

All six bucket rows must be present in the derived frame for each current finalist. Missing values remain `NaN`; charts must use `connectgaps=False`.

## Horizon Fields

Horizon curves may use `mape_h01` through `mape_h12` only when those fields exist. If a stream has only bucket values, the dashboard should show the bucket view or a missing-data note rather than fabricating a 1-12 curve.

## Ensemble Components

Current finalist ensemble composition must come from `ensemble_components_json`. The expected JSON shape is a list of objects with:

- `component_model`
- `component_short`
- `weight`

If components are absent, the chart must show a missing-data state instead of demo weights.

## Diagnostic Fields

Diagnostic panels use these fields where available:

- `durbin_watson`
- `adj_r2`, `adjusted_r2`, `mz_r2`, or `diag_mz_r2`
- `adf_pvalue`
- `kpss_pvalue`
- `breusch_pagan_pvalue`
- `white_pvalue`
- `jarque_bera_pvalue`
- `cointegration_pvalue`

If the source is `mz_r2` or `diag_mz_r2`, UI labels must say Calibration R2 or MZ R2, not Adjusted R2.
