# BUG_BACKLOG.md

Backlog state for the Stage 1 Model Governance Dashboard Parquet refresh and visual conformance sprint.

## Closed Visual Conformance Sprint Items

- [x] Close Overview visual defects listed in `PAGE_BY_PAGE_VISUAL_DELTA.lock.md`.
- [x] Close Diagnostics visual defects listed in `PAGE_BY_PAGE_VISUAL_DELTA.lock.md`.
- [x] Close Scenario Comparison visual defects listed in `PAGE_BY_PAGE_VISUAL_DELTA.lock.md`.
- [x] Close Schiff Benchmark visual defects listed in `PAGE_BY_PAGE_VISUAL_DELTA.lock.md`.
- [x] Extend validation from 80 gates to 100 gates with visual conformance gates 81-100.
- [x] Regenerate after-screenshots and mark visual reviewer artifacts PASS.
- [x] Add hard Playwright/frontend interaction gate to `scripts/verify_dashboard.ps1`.
- [x] Create `tests/test_playwright_frontend_interactions.py` and verify tabs, filters, reset, hovers, console errors, stale values, and screenshots in a real browser.

## Closed Parquet Refresh Sprint Items

- [x] Replaced the placeholder circular logo with the actual NZ Transport Agency Waka Kotahi logo asset.
- [x] Changed the dashboard masthead title to `NTLF Revenue Modelling`.
- [x] Removed the compact filter/run-evidence text line beneath the primary filters and added a browser regression to prevent it returning.
- [x] Located `stage1_curated_candidate_cone.parquet` in the information pack and made it the primary dashboard data source.
- [x] Located `stage1_curated_candidate_cone_metadata.json` and recorded it in schema artifacts.
- [x] Located the CSV mirror and recorded it as secondary audit evidence.
- [x] Added robust aliases for the information pack schema, including frontier, distribution sample, paired gain, stress, and diagnostic fields.
- [x] Reconciled current finalists to the Parquet flags and values.
- [x] Verified stale old finalist values are absent from current finalist metrics.
- [x] Rebuilt the four primary pages around Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark.
- [x] Verified the Candidate Search Frontier uses curated cone rows, frontier rows, finalist markers and pure Schiff markers.
- [x] Verified pure Schiff rows exclude residual, blend, solver and ensemble challengers.
- [x] Fixed derived stress rows so the Overview stress chart renders from Parquet finalist stress fields.
- [x] Fixed stress and horizon alias coalescing so PED, Light RUC and Heavy RUC all read their Parquet bucket fields and Heavy RUC policy-stress gaps do not connect visually.
- [x] Added the Scenario and Schiff horizon scenario field required by validation.
- [x] Regenerated four final page screenshots from the Parquet backed app.
- [x] Regenerated hover screenshots and verified clean hover text.
- [x] Verified direct primary filters, active chip update, visible data update after a filter change, and Reset Filters.
- [x] Fixed Streamlit duplicate widget-default warning for `advanced_top_n` and related advanced toggles by using session state as the single source of widget defaults.
- [x] Added a hard verifier gate that fails if Streamlit logs the session-state/default-value warning during browser verification.
- [x] Regenerated schema, validation, screenshot, hover, filter, visual and performance artifacts.
- [x] Ran the full existing browser e2e suite with 37 passing tests.
- [x] Ran the mandatory frontend interaction Playwright suite with 5 passing tests.

## Closed Chart Data Reconciliation Items

