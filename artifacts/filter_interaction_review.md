# Filter Interaction Review

Status: pass for the current verification pass.

## Checked interactions

- Stream filter opens directly without using the More button.
- Model Family filter opens directly.
- Stage filter opens directly.
- Baseline filter opens directly.
- Horizon filter opens directly.
- Forecast Vintage filter opens directly or shows available latest-vintage option.
- Date Window filter opens directly.
- Reset Filters restores the default chips.
- Active filter chips update after a stream/horizon change.
- At least one KPI/chart region updates after a non-default stream filter.

## Hover checks

- Finalist Forecast Accuracy hover includes Quarterly MAPE, Annual MAPE, Model and Source.
- Candidate Landscape hover includes Stream, Model, Candidate role, Quarterly MAPE, Annual MAPE, Bias and Source.
- Ensemble Composition hover includes Weight and Component.
- Stress Checks hover includes Stress window, MAPE and Model.

No hover check exposes raw internal column names or underscores.

## Evidence

- `tests/test_filter_and_hover.py`
- `tests/test_filters_are_clickable.py`
- `tests/test_reset_filters.py`
- `tests/test_hovers_are_readable.py`
- `artifacts/hover_review.md`
