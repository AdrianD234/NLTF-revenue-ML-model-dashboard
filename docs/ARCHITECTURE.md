# Architecture

The dashboard runtime has one governed data path:

1. Resolve a user-supplied data root from CLI, environment, or UI.
2. Locate the curated candidate Parquet pack and adjacent diagnostic audit files.
3. Normalize those inputs into a `DashboardData` object.
4. Build page-specific frames and mandatory source tables.
5. Render Streamlit pages from those frames only.
6. Validate the browser output with Playwright.

## Data Flow

```text
Parquet candidate pack
  + diagnostic audit support files
  -> model_dashboard.data.locate
  -> model_dashboard.data.transforms
  -> model_dashboard.data.parquet_loader.load_parquet_dashboard
  -> DashboardData
  -> chart source tables
  -> Plotly figures
  -> Streamlit pages
```

`artifacts/data_source_manifest.json` records the requested data root, search roots, resolved Parquet path, optional metadata/CSV mirror, diagnostic support files, and source mode for every load.

## Runtime Boundaries

- `app.py` consumes `DashboardData`; it must not silently fall back to old run folders.
- `model_dashboard/data/config.py` owns runtime defaults and environment variable lookup.
- `model_dashboard/data/locate.py` owns file discovery.
- `model_dashboard/data/transforms.py` owns Parquet schema aliases and candidate normalization.
- `model_dashboard/data/parquet_loader.py` owns the governed Parquet load path, finalist/Schiff frame assembly, stress/horizon/ensemble frame derivation, source manifest writes, and reconciliation source-table export.
- `model_dashboard/data/diagnostics.py` owns diagnostic audit-table loading, diagnostic frame construction, and diagnostic ACF source tables.
- `model_dashboard/data/chart_sources.py` owns the 16 primary chart source-table builders and export contract.
- `model_dashboard/data/legacy_loader.py` owns review-only run-folder and curated CSV/XLSX loading; it must not replace the Parquet app path.
- `model_dashboard/data_loader.py` and `model_dashboard/chart_sources.py` are compatibility facades for existing imports and should not regain transformation, discovery, Parquet, diagnostics, source-table, or legacy implementation logic.

## Generated Outputs

Generated artifacts are deliberately ignored by Git. The verifier regenerates source tables, screenshots, logs, data reviews, and gate results for the active data root.

The repo should track source code, lock specs, documentation, tests, and small fixtures only.
