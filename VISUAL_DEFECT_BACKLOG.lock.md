# VISUAL_DEFECT_BACKLOG.lock.md

The dashboard visual-fidelity defects from the supplied reference screenshots have been reviewed against the latest Playwright screenshots.

## Header and Navigation Defects

- [x] Header does not match the reference layout.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::header`, `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_navigation_labels_not_clipped`; fresh screenshot shows logo lockup left, large Governance title, lime underline, page indicator right, and a compact horizontal nav below the masthead.
  - Status: Complete.

- [x] Top navigation is broken/truncated.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_primary_navigation`, `tests/test_playwright_dashboard.py::test_navigation_labels_not_clipped`.
  - Browser/visual assertion: Playwright asserts `Schiff Benchmark` is present and `‹nchmark` is absent.
  - Status: Complete.

- [x] Page structure does not match four-page reference.
  - Evidence: `artifacts/screenshots/final-01-overview.png` through `artifacts/screenshots/final-04-schiff-benchmark.png`.
  - Changed file/function: `app.py::main`, `app.py::render_overview`, `app.py::render_diagnostics`, `app.py::render_scenario_comparison`, `app.py::render_schiff_benchmark_page`.
  - Browser/visual assertion: Playwright clicks Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark.
  - Status: Complete.

## Filter Bar Defects

- [x] Filter controls are truncated.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_top_filter_bar`, `model_dashboard/ui.py::filter_chips`.
  - Browser/visual assertion: `test_filter_values_are_readable` asserts `Stream: All Streams`, `Family: All Families`, and `Horizon: 1-12 Quarters`.
  - Status: Complete.

- [x] Filter area is too tall and sparse.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_top_filter_bar`, `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: Fresh screenshot shows a single compact filter-chip row with advanced controls behind `More`.
  - Status: Complete.

- [x] Reset button styling is oversized and misaligned.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: Reset Filters appears as a compact navy button aligned to the filter chip row.
  - Status: Complete.

## Overview Page Defects

- [x] Overview page must fit key charts above the fold like the reference.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_overview`, `app.py::compact_figure`, `tests/test_playwright_dashboard.py`.
  - Browser/visual assertion: Playwright captures a 1680 x 940 screenshot and asserts all five numbered Overview management chart modules are above the first viewport fold.
  - Status: Complete.

- [x] KPI cards are missing or not in reference style.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::gov_kpi_grid`, `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: Overview screenshot shows four icon KPI cards with headline values and deltas.
  - Status: Complete.

- [x] Chart panels need rounded-card containers.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::chart_card`, `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: All numbered overview modules render inside rounded bordered dashboard cards.
  - Status: Complete.

## Candidate Landscape Defects

- [x] Candidate landscape chart is clipped and poorly positioned.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/plots.py::plot_candidate_landscape`, `app.py::compact_figure`.
  - Browser/visual assertion: Overview screenshot shows a clean, unclipped competitive-frontier scatter.
  - Status: Complete.

- [x] Finalist labels overlap.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::compact_figure`.
  - Browser/visual assertion: Compact overview landscape removes annotation labels; detailed hover evidence remains in the drilldown.
  - Status: Complete.

- [x] Candidate landscape must show competitive frontier clearly.
  - Evidence: `artifacts/screenshots/final-01-overview.png`, `artifacts/screenshots/final-05-candidate-landscape.png`.
  - Changed file/function: `model_dashboard/plots.py::plot_candidate_landscape`, `app.py::hide_candidate_outliers`.
  - Browser/visual assertion: Frontier/outlier filtering remains tested by unit and browser checks.
  - Status: Complete.

## Ensemble Composition Defects

- [x] Ensemble composition is wrong visually and analytically weak.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_overview`, `app.py::reference_ensemble_composition`, `app.py::render_ensemble_composition`.
  - Browser/visual assertion: Overview now uses the supplied report/reference composition; the drilldown preserves selected-run solver-weight modes.
  - Status: Complete.

- [x] Ensemble composition should use three side-by-side mini panels, not vertically stacked full-width bars.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/plots.py::plot_ensemble_composition`.
  - Browser/visual assertion: `test_ensemble_composition_has_three_stream_panels` checks PED, Light RUC, and Heavy RUC.
  - Status: Complete.

- [x] Component label mapping table is too dense and appears too early.
  - Evidence: `artifacts/screenshots/final-06-ensemble-composition.png`.
  - Changed file/function: `app.py::render_ensemble_composition`.
  - Browser/visual assertion: Component label mapping remains collapsed by default.
  - Status: Complete.

## Model Inventory Defects

- [x] Model Inventory is too plain and not dashboard-like.
  - Evidence: `artifacts/screenshots/final-09-model-inventory.png`.
  - Changed file/function: `app.py::render_model_inventory`, `app.py::render_model_detail`, `model_dashboard/plots.py::plot_inventory_family_performance`, `model_dashboard/plots.py::plot_schiff_class_mix`.
  - Browser/visual assertion: Screenshot review confirms KPI cards, visual summaries, model detail, and download behind a professional layout.
  - Status: Complete.