- [x] Rebuilt Finalist Ensemble Composition from Parquet `ensemble_components_json` and blocked stale/demo component weights.
- [x] Added `artifacts/ensemble_composition_source_table.csv` as the auditable source for ensemble chart weights.
- [x] Renamed full-sample gain charts so they no longer misuse paired-gain terminology.
- [x] Clarified Scenario Comparison table labels as full-sample gains plus paired common-grid win rate.
- [x] Added `artifacts/scenario_comparison_source_table.csv` with full-sample and paired common-grid evidence.
- [x] Added `artifacts/horizon_comparison_source_table.csv` for Scenario and Schiff horizon charts.
- [x] Added `artifacts/diagnostic_acf_source_table.csv` with residual source and calculation method.
- [x] Renamed the R2 KPI to Mean calibration R2 because the source field is Mincer-Zarnowitz/calibration R2.
- [x] Relabelled Residual vs Fitted x-axes as native units to avoid misleading PED scaling.
- [x] Changed Diagnostic Overall to Watch when normality is the only caution/fail condition.
- [x] Renamed the candidate count KPI to Plotted candidates for default curated cone rows.

## Closed Chart Source Audit Items

- [x] Added per-chart source tables for all 16 primary dashboard charts under `artifacts/chart_sources/`.
- [x] Added `scripts/validate_chart_sources.py` and `tests/test_chart_source_tables.py`.
- [x] Added `scripts/validate_semantic_labels.py` to fail stale/ambiguous labels such as Candidate Models, Mean Adjusted R2 and Paired Gain vs Schiff.
- [x] Added `scripts/validate_visual_conformance.py` and `scripts/validate_120_gates.py` for the source-table and semantic extension gates.
- [x] Extended `scripts/verify_dashboard.ps1` and `scripts/run_recursive_dashboard_validation.ps1` so the dashboard cannot pass without chart-source, semantic, visual and Playwright checks.
- [x] Added browser trace validation that compares rendered Plotly stress chart data back to `overview_stress_horizon_checks.csv`.

## Closed Repo Cleanup Sprint Items

- [x] Moved Parquet schema aliases and candidate normalization from `model_dashboard/data_loader.py` to `model_dashboard/data/transforms.py`.
- [x] Moved diagnostic audit loading, diagnostic frame construction and ACF source-table construction to `model_dashboard/data/diagnostics.py`.
- [x] Updated schema/data/gate validation scripts to import governed data config, locator, and transform modules directly.
- [x] Removed whole-repo recursive lookup from default data discovery so generated `artifacts/` cannot be used as dashboard input.
- [x] Added a regression test proving generated artifacts are ignored by governed file discovery.
- [x] Tightened verifier compile scope to `app.py`, `model_dashboard`, and `scripts`.
- [x] Ran `scripts/verify_dashboard.ps1` against `tests/fixtures/mini_parquet`; the sequential verifier passed through Playwright and 120 gates.
- [x] Moved governed Parquet dashboard orchestration from `model_dashboard/data_loader.py` to `model_dashboard/data/parquet_loader.py`.
- [x] Added a regression test proving Parquet load, finalist, Schiff, stress, horizon and ensemble frame orchestration definitions no longer live in `data_loader.py`.
- [x] Updated the 80/120 gate cache evidence to inspect `model_dashboard/data/parquet_loader.py`.
- [x] Re-ran `scripts/verify_dashboard.ps1` against `tests/fixtures/mini_parquet`; the sequential verifier passed through Playwright and 120 gates after the Parquet loader split.
- [x] Moved legacy run-folder and curated CSV/XLSX review loading from `model_dashboard/data_loader.py` to `model_dashboard/data/legacy_loader.py`.
- [x] Reduced `model_dashboard/data_loader.py` to a compatibility facade for current import sites.
- [x] Added a regression test proving legacy review loading definitions no longer live in `data_loader.py`.
- [x] Re-ran `scripts/verify_dashboard.ps1` against `tests/fixtures/mini_parquet`; the sequential verifier passed through Playwright and 120 gates after the legacy loader split.
- [x] Moved chart source-table implementation from top-level `model_dashboard/chart_sources.py` to `model_dashboard/data/chart_sources.py`.
- [x] Reduced top-level `model_dashboard/chart_sources.py` to a compatibility facade for current import sites.
- [x] Added a regression test proving chart-source builder definitions live in the data package.
- [x] Tightened explicit external-root discovery so the mini fixture is not mixed into the active diagnostic audit pack.
- [x] Added focused regression coverage for fixture fallback isolation.

