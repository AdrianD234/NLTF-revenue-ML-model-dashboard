# Interaction and Filter Review

Reviewer role: interaction/filter reviewer for the Stage 1 Model Governance Dashboard.

Review date: 2026-05-21.

Status: pass for the current verification pass.

## Scope Reviewed

- Rendered Streamlit app at `http://localhost:8501`.
- Primary governance page navigation.
- Directly clickable top filter controls.
- Reset Filters behavior.
- Active filter chips.
- Candidate, forecast, and inventory supporting controls.
- Hover text readability across major charts.
- Current browser tests and screenshots.
- Latest arbitration-run evidence for `run_20260520_002339`.

## Verdict

Pass. The current app exposes the primary filters as real directly clickable controls, keeps active filter chips readable, resets the top filter state, and preserves the supporting drilldown interactions through focused browser tests.

The prior failure state is no longer current: the strict verifier passes, Playwright e2e passes, and the focused filter/hover browser tests pass. The review is now aligned to the current four-page governance shell plus supporting drilldown modules.

## Checked Interactions

| Interaction | Current result | Evidence |
|---|---|---|
| Overview, Diagnostics, Scenario Comparison, Schiff Benchmark navigation | Pass | `tests/test_playwright_dashboard.py`; fresh `mcp-*` and `final-*` screenshots. |
| Stream filter | Pass | Direct dropdown click opens and can select a non-default stream. |
| Model Family filter | Pass | Direct dropdown click opens; readable filter value retained. |
| Stage filter | Pass | Direct dropdown click opens; current stage chip remains readable. |
| Baseline filter | Pass | Direct dropdown click opens and displays `Refined Finalist`. |
| Horizon filter | Pass | Direct dropdown click opens and displays `1-12 Quarters`. |
| Forecast Vintage filter | Pass | Direct dropdown click opens or exposes the current latest-run vintage value. |
| Date Window filter | Pass | Direct dropdown click opens and displays the target-period scope. |
| Reset Filters | Pass | Browser test changes Stream and Horizon, clicks Reset Filters, and confirms default chips return. |
| Candidate Landscape drilldown | Pass | Browser tests verify candidate-role content, readable hover, finalist marker evidence, and download availability. |
| Model Inventory drilldown | Pass | Browser tests verify search/rank/model-detail controls and filtered CSV download. |
| Forecast/Stress drilldown | Pass | Browser tests verify forecast controls and stress hover readability. |

## Hover Review

| Chart | Current result | Evidence |
|---|---|---|
| Finalist Forecast Accuracy | Pass | Hover shows management labels, formatted percentages, model, and source. |
| Candidate Search Landscape | Pass | Hover shows Stream, Model, Candidate role, Quarterly MAPE, Annual MAPE, Bias, and Source without raw column names. |
| Ensemble Composition | Pass | Hover shows component and weight with one-decimal percentage formatting. |
| Stress and Horizon Checks | Pass | Hover shows human-readable stress bucket labels and MAPE formatting. |

## Current Test Evidence

- Full pytest passed: `119 passed, 29 deselected`.
- Strict verifier browser e2e passed: `28 passed`.
- Focused filter and hover tests are covered by:
  - `tests/test_filter_and_hover.py`
  - `tests/test_filters_are_clickable.py`
  - `tests/test_reset_filters.py`
  - `tests/test_hovers_are_readable.py`

## State Export Note

The dashboard implements current-view JSON export in the advanced controls rather than full URL bookmark restoration. This is documented behavior and is covered as an audit/export workflow, not a complete import/restore bookmark workflow.

## Conclusion

The current interaction and filter layer passes for this recursive audit loop. The remaining reason the overall sprint cannot be closed is quota-based: fewer than 20 recursive audit loops have been completed.
