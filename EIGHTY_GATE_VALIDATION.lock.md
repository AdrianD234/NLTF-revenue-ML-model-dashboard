# Eighty Gate Validation Lock

This dashboard task is not complete unless all 80 gates below pass with direct evidence from code, tests, screenshots, browser checks, data validation, or artifact review.

A gate must not be marked PASS from visual impression alone. A gate may only pass when the validation script records the evidence source.

## A. Data source and Parquet integrity

1. Parquet file is found recursively under the supplied data root.
2. Parquet file loads without error.
3. Parquet row count is greater than zero.
4. Parquet contains all three streams.
5. Stream labels are human-readable.
6. Model labels are human-readable or have short labels.
7. No user-facing label contains raw underscores.
8. Metadata JSON is found or gracefully marked missing.
9. CSV mirror is found or gracefully marked missing.
10. Data schema report is written to artifacts/data_schema_report.md.

## B. Current finalist integrity

11. Exactly one current recommended finalist exists for PED, or ambiguity is explicitly warned.
12. Exactly one current recommended finalist exists for Light RUC, or ambiguity is explicitly warned.
13. Exactly one current recommended finalist exists for Heavy RUC, or ambiguity is explicitly warned.
14. PED current finalist quarterly MAPE rounds to approximately 2.47%.
15. PED current finalist annual MAPE rounds to approximately 2.39%.
16. Light RUC current finalist quarterly MAPE rounds to approximately 9.15%.
17. Light RUC current finalist annual MAPE rounds to approximately 6.00%.
18. Heavy RUC current finalist quarterly MAPE is taken from the Parquet current-recommended flag.
19. Heavy RUC current finalist annual MAPE is taken from the Parquet current-recommended flag.
20. Stale old finalist values such as 5.49%, 11.55% and 12.38% do not appear as current latest finalist values.

## C. Candidate landscape / cone frontier

21. Candidate landscape uses the Parquet candidate rows.
22. Default candidate landscape does not use the full raw universe if row count is large.
23. Default candidate landscape uses curated rows where `plot_default_include` is true, or equivalent.
24. Candidate landscape contains distribution/cone sample rows.
25. Candidate landscape contains top quarterly candidates.
26. Candidate landscape contains top annual candidates.
27. Candidate landscape contains frontier/Pareto candidates where available.
28. Candidate landscape contains current finalist markers.
29. Candidate landscape contains pure Schiff markers.
30. Candidate landscape row count is capped at or below 400 for default rendering.

## D. Pure Schiff and benchmark logic

31. Pure Schiff rows exist for all three streams.
32. Pure Schiff rows exclude residual models.
33. Pure Schiff rows exclude fixed-blend models.
34. Pure Schiff rows exclude solver models.
35. Pure Schiff rows exclude top-k mean/median ensembles.
36. Schiff Benchmark page uses pure Schiff rows only.
37. Scenario Comparison joins current finalists to pure Schiff rows by stream.
38. Paired gain versus Schiff is computed or loaded where available.
39. Win rate versus Schiff is shown where available.
40. Benchmark summary does not classify residual/blend challengers as pure Schiff.

## E. Overview page

41. Overview page renders without Streamlit exception.
42. Overview KPI cards reconcile to Parquet values.
43. Overview finalist accuracy chart uses current finalists.
44. Overview candidate search frontier uses curated cone sample.
45. Overview ensemble composition uses real weights where available or shows a clear missing-data state.
46. Overview stress/horizon chart uses finalist stress/horizon fields.
47. Overview has no more than four main chart panels.
48. Overview screenshot is saved.
49. Overview screenshot has no obvious blank panels.
50. Overview screenshot visually aligns with the supplied target image.

## F. Diagnostics page

51. Diagnostics page renders without Streamlit exception.
52. Diagnostics KPI cards use available diagnostic fields or show clear missing-data states.
53. Durbin-Watson metric is shown where available.
54. Calibration/MZ R2 metric is shown where available and is not labelled adjusted R2 unless an adjusted R2 source field is used.
55. Heteroscedasticity pass metric is shown where available.
56. Residual autocorrelation chart renders where ACF data or residuals exist.
57. Residual vs fitted chart renders where selected predictions exist.
58. Diagnostic pass matrix renders with R2, Durbin-Watson, ADF/KPSS, Breusch-Pagan, White/Jarque-Bera or graceful missing states.
59. Error distribution by horizon renders where prediction/error rows exist.
60. Diagnostics screenshot is saved and visually aligns with supplied target.

