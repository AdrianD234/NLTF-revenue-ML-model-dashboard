# Chart Semantics Review

Status: PASS

The charts are data-backed and now conform to the required visual semantics.

| Area | Result | Evidence |
| --- | --- | --- |
| Candidate frontier | PASS | Uses Parquet candidate rows, curated cone sample, finalist stars, pure Schiff open triangles, PDF diamonds, and no giant overlays. |
| Overview stress order | PASS | Browser test verifies `1-4 qtrs`, `5-8 qtrs`, `9-12 qtrs`, `2024+`, `2022-23`, `Annual`. |
| Diagnostics | PASS | Diagnostic matrix has styled pass/caution/fail cells; residual-vs-fitted uses stream facets. |
| Scenario comparison | PASS | Scenario A/B dumbbell sections are separated; horizon profiles include PED, Light RUC and Heavy RUC. |
| Schiff benchmark | PASS | MAPE comparison is split into Quarterly and Annual sections; horizon profiles include all streams and pure Schiff rows only. |
| Full-sample vs paired terminology | PASS | Gain charts showing +2.40 pp for Light RUC are labelled full-sample; Light RUC paired common-grid gain is retained separately as negative. |
| Chart source tables | PASS | All 16 primary charts export source tables under `artifacts/chart_sources/`, and `scripts/validate_chart_sources.py` passed. |

Browser evidence: `tests/test_playwright_frontend_interactions.py` passed after hovering major Plotly charts, inspecting hover text and comparing rendered Plotly stress trace data to the exported source table.
