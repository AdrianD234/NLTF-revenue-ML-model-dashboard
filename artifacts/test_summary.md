# Test Summary

Status: **passed** for the Parquet-backed Stage 1 Model Governance Dashboard visual conformance sprint.

Retained latest arbitration smoke run: `run_20260520_002339`.

## Data Root Used For Latest Verification

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack`

The requested diagnostic audit pack contains the diagnostic workbook, report, tables, and figures. The curated candidate Parquet is resolved by the loader from the adjacent information pack.

Resolved primary Parquet:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet`

## Current Verification

| Check | Result |
|---|---|
| Compile | Passed |
| Schema inspection | Passed |
| Data validation | Passed |
| Chart-data reconciliation tests | 14 passed |
| Per-chart source-table tests | 6 passed |
| Full pytest | 150 passed, 5 skipped, 38 deselected |
| Chart source validation | 16 source tables passed |
| Semantic label validation | Passed |
| Visual conformance validation | Passed |
| Existing browser e2e | 37 passed |
| Mandatory frontend interaction browser tests | 5 passed |
| Streamlit session-state/default warning gate | Passed; no duplicate widget-default warning found in Streamlit logs |
| Branding/header update | Passed; browser verified `NTLF Revenue Modelling` and the NZ Transport Agency Waka Kotahi logo asset |
| Compact filter evidence line removal | Passed; browser verified `.run-evidence-compact`, `Run evidence:`, and `Curated rows:` are not visible |
| 100-gate validation | 100 passed, 0 failed, 0 supporting failures |
| 120-gate validation | 120 passed, 0 failed |
| `scripts/verify_dashboard.ps1` | Passed on port 8501 |
| `scripts/run_recursive_dashboard_validation.ps1` | Passed on pass 1 of 1 with the updated 120-gate harness |
| Focused post-pass regression loop | 20/20 passed |
| Backlog | No unchecked items |

## Finalist Reconciliation

- PED VKT per capita: 2.47 percent quarterly MAPE and 2.39 percent annual MAPE.
- Light RUC volume: 9.15 percent quarterly MAPE and 6.00 percent annual MAPE.
- Heavy RUC volume: 3.48 percent quarterly MAPE and 3.02 percent annual MAPE from the current recommended Parquet flag.
- Stale current-finalist values 5.49 percent, 11.55 percent, and 12.38 percent are rejected by data validation and browser tests.

## Browser Evidence

- Streamlit URL tested: `http://localhost:8501`.
- Final screenshots from existing browser e2e: `final-01-overview.png`, `final-02-diagnostics.png`, `final-03-scenario-comparison.png`, and `final-04-schiff-benchmark.png`.
- Final screenshots from mandatory frontend interaction tests: `final-overview.png`, `final-diagnostics.png`, `final-scenario-comparison.png`, and `final-schiff-benchmark.png`.
- The masthead displays `NTLF Revenue Modelling` with the actual NZ Transport Agency Waka Kotahi logo asset.
- The compact text line formerly showing stream/model/stage/run evidence/curated row details is removed from the visible dashboard.
- Direct filter tests clicked Stream, Model Family, Stage, Baseline, Horizon, Forecast Vintage, and Date Window.
- Stream and Horizon filters were changed to non-default values; active chips and visible content updated; Reset Filters restored defaults.
- Plotly hover text was inspected on Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark and contained no raw dataframe labels or excessive decimals.
- Browser console/page-error/request-failure checks were clean during the mandatory frontend interaction suite.
- Streamlit logs were scanned for the `created with a default value but also had its value set via the Session State API` warning after browser verification; no warning was found.
- Overview Stress and Horizon Checks was browser-verified from rendered Plotly trace data: PED and Light RUC carry non-null 1-4, 5-8 and 9-12 quarter buckets, while Heavy RUC 2024+ and 2022-23 remain explicit missing points with `connectgaps=False`.
- Schiff Benchmark browser DOM verifies the gain chart is titled Full-sample Gain vs Schiff, not Paired Gain vs Schiff.
- A focused 20-pass regression loop reran chart-source validation, semantic-label validation, visual conformance validation, and `tests/test_playwright_frontend_interactions.py` against `http://localhost:8501`; all 20 passes succeeded.

## Chart Data Reconciliation Evidence

- Ensemble Composition now reads current finalist `ensemble_components_json` from the Parquet and exports both `artifacts/ensemble_composition_source_table.csv` and `artifacts/chart_sources/overview_ensemble_composition.csv`.
- Scenario Comparison exports `artifacts/scenario_comparison_source_table.csv` with full-sample gains and paired common-grid win-rate/gain evidence; Light RUC paired gain is recorded as negative.
- Scenario and Schiff horizon charts export `artifacts/horizon_comparison_source_table.csv`.
- Diagnostics ACF exports `artifacts/diagnostic_acf_source_table.csv` with residual source and calculation method.
- All 16 primary charts export source tables under `artifacts/chart_sources/` with page, chart id, metric, display value, source column, source file, calculation basis and notes.
- The R2 KPI is labelled Mean calibration R2, Residual vs Fitted uses native-unit axis labels, Diagnostic Overall can be Watch when normality is the only concern, and the candidate count KPI is labelled Plotted candidates.

## Final Commands Run

```powershell
pwsh -File scripts\verify_dashboard.ps1 -Python ".venv\Scripts\python.exe" -DataRoot "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack" -Port 8501
pwsh -File scripts\run_recursive_dashboard_validation.ps1 -MaxPasses 1 -Python ".venv\Scripts\python.exe" -DataRoot "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack" -VerifierPort 8501
```

Focused 20-pass regression loop:

```powershell
for each pass 1..20:
  .venv\Scripts\python.exe scripts\validate_chart_sources.py --data-root "<diagnostic audit pack>"
  .venv\Scripts\python.exe scripts\validate_semantic_labels.py --data-root "<diagnostic audit pack>"
  .venv\Scripts\python.exe scripts\validate_visual_conformance.py
  .venv\Scripts\python.exe -m pytest -q tests\test_playwright_frontend_interactions.py
```