## G. Scenario Comparison page

61. Scenario Comparison page renders without Streamlit exception.
62. Scenario A defaults to current refined finalist.
63. Scenario B defaults to pure Schiff structural benchmark.
64. Scenario controls render and are not fake static controls.
65. Stream comparison chart uses finalist vs Schiff values.
66. Improvement-vs-benchmark chart computes gain correctly.
67. Horizon comparison chart uses finalist and Schiff horizon fields.
68. Decision summary table shows Stream, Full-sample Qtr Gain, Full-sample Annual Gain, Paired Win Rate and Recommendation.
69. Scenario Comparison page has no more than four main chart/object panels.
70. Scenario Comparison screenshot is saved and visually aligns with supplied target.

## H. Schiff Benchmark page

71. Schiff Benchmark page renders without Streamlit exception.
72. Schiff KPI cards use pure Schiff and finalist rows correctly.
73. Schiff vs Finalist MAPE chart renders.
74. Benchmark Horizon Profiles render for all three streams where data exists.
75. Full-sample Gain vs Schiff chart renders without misusing paired terminology.
76. Benchmark Summary table renders with clean labels.
77. Schiff Benchmark page has no more than four main chart/object panels.
78. Schiff Benchmark screenshot is saved and visually aligns with supplied target.

## I. Interaction, hovers and robustness

79. All primary filters are directly clickable in the browser without using only the More button.
80. All major Plotly hovers are human-readable: no underscores, no raw internal column names, clean decimals, compact management-readable text.

## J. Visual conformance hardening

The previous 80 gates are necessary but no longer sufficient. Gates 81-100 must also pass before completion.

81. Overview screenshot conforms to target card/panel structure.
82. Overview stress bucket order is correct.
83. Overview candidate frontier has no giant circle/ellipse overlays.
84. Overview candidate frontier displays finalist and Schiff markers.
85. Diagnostics matrix has styled pass/caution/fail cells.
86. Diagnostics page shows R2, Durbin-Watson and heteroscedasticity KPIs.
87. Diagnostics residual-vs-fitted chart does not collapse PED into an unreadable vertical strip, or uses small multiples to solve scale imbalance.
88. Scenario stream comparison labels do not overlap.
89. Scenario horizon comparison shows all three streams when Stream filter is All Streams.
90. Scenario decision table is styled and not an unformatted basic table.
91. Schiff MAPE chart separates Quarterly and Annual clearly.
92. Schiff horizon profiles show all three streams when Stream filter is All Streams.
93. Schiff summary table is styled and readable.
94. Visual reviewer report marks all four pages PASS.
95. Screenshot review confirms no major target/current visual gaps remain.
96. Browser test verifies all four top-level pages after visual fixes.
97. Filter/dropdown tests still pass.
98. Hover readability tests still pass.
99. Performance smoke check still passes.
100. BUG_BACKLOG.md has no unchecked visual defects.

## K. Chart source and semantic reconciliation hardening

The 100 visual/data gates are necessary but no longer sufficient. Gates 101-120 must also pass before completion.

101. Every main chart has a source table under `artifacts/chart_sources/`.
102. Chart source tables include the required page/chart/metric/source/calculation columns.
103. Overview finalist accuracy source reconciles to current Parquet values.
104. Ensemble composition source uses Parquet component weights from `ensemble_components_json`.
105. Stress source coalesces aliases and preserves Heavy RUC missing policy-window gaps.
106. Schiff gain chart is labelled full-sample when it shows full-sample MAPE gains.
107. Light RUC paired common-grid weakness is retained and not hidden by full-sample labels.
108. Scenario decision labels separate full-sample gains and paired win rate.
109. Horizon chart sources include all three streams and both finalist/Schiff scenarios when All Streams is selected.
110. ACF chart source table exists and documents residual source.
111. Calibration R2 label matches its source field.
112. Residual-vs-fitted axis units are not misleading.
113. Candidate count label is precise.
114. Chart source validation report passes.
115. Semantic label validation report passes.
116. Visual conformance validation report passes.
117. Final screenshots exist for all four pages.
118. Screenshot matrix marks all four pages PASS.
119. Filter and hover evidence is present.
120. Existing 100-gate validation has zero failures and BUG_BACKLOG.md is closed.
