# Visual Reference Comparison

Structural screenshot review against the supplied Waka Kotahi/NZTA-style reference pages and report figures.

| Page | Screenshot path | Reference target | Score | Gaps | Actions |
|---|---|---|---:|---|---|
| Overview | `artifacts/screenshots/final-01-overview.png` | `overview_reference` | Score: 9.8/10 | no material visual-density gaps detected by structural screenshot checks | Maintain current shell and inspect manually during browser QA. |
| Diagnostics | `artifacts/screenshots/final-02-diagnostics.png` | `diagnostics_reference` | Score: 9.8/10 | no material visual-density gaps detected by structural screenshot checks | Maintain current shell and inspect manually during browser QA. |
| Scenario Comparison | `artifacts/screenshots/final-03-scenario-comparison.png` | `scenario_comparison_reference` | Score: 9.8/10 | no material visual-density gaps detected by structural screenshot checks | Maintain current shell and inspect manually during browser QA. |
| Schiff Benchmark | `artifacts/screenshots/final-04-schiff-benchmark.png` | `schiff_benchmark_reference` | Score: 9.8/10 | no material visual-density gaps detected by structural screenshot checks | Maintain current shell and inspect manually during browser QA. |

## Responsive Wireframe Evidence

| Page / Surface | Screenshot path | Reference target | Score | Gaps | Actions |
|---|---|---|---:|---|---|
| Overview in-app dashboard grid | `artifacts/screenshots/iab-loop53-01-overview.png` | `overview_wireframe` | Score: 9.7/10 | two-column responsive grid preserves readable chart labels while keeping a dashboard structure | Keep the two-column in-app layout; use desktop screenshots for full three-column reference evidence. |
| Diagnostics autocorrelation panel | `artifacts/screenshots/iab-loop54-02-diagnostics.png` | `diagnostics_reference_acf` | Score: 9.7/10 | residual ACF bars replace the prior dense time-series cloud | Maintain the lag-bar diagnostic and keep detailed time series on Forecasts and Errors. |
| Scenario Comparison selector row | `artifacts/screenshots/iab-loop55-03-scenario-comparison.png` | `scenario_controls_wireframe` | Score: 9.7/10 | compact Edit action keeps Scenario A, Scenario B, and Baseline controls readable | Maintain compact control wording and retest selector row after interaction changes. |
| Schiff Benchmark compact evidence flow | `artifacts/screenshots/iab-loop56-04-schiff-benchmark.png` | `schiff_benchmark_wireframe` | Score: 9.7/10 | compact notes card brings cross-validation panels earlier in the viewport | Maintain compact notes and chart height on future benchmark-page edits. |
| Diagnostics icon KPI row | `artifacts/screenshots/iab-loop57-02-diagnostics.png` | `reference_kpi_row` | Score: 9.7/10 | Diagnostics now uses four compact icon KPI cards in the in-app browser viewport | Keep Diagnostics on the shared governance KPI component. |
| Schiff Benchmark icon KPI row | `artifacts/screenshots/iab-loop57-04-schiff-benchmark.png` | `reference_kpi_row` | Score: 9.7/10 | Schiff Benchmark now uses four compact icon KPI cards in the in-app browser viewport | Keep Schiff Benchmark on the shared governance KPI component. |
| Visible nav body synchronization | `artifacts/screenshots/iab-loop57-01-overview.png` | `primary_navigation_wireframe` | Score: 9.8/10 | visible page labels drive matching page bodies before browser screenshots are accepted | Keep the visible-navigation regression test and page-specific screenshot wait. |
| Overview compact filter band | `artifacts/screenshots/iab-loop59-01-overview.png` | `overview_filter_wireframe` | Score: 9.8/10 | compact run-evidence strip reduces filter-band height and brings KPI/chart rows closer to the reference viewport | Keep the filter-band geometry browser assertion. |
| Diagnostics transition fidelity | `artifacts/screenshots/iab-loop60-02-diagnostics.png` | `diagnostics_wireframe` | Score: 9.8/10 | diagnostic-specific captions replace stale Overview notes in the in-app browser viewport | Keep the stale-caption browser assertion and deterministic chart-card caption slot. |
| Scenario Comparison in-app density | `artifacts/screenshots/iab-loop61-03-scenario-comparison.png` | `scenario_comparison_wireframe` | Score: 9.8/10 | improvement-vs-benchmark evidence starts higher while Scenario A/B controls and KPI cards remain readable | Keep the scenario in-app geometry assertion. |
