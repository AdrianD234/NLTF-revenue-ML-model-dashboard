# PARQUET_DASHBOARD_DATA_SPEC.lock.md

This lock defines the data contract for the Stage 1 Model Governance Dashboard refresh.

## Locked Data Source Rules

1. `stage1_curated_candidate_cone.parquet` is the primary data source for candidate and model rows.
2. Diagnostic audit files are secondary data sources for residual diagnostics, ACF, tests, actual-vs-predicted evidence and statistical checks.
3. The app must support missing diagnostic files gracefully with explicit unavailable states.
4. The app must never show stale old run values as current finalist metrics, including PED 5.49%, Light RUC 11.55%, or Heavy RUC 12.38% quarterly MAPE.
5. User-facing labels must be human-readable: no underscores, no raw column names, and no raw internal model names in chart hovers unless shown as secondary detail.
6. Default charting must use curated rows only, especially `plot_default_include == true` for candidate landscape views.
7. Full raw detail, if available, belongs behind expanders or downloads rather than the default management view.
8. The candidate landscape must preserve the cone-shaped search frontier insight, with distribution samples, frontier rows, finalists, pure Schiff, and PDF references differentiated.

## Required Derived Dashboard Datasets

- `candidate_df`: normalised Parquet candidate rows.
- `finalists_df`: one current recommended finalist per stream.
- `schiff_df`: pure Schiff structural benchmark rows only.
- `pdf_reference_df`: PDF/reference benchmark rows.
- `frontier_df`: candidate rows flagged as search frontier.
- `distribution_df`: curated cone distribution sample rows.
- `stress_df`: finalist horizon/stress buckets.
- `horizon_df`: long-form horizon MAPE data for finalists and Schiff.
- `diagnostic_df`: finalist and Schiff diagnostic measures from Parquet and audit files.
- `ensemble_df`: real component weights where available; never fabricated.
- `paired_df`: paired finalist-vs-Schiff comparison data.

## Current Workspace Status

As of the 2026-05-22 validation run, the requested diagnostic audit pack is present and the loader resolves the primary Parquet from the adjacent information pack:

`C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet`

The dashboard must also write auditable per-chart source tables under `artifacts/chart_sources/` for every primary chart. Validation must fail if any chart source table is missing, if source tables no longer reconcile to the Parquet/diagnostic pack, or if semantic labels confuse full-sample gains with paired common-grid metrics.
