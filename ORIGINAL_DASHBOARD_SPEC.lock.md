# ORIGINAL_DASHBOARD_SPEC.lock.md

Locked product specification for the NLTF Stage 1 Model Governance Dashboard, transcribed from the original dashboard brief.

## Objective

- Build a Streamlit dashboard that visualises Stage 1 econometric and machine-learning model-discovery results for the NLTF revenue forecasting project.
- Let the user select a completed model-run folder.
- Read CSV/XLSX outputs robustly.
- Explore recommended finalist models by stream.
- Explore quarterly and annual MAPE.
- Explore the candidate search landscape.
- Compare Schiff structural benchmark against ML and ensemble candidates.
- Show finalist ensemble composition.
- Show forecast error distribution by horizon bucket.
- Show stress and horizon checks.
- Show paired comparisons versus Schiff.
- Show model diagnostics and run health.
- Show feature sets and candidate inventory.
- Use the capital programme optimiser Streamlit dashboard as visual base where possible.
- Replace old backend logic with model-search result backend.
- Produce a clean, professional, reusable dashboard for model governance and management review.

## Stage 1 Framing

- Dashboard copy must explain Stage 1 actual-driver testing.
- Stage 1 asks: if future explanatory variables were known, which model maps those drivers to target volume best?
- Dashboard must make clear this is not the vintage macro/fuel input forecast-error layer.
- Use plain-language terms and tooltips for Stage 1 actual-driver test, rolling-origin forecast, held-out forecast, MAPE, annual MAPE, bias, P90 APE, Schiff benchmark, GBM, shallow GBM, differenced features, target lags, sliding window, expanding window, solver ensemble, and prequential ensemble.

## Data Loading

- Ask the user to select or enter a model-run folder.
- Support browsing/selecting a run subfolder from a parent folder if practical.
- Ignore live folder `run_20260519_150434`.
- Prefer common output files:
  - `recommended_finalists.csv`
  - `final_summary.csv`
  - `quarterly_predictions.csv`
  - `annual_predictions.csv`
  - `quarterly_summary.csv`
  - `annual_summary.csv`
  - `paired_vs_schiff.csv`
  - `stress_tests.csv`
  - `ensemble_weights.csv`
  - `feature_audit_log_real_only.csv`
  - `variant_feature_counts.csv`
  - `leaderboards.csv`
  - `errors.csv`
  - `autogluon_final_robust_all_streams_results.xlsx`
  - `autogluon_final_robust_report.md`
  - `stage1_bespoke_solver_results.xlsx`
  - `stage1_bespoke_solver_report.md`
- Support older/alternative file names:
  - `all_model_summary.csv` as `final_summary.csv`
  - `all_quarterly_predictions.csv` as `quarterly_predictions.csv`
  - `all_annual_predictions.csv` as `annual_predictions.csv`
  - `top50_by_stream.csv`
  - `top100_candidates.csv`
  - `paired_finalist_vs_schiff.csv`
  - `finalist_stress_tests.csv`
- Missing files must not crash the app.
- Empty files must not crash the app.
- Display file-read status: file, found, rows, columns, size, last modified.
- Use available columns only.
- Map flexible prediction columns such as `origin`/`forecast_origin`, `actual`/`target`, and `pred`/`prediction`.

## Metrics

- Compute percentage error: `100 * (pred - actual) / actual`.
- Compute absolute percentage error.
- Compute MAPE.
- Compute bias.
- Compute P90 APE.
- Compute horizon buckets: 1-4, 5-8, 9-12 quarters.
- Compute June year for annual aggregation where needed.
- Normalize stream labels to PED VKT per capita, Light RUC volume, and Heavy RUC volume.
- Keep stream colours consistent.

## Page 1 Executive Summary

- Show metric cards:
  - number of streams;
  - recommended finalist count;
  - best PED quarterly MAPE;
  - best Light RUC quarterly MAPE;
  - best Heavy RUC quarterly MAPE;
  - number of candidate models;
  - number of quarterly prediction rows;
  - errors logged.
- Show finalist forecast accuracy grouped bar chart by stream with quarterly MAPE and annual MAPE.
- Use blue/orange bars and data labels.
- Tooltip should include model name, source family, and variant.
- Automatically update current-result claims from selected run data.

## Page 2 Candidate Landscape