## Closed External Pack Reconciliation Items

- [x] Derived diagnostic ACF source rows from aggregate H1 residual diagnostics when selected quarterly prediction rows are absent from the active audit pack.
- [x] Documented missing Scenario/Schiff horizon source rows for streams without real 1-12 horizon evidence under the active audit pack.
- [x] Updated feature-completeness tests to accept explicit missing-data states for absent selected prediction CSVs while continuing to fail fixture mixing or invented values.
- [x] Re-ran focused external-pack chart reconciliation tests: 26 passed.
- [x] Re-ran `scripts/validate_chart_sources.py` against the active external diagnostic audit pack; all 16 chart source checks passed.
- [x] Re-ran `scripts/validate_semantic_labels.py`; semantic label validation passed.
- [x] Re-ran `scripts/verify_dashboard.ps1` against the active external diagnostic audit pack; the full verifier passed through Playwright, visual conformance, 100 gates and 120 gates.
- [x] Removed active-run expected component/finalist constants from verifier scripts; source-table checks now compare against active `DashboardData`.
- [x] Moved active expected numeric values used by tests into `tests/fixtures/expected_values.py`.

## Closed Page 5 Governance & Reproducibility Items

- [x] Rebuilt Page 5 as a read-only governance dashboard page with Waka Kotahi / NZTA card styling.
- [x] Added Page 5 filter strip, segmented stream selector, reproducibility pack selector, workbook provenance, read-only status, reset button, and downloads dropdown.
- [x] Added four top status cards for packs loaded, workbook provenance, chart-source isolation, and audit-only page role.
- [x] Added stream replay cards for PED, Light RUC, and Heavy RUC with required wording and replay deltas.
- [x] Replaced table-like build flow with visual process cards.
- [x] Replaced glossary table presentation with glossary chips/cards.
- [x] Added registry and diagrammatic component trace panels from replay-pack Parquet.
- [x] Added feature importance, coefficients, scenario sensitivities, training-window trace, downloads, SHAP unavailable note, and read-only footer.
- [x] Added Page 5 visual spec, visual delta backlog, screenshot review, and target/current matrix artifacts.
- [x] Extended visual conformance validation and 120-gate matrix checks to include Page 5.

## Closure Evidence

- Schema inspection passed for the information pack Parquet reached from the requested diagnostic audit pack workflow.
- Data validation passed for the Parquet-backed candidate data and diagnostic pack.
- Browser e2e verification passed with 37 existing tests.
- Mandatory frontend interaction verification passed with 5 tests.
- Chart source validation passed for 16 primary chart source tables.
- 120-gate extension validation passed with 20 added source/semantic gates.
- Fresh after-screenshots exist for Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark from the latest active external-pack verifier path.
- Performance benchmark measured warm cached Parquet load at under 0.01 seconds.

## Closed Forecast Runner Governance Items

- [x] Added a governed variable-horizon forecast input template specification with a default 20-quarter committed template.
- [x] Added a forecast runner specification that keeps forecast-run artifacts separate from the historical evidence pack.
- [x] Added runtime manifest fields for fixed-finalist-only execution, no broad search, workbook hash, scenario name, horizon metadata, and no evidence/chart-source mutation.
- [x] Documented current forward status: Light RUC numeric fixed-finalist forecasts, PED governed gap, and Heavy RUC governed gap.
- [x] Added a forecast scenario comparison specification for multi-upload combined tables, charts, capability rows, and downloads.
- [x] Kept runtime model-state gaps in `forecast_run_manifest.json`, `forecast_capability_report.*`, and `forecast_validation_report.md` rather than adding unchecked dashboard backlog defects.

No unchecked backlog items remain.
