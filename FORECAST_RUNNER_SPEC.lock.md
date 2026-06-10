# FORECAST_RUNNER_SPEC.lock.md

## Purpose

The forecast runner is a governed forward-forecast workflow for the NLTF dashboard. It accepts one completed variable-horizon assumption workbook per scenario, validates user inputs, builds finalist-aligned transforms, and writes separate forecast-run packs under `artifacts/forecast_runs/<timestamp>_<scenario_name>/`.

It must never overwrite or recalculate the historical dashboard evidence pack.

## Invariants

- The production dashboard evidence source remains `data/dashboard_evidence_pack`.
- Forecast-run outputs live under `artifacts/forecast_runs/` and are ignored by git.
- Existing finalists, KPI values, MAPE/R2 values, scenario outputs, stress outputs, diagnostics and chart-source calculations are unchanged.
- The runner uses fixed finalist names only and must not run a broad candidate search.
- If repo-local fitted model state is unavailable, the runner writes a governed missing-capability gap instead of a fake forecast.
- Light RUC may produce numeric fixed-finalist forecasts only from the repo-local model-input history and fixed OLS-base plus GBM-residual recipe.
- PED and Heavy RUC remain governed forward-scoring gaps until executable new-row scorers are repo-local and parity-tested.

## Fixed Finalists

| Stream | Fixed finalist | Forward-run status |
|---|---|---|
| PED | `PED__RESCUE_static_annual_weighted_top12_capnone` | Governed gap: `ped_inner_hpo_static_solver_forward_scorer_missing` |
| Light RUC | `dynamic_RESID_GBR_n150_d1_lr0.05_w36` | Numeric fixed-finalist forecast when repo-local Light RUC history, registry and `scikit-learn` are available |
| Heavy RUC | `HEAVY_RUC__RECON_STATIC_REBUILT` | Governed gap: `heavy_ruc_component_forward_scorers_missing` |

## Horizon And Validation Contract

- The runner infers the scored horizon from valid rows present in the workbook.
- Valid rows are rows with all required user-entry columns populated with positive numeric values.
- Blank trailing rows are ignored.
- Valid rows must start at the first generated forecast quarter after the latest known actual and must be continuous with no gaps.
- PED, Light RUC and Heavy RUC sheets must contain the same continuous forecast periods.
- Optional CLI expectations `--quarters N` and `--end-period YYYYQn` add an explicit horizon check; they do not change workbook values.

## Required Outputs

Every scenario run writes:

- `future_forecasts.parquet`
- `future_forecasts.csv`
- `component_forecasts.parquet`
- `component_forecasts.csv`
- `forecast_assumptions.parquet`
- `forecast_assumptions.csv`
- `forecast_capability_report.parquet`
- `forecast_capability_report.csv`
- `forecast_chart_rows.parquet`
- `forecast_chart_rows.csv`
- `forecast_run_manifest.json`
- `forecast_validation_report.md`

CSV mirrors are generated artifacts for user download only. They must not feed dashboard evidence calculations.

`forecast_chart_rows.*` is a display/export artifact. It may include `historical_actual` rows sourced from `data/model_input_history` or governed evidence-pack actuals, plus `future_forecast` rows copied from the isolated future forecast output. Historical rows must never be written into `future_forecasts.*` and must not change forecast horizon metadata.

## Manifest Contract

`forecast_run_manifest.json` must include:

- runner version;
- scenario name;
- input workbook filename and SHA256 hash;
- latest known actual quarter;
- forecast periods;
- forecast horizon, start period and end period;
- validation status and messages;
- `fixed_finalists_only: true`;
- `broad_search_run: false`;
- `evidence_pack_modified: false`;
- `chart_sources_modified: false`;
- numeric and governed-gap stream lists;
- stream-level model capability status and gap code.
- output-file entries for generated display artifacts such as `forecast_chart_rows.*`.

## Scenario Comparison Contract

The runner can combine multiple scenario run results into:

`artifacts/forecast_runs/<timestamp>_scenario_comparison/`

with:

- `forecast_scenario_comparison.parquet`
- `forecast_scenario_comparison.csv`
- `forecast_scenario_capability_report.parquet`
- `forecast_scenario_capability_report.csv`
- `forecast_scenario_chart_rows.parquet`
- `forecast_scenario_chart_rows.csv`
- `forecast_scenario_comparison_manifest.json`

The combined pack must preserve each scenario's `scenario_name`, workbook metadata, horizon metadata and capability status. It is a generated comparison artifact and does not alter governed evidence-pack or chart-source calculations.

Combined chart rows must de-duplicate `historical_actual` rows by stream and period while preserving every scenario's `future_forecast` rows.

## Capability Rules

Forward forecasts are available only when repo-local artifacts include enough fitted model state or a parity-tested scoring recipe to score new feature rows. Stored backtest predictions, scorecard rows, component replay rows, training-fit rows, weights alone or MAPE/R2 tables are not enough to forecast new quarters.

Current repo-local evidence supports Light RUC fixed-finalist forward scoring from the vendored model-input history. Current repo-local PED and Heavy RUC evidence proves replay and governance diagnostics, not full new-row fitted scoring, so those streams emit governed gaps for every requested forecast row.
