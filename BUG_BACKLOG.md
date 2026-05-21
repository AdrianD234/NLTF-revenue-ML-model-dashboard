# BUG_BACKLOG.md

Backlog state after product-hardening sprint, red-team review, original-spec comparison, and three reviewer passes.

## Closed Product-Hardening Items

### Executive Summary

- [x] Add a management conclusion panel: implemented with `manager_conclusion`.
- [x] Add enterprise-ready first-viewport decision brief: implemented above KPI cards with readiness, benchmark result, watch point, and next gate.
- [x] Add a warning badge/readout if Light RUC does not beat Schiff or stress is high: implemented through governance cards and data-quality warning panel.
- [x] Add compact decision status: implemented with Promote, Watchlist, Reject, and Needs Stage 2 cards.

### Candidate Landscape

- [x] Add efficient-frontier highlighting: implemented as dotted frontier trace.
- [x] Add toggle for screen/final/both: implemented through sidebar stage selector and screen/final toggles.
- [x] Add toggle to hide failed/outlier candidates: implemented with protected finalist/Schiff preservation.
- [x] Add Schiff marker annotations: implemented for Schiff and finalist markers.
- [x] Add hover details: implemented for stage, variant, source family, model, MAPE, bias, governance score, and Schiff class.

### Schiff Comparison

- [x] Prevent Schiff residual/fixed blends being classified as pure Schiff: implemented with `schiff_class` and `is_schiff_text` protections.
- [x] Add paired win-rate badges: implemented in governance cards and paired summaries.
- [x] Add a beats-Schiff summary by stream: implemented in Schiff Decision Summary.
- [x] Show best challenger vs pure Schiff only: implemented through paired baseline rows and Schiff purity classification evidence.

### Ensemble Composition

- [x] Add short component labels C1, C2, C3 with lookup table: implemented.
- [x] Show static solver weights separately from prequential weights: implemented through static/prequential filters and method readout.
- [x] Show mean prequential weights over time if available: implemented with origin-level weight path.
- [x] Add warning if static solver wins but prequential does not: implemented in ensemble method readout.
- [x] Normalise fallback ensemble scoring across origins: implemented through `ensemble_fallback_scores`.

### Forecasts and Errors

- [x] Add actual vs predicted chart: implemented.
- [x] Add percent error over time chart: implemented.
- [x] Add horizon-bucket box plot: implemented.
- [x] Add model selector with shortened model labels: implemented.
- [x] Add empty-state messages if quarterly predictions are missing: implemented through warning panels and empty figures.
- [x] Add MAPE by forecast horizon drilldown: implemented.

### Stress Checks

- [x] Show horizon buckets 1-4, 5-8, 9-12: implemented.
- [x] Show 2022-23 stress window: implemented.
- [x] Show recent 2024+ performance: implemented.
- [x] Show loaded 2020-21 bucket when present: implemented.
- [x] Add explanatory note for why Light RUC is hard: implemented.
- [x] Add high-risk band: implemented.

### Model Inventory

- [x] Add KPI cards for filtered rows, streams represented, source families: implemented.
- [x] Add ranking options for quarterly MAPE, annual MAPE, governance score, and bias: implemented.
- [x] Add CSV download: implemented.
- [x] Add Inventory read panel naming best quarterly and annual candidates: implemented.
- [x] Add model detail drawer/section: implemented.
- [x] Add model-family and Schiff-class visuals: implemented.
- [x] Prevent stale Streamlit loader cache from hiding derived Schiff-class fields: implemented with explicit loader schema-version cache key and regression assertions.

### Run Audit

- [x] Summarise errors.csv by error type: implemented as diagnostic chart.
- [x] Add warning if errors.csv is non-empty: implemented.
- [x] Add file status table with row counts and sizes: implemented.
- [x] Add missing-file robustness tests: implemented in data-loader tests.

### Visual Polish

- [x] Check every screenshot for blank space and chart density: documented in screenshot reviews.
- [x] Improve chart titles and axis labels: implemented across Plotly helpers.
- [x] Add data labels where appropriate: implemented for bars and diagnostic charts.
- [x] Make long model names readable: implemented with aliases and C-label mappings.
- [x] Ensure every page has meaningful content above the fold: implemented with cards/readouts/charts before row detail.
- [x] Collapse operational sidebar by default for presentation screenshots: implemented.
- [x] Keep technical schema diagnostics out of global management-page warning banners: implemented by moving them into Run Audit.
- [x] Add Waka Kotahi/NZTA-style governance shell with four primary pages: implemented with Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark.
- [x] Add visible horizontal filter bar: implemented with stream, model family, stage, baseline, horizon, forecast vintage, date window, reset, and state export controls.
- [x] Add footer and page indicator: implemented with page labels and a navy footer strip.
- [x] Standardise Overview around the supplied report figures: implemented with five numbered chart modules.

### Red-Team Review

- [x] Evidence that selected models really win is visible and sourced.
- [x] Schiff benchmark answer is clear and separated from Schiff residual/blend challengers.
- [x] Static solver hindsight risk is visible through static/prequential readout.
- [x] 2022-23 RUC stress window is explicit.
- [x] Charts include stress and frontier cues so weak performance is not hidden.
- [x] Failed candidates/outliers can be hidden without losing finalists or Schiff rows.
- [x] Metrics are calculated from real loaded data and tested.
- [x] Long model names are aliased or mapped.
- [x] Pages are management-ready with executive conclusions, charts, and warnings.

### Reviewer Findings from Final Product-Hardening Sprint

