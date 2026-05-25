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
  -> model_dashboard.data_loader.load_parquet_dashboard
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
- `model_dashboard/data/diagnostics.py` owns diagnostic audit-table loading, diagnostic frame construction, and diagnostic ACF source tables.
- `model_dashboard/data/parquet_loader.py` and `chart_sources.py` are the next target homes for remaining loader responsibilities as the legacy monolith is reduced.
- `model_dashboard/data/legacy_loader.py` is review-only and must not replace the Parquet app path.

## Generated Outputs

Generated artifacts are deliberately ignored by Git. The verifier regenerates source tables, screenshots, logs, data reviews, and gate results for the active data root.

The repo should track source code, lock specs, documentation, tests, and small fixtures only.