- [x] Inventory read sentence is awkward and too long.
  - Evidence: `artifacts/screenshots/final-09-model-inventory.png`.
  - Changed file/function: `app.py::inventory_summary`, `app.py::inventory_insight_cards`.
  - Browser/visual assertion: Inventory read is split into concise insight cards.
  - Status: Complete.

## Visual Style Defects

- [x] Colours do not fully match target.
  - Evidence: `artifacts/screenshots/final-01-overview.png` through `artifacts/screenshots/final-04-schiff-benchmark.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: Navy, lime, teal, and orange are used consistently across KPI, chart, and footer components.
  - Status: Complete.

- [x] Typography is not close enough.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: Page title, nav labels, card titles, and KPI values use a compact Segoe/Inter-style hierarchy.
  - Status: Complete.

- [x] Cards lack the polished reference appearance.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: Rounded cards, borders, top accents, shadows, compact notes, and button styling are visible.
  - Status: Complete.

- [x] Page footer should match reference.
  - Evidence: `artifacts/screenshots/final-01-overview.png` full-page capture.
  - Changed file/function: `model_dashboard/ui.py::footer_strip`, `app.py::main`.
  - Browser/visual assertion: Full-page screenshots include the dark navy footer strip with testbench label and data-as-of date.
  - Status: Complete.

## Required Layout-System Defects

- [x] Create CSS layout system with reusable government-dashboard cards.
  - Evidence: `model_dashboard/ui.py`.
  - Changed file/function: `.gov-header`, `.gov-nav`, `.gov-filter-card`, `.gov-kpi-grid`, `.gov-kpi-card`, `.gov-chart-card`, `.gov-dashboard-grid`, `.gov-footer`, `.gov-note`, `.gov-badge`.
  - Browser/visual assertion: The four primary screenshots use the shared shell and card styling.
  - Status: Complete.

- [x] Rebuild Overview page using grid/card layout.
  - Evidence: `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_overview`.
  - Status: Complete.

- [x] Rebuild Diagnostics page using grid/card layout.
  - Evidence: `artifacts/screenshots/final-02-diagnostics.png`.
  - Changed file/function: `app.py::render_diagnostics`.
  - Browser/visual assertion: Playwright asserts all six numbered Diagnostics panels are above the first viewport fold after the loop 30 rebuild.
  - Status: Complete.

- [x] Rebuild Scenario Comparison page using grid/card layout.
  - Evidence: `artifacts/screenshots/final-03-scenario-comparison.png`.
  - Changed file/function: `app.py::render_scenario_comparison`.
  - Browser/visual assertion: Playwright asserts compact Scenario A/B controls and all six numbered Scenario panels are above the first viewport fold.
  - Status: Complete.

- [x] Rebuild Schiff Benchmark page using grid/card layout.
  - Evidence: `artifacts/screenshots/final-04-schiff-benchmark.png`.
  - Changed file/function: `app.py::render_schiff_benchmark_page`.
  - Browser/visual assertion: Playwright asserts the benchmark chart, replication notes, and all three stream cross-validation panels are above the first viewport fold.
  - Status: Complete.

## Responsive In-App Browser Defects

- [x] Narrow in-app browser header/page label clips or weakens the reference hierarchy.
  - Evidence: `artifacts/screenshots/iab-loop51-01-overview.png`, `artifacts/screenshots/iab-loop51-04-schiff-benchmark.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_governance_shell_is_readable_in_narrow_browser` checks four navigation labels, page chip text, filter values, and no horizontal overflow at 820px width.
  - Status: Complete.

- [x] Narrow in-app browser overview squeezes three chart cards into unreadable columns.
  - Evidence: `artifacts/screenshots/iab-loop51-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_governance_shell_is_readable_in_narrow_browser` asserts the first and second Overview chart titles are vertically stacked at narrow width.
  - Status: Complete.

## Loop 52 Desktop Header / Density Defects

- [x] Desktop primary nav still sat below the masthead instead of integrated into the right-side header band.
  - Evidence: `artifacts/screenshots/final-01-overview.png`, `artifacts/screenshots/iab-loop52-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_reference_header_nav_is_integrated_on_desktop`.
  - Status: Complete.

- [x] Narrow browser nav overlapped logo/title after the desktop nav lift.
  - Evidence: `artifacts/screenshots/iab-loop52-01-overview.png` through `artifacts/screenshots/iab-loop52-04-schiff-benchmark.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_governance_shell_is_readable_in_narrow_browser`.
  - Status: Complete.

## Loop 53 Overview Responsive Grid Defects

- [x] In-app Overview remained visually sparse when chart cards stacked into a single column.
  - Evidence: `artifacts/screenshots/iab-loop53-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_governance_shell_is_readable_in_narrow_browser`.
  - Status: Complete.

- [x] Three-column in-app Overview squeeze made chart labels and ensemble components unreadable.
  - Evidence: `artifacts/screenshots/iab-loop53-01-overview.png`.
  - Changed file/function: `model_dashboard/ui.py::inject_theme`.
  - Browser/visual assertion: `test_governance_shell_is_readable_in_narrow_browser`.
  - Status: Complete.

## Loop 54 Diagnostics Chart Fidelity Defects

- [x] Diagnostics autocorrelation card used a dense signed-error-over-time cloud instead of a reference-style lag diagnostic.
  - Evidence: `artifacts/screenshots/iab-loop54-02-diagnostics.png`.
  - Changed file/function: `model_dashboard/plots.py::plot_autocorrelation_diagnostics`, `app.py::render_diagnostics`.
  - Browser/visual assertion: `test_autocorrelation_diagnostics_uses_lag_bars`, Playwright Diagnostics content check.
  - Status: Complete.

## Loop 55 Scenario Comparison Control Defects

- [x] Scenario Comparison control row used a long settings label that crowded Scenario A/B/Baseline controls in the in-app browser.
  - Evidence: `artifacts/screenshots/iab-loop55-03-scenario-comparison.png`.
  - Changed file/function: `app.py::render_scenario_comparison`.
  - Browser/visual assertion: Playwright Scenario Comparison check asserts compact `Edit` control and absence of the long label.
  - Status: Complete.

## Loop 56 Schiff Benchmark Viewport Defects

- [x] Schiff Benchmark replication notes panel was too tall, delaying cross-validation evidence in the in-app viewport.
  - Evidence: `artifacts/screenshots/iab-loop56-04-schiff-benchmark.png`.
  - Changed file/function: `app.py::render_schiff_benchmark_page`, `app.py::schiff_replication_notes_panel`.
  - Browser/visual assertion: Schiff Benchmark browser assertions plus loop-56 screenshot review.
  - Status: Complete.

## Loop 57 KPI Row Defects

- [x] Diagnostics and Schiff Benchmark KPI rows looked plainer than the supplied reference KPI cards.
  - Evidence: `artifacts/screenshots/iab-loop57-02-diagnostics.png`, `artifacts/screenshots/iab-loop57-04-schiff-benchmark.png`.
  - Changed file/function: `app.py::basic_cards_as_governance_kpis`, `app.py::render_diagnostics`, `app.py::render_schiff_benchmark_page`.
  - Browser/visual assertion: `test_primary_reference_pages_use_icon_kpi_rows`.
  - Status: Complete.

## Loop 58 Navigation Synchronization Defects

- [x] Visible top-nav clicks could show the selected page chip while the body briefly retained stale prior-page content in the in-app browser.
  - Evidence: `artifacts/screenshots/iab-loop57-01-overview.png` through `artifacts/screenshots/iab-loop57-04-schiff-benchmark.png`.
  - Changed file/function: `app.py::main`, `model_dashboard/ui.py::inject_theme`, `tests/test_playwright_dashboard.py::test_visible_navigation_text_changes_page_body`.
  - Browser/visual assertion: browser pass clicked Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark via visible labels and confirmed the matching page body before each screenshot.
  - Status: Complete.

## Loop 59 Filter Band Density Defects

- [x] Governance filter card remained taller than the supplied reference layout and pushed the KPI/chart grid down.
  - Evidence: `artifacts/screenshots/iab-loop59-01-overview.png`, `artifacts/screenshots/final-01-overview.png`.
  - Changed file/function: `app.py::render_top_filter_bar`, `model_dashboard/ui.py::inject_theme`, `tests/test_playwright_dashboard.py::test_filter_band_is_reference_compact`.
  - Browser/visual assertion: browser geometry test asserts the filter-to-KPI and first-chart vertical positions stay within reference-density targets.
  - Status: Complete.

## Loop 60 Diagnostics Transition Defects

- [x] Diagnostics in-app screenshots could retain faint Overview captions during the page transition.
  - Evidence: `artifacts/screenshots/iab-loop60-02-diagnostics.png`.
  - Changed file/function: `app.py::render_diagnostics`, `model_dashboard/ui.py::chart_card`, `tests/test_playwright_dashboard.py::test_diagnostics_in_app_grid_replaces_overview_panels`.
  - Browser/visual assertion: browser test asserts Diagnostics-specific evidence/captions are visible and `Stress watch:` / `Error distribution read:` are not visible above the fold on the Diagnostics page.
  - Status: Complete.

## Loop 61 Scenario Comparison Density Defects

- [x] Scenario Comparison improvement evidence started too low in the in-app viewport after the first two chart cards.
  - Evidence: `artifacts/screenshots/iab-loop61-03-scenario-comparison.png`.
  - Changed file/function: `app.py::render_scenario_comparison`, `tests/test_playwright_dashboard.py::test_scenario_in_app_grid_brings_improvement_panel_into_view`.
  - Browser/visual assertion: browser test asserts the first three Scenario Comparison panels are above the fold and the Improvement vs Benchmark panel starts before y=790 at 820px width.
  - Status: Complete.

## Current Sprint Status

All listed visual defects have after-screenshot evidence and direct code/test evidence. The four primary wireframe rebuild loops are documented as loops 29 through 32, the strict 50-loop quota is exceeded with loop 61, and the latest browser pass is documented in `artifacts/screenshots/iab-loop61-*.png`.
