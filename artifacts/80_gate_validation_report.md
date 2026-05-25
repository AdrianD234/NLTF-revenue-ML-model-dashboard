# 100 Gate Validation Report

Status: **PASS**.
Generated: 2026-05-25T12:28:40
Passed gates: 100/100
Failed gates: 0/100
Failed supporting checks: 0

## Data Sources

- Data root: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack`
- Parquet path: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet`
- Metadata path: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone_metadata.json`
- CSV mirror path: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.csv`

## Gate Results

| Gate | Status | Evidence |
| --- | --- | --- |
| 1. Parquet file is found recursively under the supplied data root. | PASS | Resolved Parquet path: C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet |
| 2. Parquet file loads without error. | PASS | Parquet loaded with shape (300, 153). |
| 3. Parquet row count is greater than zero. | PASS | 300 candidate rows loaded. |
| 4. Parquet contains all three streams. | PASS | All three streams present. |
| 5. Stream labels are human-readable. | PASS | stream_label values are human-readable. |
| 6. Model labels are human-readable or have short labels. | PASS | model_short values are available for display. |
| 7. No user-facing label contains raw underscores. | PASS | User-facing label columns are clean. |
| 8. Metadata JSON is found or gracefully marked missing. | PASS | Metadata JSON found: C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone_metadata.json |
| 9. CSV mirror is found or gracefully marked missing. | PASS | CSV mirror found: C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.csv |
| 10. Data schema report is written to artifacts/data_schema_report.md. | PASS | artifacts/data_schema_report.md exists. |
| 11. Exactly one current recommended finalist exists for PED, or ambiguity is explicitly warned. | PASS | Exactly one current recommended finalist for PED. |
| 12. Exactly one current recommended finalist exists for Light RUC, or ambiguity is explicitly warned. | PASS | Exactly one current recommended finalist for LIGHT_RUC. |
| 13. Exactly one current recommended finalist exists for Heavy RUC, or ambiguity is explicitly warned. | PASS | Exactly one current recommended finalist for HEAVY_RUC. |
| 14. PED current finalist quarterly MAPE rounds to approximately 2.47%. | PASS | PED quarterly_mape is 2.47%, matching expected 2.47%. |
| 15. PED current finalist annual MAPE rounds to approximately 2.39%. | PASS | PED annual_mape is 2.39%, matching expected 2.39%. |
| 16. Light RUC current finalist quarterly MAPE rounds to approximately 9.15%. | PASS | LIGHT_RUC quarterly_mape is 9.15%, matching expected 9.15%. |
| 17. Light RUC current finalist annual MAPE rounds to approximately 6.00%. | PASS | LIGHT_RUC annual_mape is 6.00%, matching expected 6.00%. |
| 18. Heavy RUC current finalist quarterly MAPE is taken from the Parquet current-recommended flag. | PASS | Heavy RUC quarterly_mape comes from 1 current-recommended Parquet row(s): [3.484367565681976]. |
| 19. Heavy RUC current finalist annual MAPE is taken from the Parquet current-recommended flag. | PASS | Heavy RUC annual_mape comes from 1 current-recommended Parquet row(s): [3.0199801790589795]. |
| 20. Stale old finalist values do not appear as current latest finalist values. | PASS | Known stale finalist values are absent from current finalists. |
| 21. Candidate landscape uses the Parquet candidate rows. | PASS | Candidate rows loaded from Parquet: C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet |
| 22. Default candidate landscape does not use the full raw universe if row count is large. | PASS | Default landscape uses 287 rows from 300 total. |
| 23. Default candidate landscape uses curated rows where plot_default_include is true, or equivalent. | PASS | 287 plot_default_include rows form the default landscape. |
| 24. Candidate landscape contains distribution/cone sample rows. | PASS | 300 distribution/cone sample rows found. |
| 25. Candidate landscape contains top quarterly candidates. | PASS | 6 top quarterly rows found. |
| 26. Candidate landscape contains top annual candidates. | PASS | 10 top annual rows found. |
| 27. Candidate landscape contains frontier/Pareto candidates where available. | PASS | 2 frontier/Pareto rows found. |
| 28. Candidate landscape contains current finalist markers. | PASS | 3 current finalist marker rows found. |
| 29. Candidate landscape contains pure Schiff markers. | PASS | 5 pure Schiff marker rows found. |
| 30. Candidate landscape row count is capped at or below 400 for default rendering. | PASS | Default landscape has 287 rows, within cap 400. |
| 31. Pure Schiff rows exist for all three streams. | PASS | Pure Schiff rows exist for all three streams. |
| 32. Pure Schiff rows exclude residual models. | PASS | Pure Schiff rows exclude residual models. |
| 33. Pure Schiff rows exclude fixed-blend models. | PASS | Pure Schiff rows exclude fixed-blend models. |
| 34. Pure Schiff rows exclude solver models. | PASS | Pure Schiff rows exclude solver models. |
| 35. Pure Schiff rows exclude top-k mean/median ensembles. | PASS | Pure Schiff rows exclude top-k mean/median ensembles. |
| 36. Schiff Benchmark page uses pure Schiff rows only. | PASS | Pure Schiff benchmark rows are not contaminated. |
| 37. Scenario Comparison joins current finalists to pure Schiff rows by stream. | PASS | Current finalists join to pure Schiff rows for all streams. |
| 38. Paired gain versus Schiff is computed or loaded where available. | PASS | Paired gain is loaded from Parquet columns. |
| 39. Win rate versus Schiff is shown where available. | PASS | Win-rate field is available. |
| 40. Benchmark summary does not classify residual/blend challengers as pure Schiff. | PASS | Pure Schiff benchmark rows are not contaminated. |
| 41. Overview page renders without Streamlit exception. | PASS | Parquet schema passed and screenshot exists: artifacts/screenshots/final-01-overview.png |
| 42. Overview KPI cards reconcile to Parquet values. | PASS | Overview KPI means derived from Parquet finalists: quarterly=5.04, annual=3.80. |
| 43. Overview finalist accuracy chart uses current finalists. | PASS | Finalist accuracy has 3 current finalist rows. |
| 44. Overview candidate search frontier uses curated cone sample. | PASS | 287 plot_default_include rows form the default landscape. |
| 45. Overview ensemble composition uses real weights where available or shows a clear missing-data state. | PASS | Parquet ensemble component data available: 8 rows. |
| 46. Overview stress/horizon chart uses finalist stress/horizon fields. | PASS | Stress/horizon aliases coalesced into six-bucket rows: 18. |
| 47. Overview has no more than four main chart panels. | PASS | Overview four-panel rule is locked in DASHBOARD_PAGE_CHART_SPEC.lock.md. |
| 48. Overview screenshot is saved. | PASS | artifacts/screenshots/final-01-overview.png |
| 49. Overview screenshot has no obvious blank panels. | PASS | Parquet schema passed and screenshot exists: artifacts/screenshots/final-01-overview.png |
| 50. Overview screenshot visually aligns with the supplied target image. | PASS | Overview screenshot, visual reviewer PASS, and closed backlog evidence are present. |
| 51. Diagnostics page renders without Streamlit exception. | PASS | Parquet schema passed and screenshot exists: artifacts/screenshots/final-02-diagnostics.png |
| 52. Diagnostics KPI cards use available diagnostic fields or show clear missing-data states. | PASS | Diagnostic KPI source rows available: 8. |
| 53. Durbin-Watson metric is shown where available. | PASS | Durbin-Watson has available values. |
| 54. Calibration R2 metric is shown where available. | PASS | Calibration R2 has available values. |
| 55. Heteroscedasticity pass metric is shown where available. | PASS | Breusch-Pagan has available values. |
| 56. Residual autocorrelation chart renders where ACF data or residuals exist. | PASS | Residual autocorrelation code path is present. |
| 57. Residual vs fitted chart renders where selected predictions exist. | PASS | Residual vs fitted code path is present. |
| 58. Diagnostic pass matrix renders with required checks or graceful missing states. | PASS | Diagnostic pass matrix code path is present. |
| 59. Error distribution by horizon renders where prediction/error rows exist. | PASS | Error distribution by horizon code path is present. |
| 60. Diagnostics screenshot is saved and visually aligns with supplied target. | PASS | Diagnostics screenshot, visual reviewer PASS, and closed backlog evidence are present. |
| 61. Scenario Comparison page renders without Streamlit exception. | PASS | Parquet schema passed and screenshot exists: artifacts/screenshots/final-03-scenario-comparison.png |
| 62. Scenario A defaults to current refined finalist. | PASS | Current finalist rows exist for Scenario A. |
| 63. Scenario B defaults to pure Schiff structural benchmark. | PASS | Pure Schiff rows exist for Scenario B. |
| 64. Scenario controls render and are not fake static controls. | PASS | Scenario controls are implemented as Streamlit controls. |
| 65. Stream comparison chart uses finalist vs Schiff values. | PASS | Current finalists join to pure Schiff rows for all streams. |
| 66. Improvement-vs-benchmark chart computes gain correctly. | PASS | Quarterly gains computed for 5 stream rows. |
| 67. Horizon comparison chart uses finalist and Schiff horizon fields. | PASS | Scenario comparison horizon data rows: 24. |
| 68. Decision summary table labels full-sample gains and paired win rate clearly. | PASS | Decision summary labels are present in code. |
| 69. Scenario Comparison page has no more than four main chart/object panels. | PASS | Scenario Comparison four-panel rule is locked in DASHBOARD_PAGE_CHART_SPEC.lock.md. |
| 70. Scenario Comparison screenshot is saved and visually aligns with supplied target. | PASS | Scenario Comparison screenshot, visual reviewer PASS, and closed backlog evidence are present. |
| 71. Schiff Benchmark page renders without Streamlit exception. | PASS | Parquet schema passed and screenshot exists: artifacts/screenshots/final-04-schiff-benchmark.png |
| 72. Schiff KPI cards use pure Schiff and finalist rows correctly. | PASS | Schiff KPI sources: 5 Schiff rows and 3 finalist rows. |
| 73. Schiff vs Finalist MAPE chart renders. | PASS | Schiff vs Finalist MAPE code path is present. |
| 74. Benchmark Horizon Profiles render for all three streams where data exists. | PASS | Schiff benchmark horizon data rows: 24. |
| 75. Full-sample Gain vs Schiff chart does not misuse paired terminology. | PASS | Full-sample gain chart label is distinct from paired common-grid evidence. |
| 76. Benchmark Summary table renders with clean labels. | PASS | Benchmark table labels are clean and human-readable. |
| 77. Schiff Benchmark page has no more than four main chart/object panels. | PASS | Schiff Benchmark four-panel rule is locked in DASHBOARD_PAGE_CHART_SPEC.lock.md. |
| 78. Schiff Benchmark screenshot is saved and visually aligns with supplied target. | PASS | Schiff Benchmark screenshot, visual reviewer PASS, and closed backlog evidence are present. |
| 79. All primary filters are directly clickable in the browser without using only the More button. | PASS | Filter review records direct clickable primary filters. |
| 80. All major Plotly hovers are human-readable. | PASS | Hover review is present and contains no raw internal labels or underscores. |
| 81. Overview screenshot conforms to target card/panel structure. | PASS | Overview card/panel structure is locked and reviewer-approved. |
| 82. Overview stress bucket order is correct. | PASS | Overview stress bucket order is explicitly locked in labels and plot axis settings. |
| 83. Overview candidate frontier has no giant circle/ellipse overlays. | PASS | Candidate frontier has no circle/ellipse overlay code. |
| 84. Overview candidate frontier displays finalist and Schiff markers. | PASS | Candidate frontier exposes finalist stars and Schiff open triangles. |
| 85. Diagnostics matrix has styled pass/caution/fail cells. | PASS | Diagnostic matrix uses styled pass/caution/fail/unavailable cells. |
| 86. Diagnostics page shows R2, Durbin-Watson and heteroscedasticity KPIs. | PASS | Diagnostics KPI labels match target semantics. |
| 87. Diagnostics residual-vs-fitted chart solves scale imbalance. | PASS | Residual-vs-fitted uses stream facets and native-unit axis labelling. |
| 88. Scenario stream comparison labels do not overlap. | PASS | Scenario visual review confirms dumbbell labels no longer overlap. |
| 89. Scenario horizon comparison shows all three streams when Stream filter is All Streams. | PASS | Scenario Comparison horizon profile evidence covers all three streams. |
| 90. Scenario decision table is styled and not an unformatted basic table. | PASS | Scenario decision summary is rendered as a styled Plotly table. |
| 91. Schiff MAPE chart separates Quarterly and Annual clearly. | PASS | Schiff MAPE chart uses separated Quarterly and Annual sections. |
| 92. Schiff horizon profiles show all three streams when Stream filter is All Streams. | PASS | Schiff Benchmark horizon profile evidence covers all three streams. |
| 93. Schiff summary table is styled and readable. | PASS | Schiff benchmark summary is styled and readable. |
| 94. Visual reviewer report marks all four pages PASS. | PASS | All visual review artifacts explicitly mark all four pages PASS. |
| 95. Screenshot review confirms no major target/current visual gaps remain. | PASS | Screenshot review records no unresolved major visual gaps. |
| 96. Browser test verifies all four top-level pages after visual fixes. | PASS | Browser screenshot review covers all four top-level pages. |
| 97. Filter/dropdown tests still pass. | PASS | Filter review records direct clickable primary filters. |
| 98. Hover readability tests still pass. | PASS | Hover review is present and contains no raw internal labels or underscores. |
| 99. Performance smoke check still passes. | PASS | Performance smoke review is present without failure indicators. |
| 100. BUG_BACKLOG.md has no unchecked visual defects. | PASS | Visual backlog and bug backlog have no unchecked items. |

## Supporting Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Exactly 100 validation gates are defined | PASS | 100 gates defined; expected 100 |
| Reset Filters works | PASS | filter interaction review plus passed Parquet schema required |
| Active filter chips update after filter changes | PASS | filter interaction review must record active chip update |
| At least one chart/table/KPI updates after a non-default filter selection | PASS | browser review must record visible update after filter selection |
| Browser console has no critical errors | PASS | current browser console evidence required |
| Network requests have no unexplained failures | PASS | current browser network evidence required |
| App cold load and tab switching are not materially slow | PASS | performance review required after Parquet-backed run |
| The app does not parse Excel on every filter interaction | PASS | cache signature and st.cache_data evidence checked in code |
| The Parquet is cached using st.cache_data | PASS | app.py must cache Parquet load through st.cache_data |
| Full dense tables are behind expanders/downloads and not rendered by default | PASS | app.py expander/download evidence |
| Screenshots are regenerated after the final pass | PASS | all four final screenshots required after passed schema |
| BUG_BACKLOG.md has no unchecked items | PASS | BUG_BACKLOG.md checked for open task boxes |
