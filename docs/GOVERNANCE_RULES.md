# Governance Rules

## Current Finalists

Current finalists are selected from Parquet rows where `is_current_recommended` is true. The app must warn or record ambiguity if more than one current recommended row exists for a stream.

Legacy run-folder CSV/XLSX data cannot override current Parquet finalist values in the main dashboard path.

## Pure Schiff Benchmarks

Pure Schiff benchmark rows must be structural Schiff rows only. They must exclude rows whose model identity indicates residual, blend, fixed blend, solver, convex solver, ensemble, top-k mean, top-k median, GBM, local, or similar non-pure challenger logic.

## Full-Sample vs Paired Metrics

Full-sample gain compares aggregate MAPE values:

```text
Schiff full-sample MAPE - finalist full-sample MAPE
```

Paired common-grid gain compares the same forecast pairs:

```text
Schiff common-grid MAPE - finalist common-grid MAPE
```

Paired win rate is also a common-pair metric.

Charts and tables must label these concepts explicitly. If Light RUC shows a gain near `+2.40 pp`, that is full-sample quarterly gain and must not be labelled paired gain. The paired Light RUC quarterly comparison is negative in the current audit pack and must not be hidden by naming.

## Stress Buckets

Stress buckets must appear in this order:

1. `1-4 qtrs`
2. `5-8 qtrs`
3. `9-12 qtrs`
4. `2024+`
5. `2022-23`
6. `Annual`

Missing policy-stress buckets stay missing unless a valid diagnostic or reconciliation source explicitly enriches them. Plotly traces must not connect through missing stress values.

## Diagnostic Status

Diagnostic status uses `Pass`, `Watch`, and `Fail`.

Core dimensions:

- autocorrelation, using Durbin-Watson or a comparable Ljung-Box/no-severe-autocorrelation signal;
- stationarity, using ADF and KPSS where available;
- heteroscedasticity, using Breusch-Pagan and White where available;
- cointegration where applicable.

Normality is informative but not a hard override. If Jarque-Bera is caution/fail and the core dimensions pass, Overall should be `Watch`, not `Fail`.

## Chart Evidence

Each visible executive chart must have a matching CSV under `artifacts/chart_sources/` for the active run. The source table is the audit trail for chart values, labels, source columns, calculation basis, and notes.
