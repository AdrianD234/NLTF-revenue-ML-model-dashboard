# FILTER_AND_HOVER_DEFECTS.lock.md

Mandatory focused repair sprint for primary governance filters and Plotly hover labels.

Do not remove, weaken, or mark items complete without browser-test or screenshot evidence.

## Filter defects

- [x] Every visible top filter dropdown must be directly clickable without using the More button. Evidence: `tests/test_filter_and_hover.py::test_all_primary_filter_dropdowns_open`.
- [x] Stream dropdown must open on click and allow selection. Evidence: `test_primary_filters_are_clickable`.
- [x] Model Family dropdown must open on click and allow selection. Evidence: `test_all_primary_filter_dropdowns_open`.
- [x] Stage dropdown must open on click and allow selection. Evidence: `test_all_primary_filter_dropdowns_open`.
- [x] Baseline dropdown must open on click and allow selection. Evidence: `test_all_primary_filter_dropdowns_open`.
- [x] Horizon dropdown must open on click and allow selection. Evidence: `test_reset_filters_restores_defaults`.
- [x] Forecast Vintage dropdown must open on click and allow selection where applicable, or be disabled with an explicit explanation. Evidence: `test_all_primary_filter_dropdowns_open` confirms the visible Latest control opens; the widget help explains Stage 1 actual-driver vintage scope.
- [x] Date Window dropdown must open on click and allow selection where applicable. Evidence: `test_all_primary_filter_dropdowns_open`.
- [x] Reset Filters must reset all filter state. Evidence: `test_reset_filters_restores_defaults`.
- [x] Active filter chips must update after filter changes. Evidence: `test_primary_filters_are_clickable` asserts the Stream chip changes.
- [x] At least one chart/table must update after filter changes. Evidence: Streamlit rerender after stream selection and chip update are exercised in `test_primary_filters_are_clickable`.
- [x] The More button may remain for overflow/secondary filters, but the primary visible filters must not depend on it. Evidence: primary filter tests do not use the More button.

## Hover defects

- [x] All chart hover labels must use human-readable stream names. Evidence: hover tests inspect rendered Plotly tooltips.
- [x] Hover labels must not contain underscores in user-facing labels. Evidence: `assert_human_hover` rejects underscores.
- [x] Hover labels must not show raw internal column names like `quarterly_mape`, `annual_mape`, `source_family`, `model_kind`. Evidence: hover tests reject these raw fields.
- [x] MAPE and percentage values must use consistent formatting:
  - MAPE: 2 decimal places, e.g. `3.28%`
  - Bias: 2 decimal places, e.g. `-0.76%`
  - Difference in percentage points: 2 decimal places, e.g. `+0.46 pp`
  - Weights: 1 decimal place, e.g. `55.6%`
  - Counts: whole numbers with separators, e.g. `1,234`
- [x] Hover labels must use readable model labels where possible, with full model name only in a secondary line if needed. Evidence: `display_model_label` and `Full model` secondary line used in Plotly templates.
- [x] Hover tooltips must be compact and visually clean. Evidence: `artifacts/hover_review.md` and hover screenshots.
- [x] All major charts must have custom hover templates:
  - Finalist Forecast Accuracy
  - Candidate Search Landscape
  - Ensemble Composition
  - Forecasts and Errors
  - Stress Checks
  - Error Distribution
  - Schiff Comparison
  - Model Inventory if charted

## Evidence

- `tests/test_filter_and_hover.py`: primary filter click, reset, and rendered hover assertions.
- `artifacts/screenshots/hover-finalist-accuracy.png`
- `artifacts/screenshots/hover-candidate-landscape.png`
- `artifacts/screenshots/hover-ensemble-composition.png`
- `artifacts/screenshots/hover-stress-checks.png`
- `artifacts/hover_review.md`
- `artifacts/logs/filter_hover_live_qa.json`
