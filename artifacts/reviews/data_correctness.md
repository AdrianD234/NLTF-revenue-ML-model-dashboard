# Data Correctness Review

Status: PASS

Generated: 2026-06-24T20:09:55.269983+00:00
Commit reviewed: `e3a9fea`

Evidence reviewed:

- `artifacts/data_validation_review.md`: current finalist MAPE, Schiff benchmark reconciliation, stress/horizon semantics, and stale-finalist exclusion are marked passed.
- `artifacts/chart_source_validation_report.md`: chart sources, R2 ladder sources, scenario sources, and reproducibility component R2 sources are marked passed.
- `data/revenue_model_source_pack/2026_05_19/loader_exports_manifest.json`: loader exports are hash-backed and deterministic for the source-pack manifest timestamp.

Findings:

- Current dashboard metrics reconcile to the governed Parquet evidence pack.
- Revenue source-pack canonical rows include source file/cell, raw workbook SHA, distilled workbook SHA, and normalized source CSV SHA.
- Unavailable PED bridge, release-value, FED-path, and Crown top-up inputs are represented as explicit gaps rather than zero-filled values.

Residual risk:

- This review relies on current validation reports; rerun `scripts/verify_dashboard.ps1` once local Playwright startup is repaired.

Source snippets checked:

```text
# Data Validation Review

Status: **passed**.

Default dashboard validation is evidence-pack only; legacy run folders and fixtures are review-only.

- [pass] Evidence pack resolved: `data\dashboard_evidence_pack`.
- [pass] Slim evidence pack contains only root metadata, docs, and data/*.parquet files under 50 MB.
- [pass] Required Parquet files present: 14.
- [pass] Current finalist quarterly and annual MAPE reconcile to the evidence pack.
- [pass] Schiff specification benchmark quarterly and annual MAPE reconcile to the evidence pack.
- [pass] Candidate frontier default rows: 400.
- [pass] Full-sample gain and paired win-rate semantics are separated; Light RUC operational annual watch remains visible.
- [pass] Stress/horizon rows preserve source policy windows, while Overview default shows horizon buckets only.
- [pass] Diagnostic ACF residual scope is documented.
- [pass] Stale old finalist values are absent from current finalists.

# Chart Source Validation Report

Status: **passed**.

| Check | Status | Evidence |
| --- | --- | --- |
| overview_finalist_forecast_accuracy.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| overview_candidate_search_frontier.csv exists and has required columns | PASS | rows=400; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| overview_ensemble_composition.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| overview_stress_horizon_checks.csv exists and has required columns | PASS | rows=12; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| diagnostics_residual_autocorrelation.csv exists and has required columns | PASS | rows=36; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| diagnostics_residual_vs_fitted.csv exists and has required columns | PASS | rows=740; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| diagnostics_pass_matrix.csv exists and has required columns | PASS | rows=27; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| diagnostics_error_distribution_by_horizon.csv exists and has required columns | PASS | rows=756; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| diagnostics_r2_summary.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| r2_ladder_summary.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| r2_training_fit_detail.csv exists and has required columns | PASS | rows=30; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| r2_reproducibility_gap_register.csv exists and has required columns | PASS | rows=2; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| scenario_stream_comparison.csv exists and has required columns | PASS | rows=12; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| scenario_improvement_vs_benchmark.csv exists and has required columns | PASS | rows=6; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| scenario_horizon_comparison.csv exists and has required columns | PASS | rows=72; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| scenario_decision_summary.csv exists and has required columns | PASS | rows=9; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
| schiff_vs_finalist_mape.csv exists and has required columns | PASS | rows=12; missing=[]; page_ok=True; chart_id_ok=True; score_basis_ok=True |
```

Loader manifest present: yes
