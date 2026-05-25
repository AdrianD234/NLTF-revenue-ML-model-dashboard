# Stage 1 Dashboard Evidence Pack

This is a Parquet-first evidence pack for the NLTF Stage 1 Governance Dashboard. Point Codex/Streamlit to this folder and do not mix with old run folders or fixture data.

## Key files

- `data/candidate_cone.parquet`: curated 300-row candidate cone/universe. Use `plot_default_include` or `is_plot_candidate` for the default frontier plot.
- `data/finalists.parquet`: current recommended finalists.
- `data/schiff_benchmark.parquet`: pure Schiff benchmark rows.
- `data/ensemble_components.parquet`: parsed finalist ensemble weights from `ensemble_components_json`.
- `data/residual_predictions.parquet`: row-level actual/pred/error data for current finalists and pure Schiff benchmarks. Invalid zero-actual rows are excluded.
- `data/horizon_profiles.parquet`: true 1-12 horizon MAPE profiles from row-level predictions. Do not interpolate.
- `data/stress_horizon.parquet`: stress buckets and annual MAPE, with six canonical buckets.
- `data/scenario_comparison.parquet`: finalist vs Schiff full-sample and paired comparison metrics.
- `data/diagnostic_tests.parquet`: Durbin-Watson, ADF, KPSS, Breusch-Pagan, White, ARCH, JB, cointegration, calibration R².
- `data/diagnostic_acf.parquet`: ACF evidence with residual scope documented.
- `data/error_distribution.parquet`: absolute error rows for boxplots.
- `data/chart_contract.parquet`: maps the 16 dashboard panels to source tables.

## Important governance rules

- Full-sample gain and paired gain are different. Light RUC has positive full-sample gain but negative paired quarterly gain.
- Do not label full-sample gain charts as paired gain.
- Candidate frontier must use the curated cone sample, not only finalists/Schiff markers.
- If a source table is missing or `value_available` is false, show a missing-data state; do not plot a normal chart.
- The app should not load legacy CSV/XLSX run folders in default mode.
