# FORECAST_RUNNER_SPEC.lock.md

## Purpose

The forecast runner is a governed forward-forecast workflow for the NLTF dashboard. It accepts a completed 12-quarter assumption workbook, validates user inputs, builds finalist-aligned transforms, and writes a separate forecast-run pack under `artifacts/forecast_runs/<timestamp>/`.

It must never overwrite or recalculate the historical dashboard evidence pack.

## Invariants

- The production dashboard evidence source remains `data/dashboard_evidence_pack`.
- Forecast-run outputs live under `artifacts/forecast_runs/` and are ignored by git.
- Existing finalists, KPI values, MAPE/R2 values, scenario outputs, stress outputs, diagnostics and chart-source calculations are unchanged.
- The runner uses fixed finalist names only and must not run a broad candidate search.
- If repo-local fitted model state is unavailable, the runner writes a governed missing-capability gap instead of a fake forecast.

## Fixed Finalists

| Stream | Fixed finalist | Forward-run status |
|---|---|---|
| PED | `PED__RESCUE_static_annual_weighted_top12_capnone` | Governed gap unless fitted inner HPO/static-solver state is vendored |
| Light RUC | `dynamic_RESID_GBR_n150_d1_lr0.05_w36` | Governed gap unless OLS base and GBM residual fitted states are vendored |
| Heavy RUC | `HEAVY_RUC__RECON_STATIC_REBUILT` | Governed gap unless C1-C4 fitted component states are vendored |

## Required Outputs

Every run writes:

- `future_forecasts.parquet`
- `component_forecasts.parquet`
- `forecast_assumptions.parquet`
- `forecast_run_manifest.json`
- `forecast_validation_report.md`

CSV mirrors may be written inside the forecast-run directory for user download only. They are generated artifacts and must not feed dashboard evidence calculations.

## Manifest Contract

`forecast_run_manifest.json` must include:

- runner version;
- input workbook hash;
- latest known actual quarter;
- 12 forecast periods;
- validation status and messages;
- `fixed_finalists_only: true`;
- `broad_search_run: false`;
- `evidence_pack_modified: false`;
- `chart_sources_modified: false`;
- stream-level model capability status and gap code.

## Capability Rules

Forward forecasts are available only when repo-local artifacts include enough fitted model state to score new feature rows. Stored backtest predictions, scorecard rows, component replay rows, training-fit rows, weights alone or MAPE/R2 tables are not enough to forecast new quarters.

Current repo-local evidence proves replay and governance diagnostics, not full new-row fitted scoring for the three fixed finalists. The runner therefore emits governed gaps for all three streams until fitted finalist states are vendored.