- Show scatter plot with quarterly MAPE on x-axis and annual MAPE on y-axis.
- Colour by stream.
- Mark candidate models as normal points.
- Mark selected finalists as stars.
- Mark Schiff benchmarks as triangles.
- Hover fields must include stream, stage, variant, source family, model, quarterly MAPE, annual MAPE, bias, and governance score where available.
- Filters must include stage, stream, source family, variant, Schiff-only, finalists-only, all.
- Show whether finalists sit near the efficient frontier and whether Schiff was beaten.

## Page 3 Schiff Benchmark Comparison

- Use `paired_vs_schiff.csv`.
- Show table columns: stream, stage, baseline, challenger, baseline MAPE, challenger MAPE, gain, win rate, common pairs.
- Show horizontal bar chart of MAPE improvement by challenger.
- Show scatter plot of baseline MAPE vs challenger MAPE.
- Show stream-level summary: best challenger gain vs Schiff, best challenger win rate, whether challenger MAPE is lower than Schiff.
- Add badges:
  - Gain > 0 and win rate > 55%: Beats Schiff.
  - Gain > 0 and win rate <= 55%: Average gain, mixed wins.
  - Gain <= 0: Does not beat Schiff.

## Page 4 Ensemble Composition

- Use `ensemble_weights.csv` and `recommended_finalists.csv`.
- Show finalist ensemble composition.
- Static ensembles: horizontal bar chart of component model weights with percentages.
- Median/top-k ensembles: show membership or equal membership if no weights are available.
- Prequential ensembles: show average weight by component across origins and optional line chart over origin.
- Shorten long component names to C1, C2, C3, with expandable mapping table.

## Page 5 Forecasts and Errors

- Use `quarterly_predictions.csv`.
- Controls: stream, stage, model, origin, horizon bucket.
- Show actual vs predicted time series for selected model and stream.
- Show forecast error over time.
- Show absolute percentage error distribution by horizon bucket.
- Box plot should reproduce the report style for forecast errors by horizon bucket.

## Page 6 Stress and Horizon Checks

- Use `stress_tests.csv` or reconstruct from predictions.
- Show buckets: 1-4 qtrs, 5-8 qtrs, 9-12 qtrs, 2024+, 2022-23, annual.
- Show line chart with stress bucket on x-axis, MAPE on y-axis, stream lines, and markers.
- Add commentary: Light RUC expected to be weak in the 2022-23 policy window due to RUC discount and purchase timing; PED and Heavy RUC should generally be more stable if candidate selection worked.

## Page 7 Model Inventory

- Use `final_summary.csv`, `quarterly_summary.csv`, `annual_summary.csv`, and `leaderboards.csv`.
- Table filters: stream, stage, source family, variant, model contains text, top N by quarterly MAPE, top N by annual MAPE.
- Include columns: stage, stream, variant, source_family, model, quarterly_mape, annual_mape, quarterly_bias_pct, annual_bias_pct, quarterly_p90_ape, governance_score, n_quarterly_pairs, n_annual_pairs.
- Allow CSV download of filtered table.

## Page 8 Feature and Run Audit

- Use `feature_audit_log_real_only.csv`, `variant_feature_counts.csv`, and `errors.csv`.
- Show feature count by stream and variant.
- Show feature audit table.
- Show errors table.
- Show error flags: HyperOpt missing, Ray errors, permission errors, neural-model errors, empty files.
- If `errors.csv` is non-empty, show warning and explain scripts may log and skip failed candidates rather than stop the run.

## Chart and Styling Requirements

- Use Plotly for interactive charts.
- Implement chart functions for finalist accuracy, candidate landscape, Schiff benchmark, paired-vs-Schiff, ensemble composition, actual vs predicted, error distribution, and stress checks.
- Keep stream colours consistent.
- Use professional white-background report style.
- Avoid weak, blank, placeholder, or yuck table-first pages.
- Long model names must be readable or safely shortened.

## Testing and Delivery

- Create a working Streamlit app.
- Refactor backend data loader.
- Add Plotly charts matching PDF report style.
- Add README with run instructions.
- Add tests for data loader, metrics, Streamlit smoke, and Playwright dashboard.
- Run compile, pytest, Streamlit, and browser checks.
- Use browser automation to click all pages, check charts/tables, check console/network errors, and save screenshots.

## Management Questions

The dashboard must help answer:

- Which model won for PED, Light RUC and Heavy RUC?
- Did it beat the Schiff structural benchmark?
- Was the win robust across quarterly, annual, horizon and stress-period checks?
- What models or ensemble components drive the result?
- Are there warnings in run logs or errors?
- Is Light RUC still the weak stream?
