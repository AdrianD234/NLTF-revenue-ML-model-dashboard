# Stage 1 Dashboard Evidence Pack - Schiff Specification v2

This is the Parquet-first evidence pack for the NLTF Stage 1 Governance Dashboard.

This version replaces the previous default pure-Schiff benchmark rows with the final Schiff specification benchmark rows rebuilt from the paper specification and scored on the current evidence pack. User-facing label: **Schiff specification benchmark**.

## Required dashboard rule

Default app pages must use this pack only. Legacy run folders, old Schiff-style rows and fixtures must not be mixed into the default four-page dashboard.

## Key files

- `data/finalists.parquet`: current finalist rows.
- `data/schiff_benchmark.parquet`: Schiff specification benchmark rows.
- `data/residual_predictions.parquet`: row-level finalist and Schiff specification predictions.
- `data/horizon_profiles.parquet`: true 1-12 horizon profiles from row-level predictions, no interpolation.
- `data/scenario_comparison.parquet`: finalist vs Schiff specification full-sample and paired metrics.
- `data/stress_horizon.parquet`: stress buckets for finalists and Schiff specification.
- `data/candidate_cone.parquet`: candidate cone with Schiff specification anchors.

## Important governance note

The previous Heavy RUC Schiff-style benchmark produced a ~20.5% horizon-12 MAPE. This v2 pack replaces that default benchmark with the Schiff final specification benchmark; Heavy RUC Schiff specification horizon-12 MAPE should be materially lower. Keep old Schiff-style rows only in legacy/audit views, not the default benchmark.
