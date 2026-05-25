# Governance Rules

## Current Finalists

Current finalists are selected from Parquet rows where `is_current_recommended` is true. The app must warn or record ambiguity if more than one current recommended row exists for a stream.

Legacy run-folder CSV/XLSX data cannot override current Parquet finalist values in the main dashboard path.

## Schiff Specification Benchmark

The default benchmark is the Schiff specification benchmark from `data/dashboard_evidence_pack`.

Legacy Schiff-style benchmark rows are retained only for review utilities. They must not be mixed into default Scenario Comparison, Schiff Benchmark, candidate frontier, horizon, stress, residual, annual, error-distribution, paired-comparison, or chart-source-table paths.

Schiff specification benchmark rows must exclude rows whose model identity indicates residual, blend, fixed blend, solver, convex solver, ensemble, top-k mean, top-k median, GBM, local, or similar non-benchmark challenger logic.

## Full-Sample vs Paired Metrics

Full-sample gain compares aggregate MAPE values:

```text
Schiff specification benchmark full-sample MAPE - finalist full-sample MAPE
```

Paired common-grid gain compares the same forecast pairs:

```text
Schiff specification benchmark common-grid MAPE - finalist common-grid MAPE
```

Paired win rate is also a common-pair metric.

Charts and tables must label these concepts explicitly. Under the Schiff specification benchmark, Light RUC has negative full-sample quarterly gain of about `-0.73 pp`, negative full-sample annual gain of about `-1.00 pp`, and negative paired common-grid gain of about `-0.76 pp`. That benchmark weakness must not be hidden by naming or by stale legacy values such as the old Light RUC `+2.40 pp` gain.

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