- [x] Interaction P1: clearing empty selection should not widen results: implemented in `filter_by_common_controls` and covered by unit tests.
- [x] Interaction P1: dashboard-level reset/default restoration: implemented through the visible Reset Filters action.
- [x] Interaction P1: bookmark/state export: implemented as JSON current-view export; full URL query bookmarking documented in `INTERACTION_SPEC.lock.md`.
- [x] Interaction P2: Playwright render checks needed stronger interaction coverage: strengthened with reset, filter state, page-navigation, and export-control assertions.
- [x] Interaction P2: model selector 80-row cap: removed after search/ranking filters.
- [x] Interaction P2: Candidate Landscape page-local download: implemented.
- [x] Visual P1: eight-tab analyst shell did not match reference: four primary governance pages added while keeping drilldown tabs.
- [x] Visual P1: filters hidden in sidebar: visible governance filter row added.
- [x] Visual P1: footer/page indicator missing: implemented.
- [x] UX P1: first viewport lacked reference-style dashboard density: Overview now contains the key report figures and management decision content.
- [x] Governance recommendation: keep champion-selection rule explicit: retained in Overview, Scenario Comparison, and Schiff Benchmark text.

No unchecked items remain.

## Loop 51 Responsive Visual Repair

- [x] Prevent narrow in-app browser page-chip clipping and filter-value ellipses.
- [x] Stack Overview chart cards at narrow widths so charts remain readable instead of squeezing three panels into one row.
- [x] Add a narrow-browser Playwright assertion covering navigation labels, filter readability, shell overflow, and chart stacking.

## Loop 52 Header / Navigation Visual Repair

- [x] Integrate the desktop primary navigation into the masthead band instead of leaving it below the header.
- [x] Tighten the top filter band after moving the desktop nav upward.
- [x] Preserve the narrow in-app browser layout so the nav sits below the Governance title without overlap.
- [x] Add desktop masthead and narrow non-overlap browser assertions.

## Loop 53 Overview Responsive Grid Repair

- [x] Remove the cramped visual masthead subtitle from the governance header.
- [x] Replace the sparse one-column in-app Overview stack with a readable two-column dashboard grid.
- [x] Avoid the unreadable three-panel squeeze that crushed chart labels and ensemble components.
- [x] Strengthen the narrow-browser assertion so Overview chart cards keep dashboard-row density.

## Loop 54 Diagnostics Autocorrelation Repair

- [x] Replace the dense error-over-time cloud in Diagnostics with residual ACF-by-lag bars.
- [x] Add unit coverage that verifies lag-bar semantics and axis labels.
- [x] Add browser coverage that verifies the Diagnostics page exposes the residual ACF explanation.

## Loop 55 Scenario Comparison Control Repair

- [x] Replace the long Scenario settings popover label with compact Edit wording.
- [x] Add browser coverage that verifies the compact control and rejects the longer crowded label.

## Loop 56 Schiff Benchmark Viewport Repair

- [x] Reduce the Schiff benchmark chart height for the in-app wireframe.
- [x] Compact the benchmark comparison and paper replication notes panel.
- [x] Move cross-validation evidence earlier in the in-app viewport.

## Loop 57 KPI Row Reference Repair

- [x] Convert Diagnostics KPI cards to the same icon-tile governance KPI row used by the reference pages.
- [x] Convert Schiff Benchmark KPI cards to the same icon-tile governance KPI row used by the reference pages.
- [x] Add browser coverage that verifies both pages retain four dense KPI cards at the in-app browser width.

## Loop 58 Primary Navigation Synchronization Repair

- [x] Preserve Streamlit radio interactivity while hiding the native radio glyph.
- [x] Bind page-body rendering to the same current page value used by the governance shell.
- [x] Add browser coverage that clicks visible nav text and rejects stale prior-page body content.

## Loop 59 Filter Band Density Repair

- [x] Replace the tall run-evidence caption block with a compact evidence line inside the filter card.
- [x] Tighten the filter-to-KPI vertical spacing so the Overview page more closely matches the reference first viewport.
- [x] Add browser geometry coverage for filter band, first KPI row, and first chart position.

## Loop 60 Diagnostics Transition Repair

- [x] Replace the wrapped Diagnostics provenance caption with a compact first-viewport evidence strip.
- [x] Add Diagnostics-specific chart captions so the first diagnostic cards cannot show stale Overview readouts.
- [x] Add deterministic empty-caption placeholders to the shared chart card component.
- [x] Add browser coverage that rejects visible Overview ghost captions on the Diagnostics page.

## Loop 61 Scenario Comparison Density Repair

- [x] Reduce Scenario Comparison primary chart heights to move the Improvement vs Benchmark panel higher in the in-app browser.
- [x] Keep the first three Scenario Comparison panels visible above the fold at 820px width.
- [x] Add browser coverage for the Scenario Comparison improvement-panel first-viewport position.

## Loop 62 Filters and Hovers Repair

- [x] Replace fake-looking primary filter displays with directly clickable `st.selectbox` controls for Stream, Model Family, Stage, Baseline, Horizon, Forecast Vintage, and Date Window.
- [x] Keep More as an advanced-control overflow only; primary filter tests do not depend on it.
- [x] Add browser assertions for direct primary dropdown opening, stream selection, active chip update, KPI/chart-region update, and reset-to-default behaviour.
- [x] Add shared hover formatting helpers and apply custom Plotly hover templates to major management charts.
- [x] Add browser assertions and screenshot evidence for human-readable hover labels on Finalist Accuracy, Candidate Landscape, Ensemble Composition, and Stress Checks.
