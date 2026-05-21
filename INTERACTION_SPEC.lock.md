# INTERACTION_SPEC.lock.md

## Required interactions

The dashboard must support:

- Run folder selection or configured run path.
- Stream filter.
- Model family/source family filter.
- Stage filter where available.
- Baseline selector where available.
- Horizon selector or horizon bucket selector.
- Date window selector where available.
- Forecast vintage selector if available, otherwise disabled/explained.
- Reset filters button.
- Model selector for forecast/error pages.
- Candidate table search/filter.
- Download filtered table as CSV.

## Bookmarks / state

Implemented approach:

- Streamlit session state persists filters during the session.
- A "Copy current view settings" button exports the current filter state as JSON.

Full URL query-parameter bookmarking is documented as unsupported for this Streamlit build because selected model/run controls include long local Windows paths and large multiselect state. The JSON export is the reproducible-review artifact.

## Interaction testing

Playwright/browser tests must verify:

- every tab can be opened;
- every major dropdown can be clicked or is represented by a visible state control;
- at least one non-default filter changes page content;
- reset filters restores defaults;
- model selector changes the displayed model where source data allows;
- missing-file warnings do not break interactions;
- state export behavior works as implemented.

## Completion rule

Do not mark the interaction layer complete unless all required interactions are tested or explicitly documented as unavailable due to missing source data.
