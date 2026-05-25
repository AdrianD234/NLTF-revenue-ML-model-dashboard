# Filter Interaction Review

Status: **passed** for the Parquet backed browser verification run.

## Checked Interactions

- Stream opens directly without using the More button.
- Model Family opens directly.
- Stage opens directly.
- Baseline opens directly.
- Horizon opens directly.
- Forecast Vintage opens directly.
- Date Window opens directly.
- Reset Filters restores the default selected combobox values.
- Selected combobox state is recorded through Streamlit's `aria-label` after a stream or horizon change.
- The KPI row updates to the selected stream's Parquet-backed MAPE after a Stream filter change.
- The removed compact filter/run-evidence text strip is absent from the visible browser DOM.

## Hover Checks

- Finalist Forecast Accuracy hover includes clean model, source, MAPE and bias labels.
- Candidate Search Frontier hover includes clean stream, model, role, MAPE, bias, source and feature labels.
- Ensemble Composition hover includes clean weight and component labels.
- Stress and Horizon Checks hover includes clean stress window, MAPE and model labels.

No hover check exposes raw internal names, source identifiers as primary labels, or excessive decimals.

## Evidence

- Full e2e browser run: 37 passed.
- Mandatory frontend interaction browser run: 5 passed.
- Hover screenshots are present under `artifacts/screenshots`.
- `tests/test_playwright_dashboard.py::test_filter_band_is_reference_compact` verifies `.run-evidence-compact`, `Run evidence:`, and `Curated rows:` are not visible.
