# FORECAST_SCENARIO_COMPARISON_SPEC.lock.md

## Purpose

Forecast scenario comparison combines two or more isolated forecast-run packs into a single review pack for the Forecast Builder UI. It is a forward-looking generated artifact and is not an input to the governed historical dashboard evidence pack.

## Inputs

Each input scenario is produced by `run_forecast_workbook` from a completed forecast input workbook.

Each scenario must carry:

- `scenario_name`;
- `workbook_filename`;
- `workbook_sha256`;
- `forecast_horizon_quarters`;
- `forecast_start_period`;
- `forecast_end_period`;
- `forecast_status`;
- `future_forecasts`;
- `forecast_capability_report`.

Scenario names are sanitized to lowercase letters, digits and underscores. Duplicate UI scenario names are suffixed with `_2`, `_3`, and so on.

## Output Folder

The comparison writer creates:

`artifacts/forecast_runs/<timestamp>_scenario_comparison/`

or a caller-provided output directory.

## Required Outputs

- `forecast_scenario_comparison.parquet`
- `forecast_scenario_comparison.csv`
- `forecast_scenario_capability_report.parquet`
- `forecast_scenario_capability_report.csv`
- `forecast_scenario_chart_rows.parquet`
- `forecast_scenario_chart_rows.csv`
- `forecast_scenario_comparison_manifest.json`

## Data Contract

`forecast_scenario_comparison.parquet` and `.csv` contain the row-wise union of scenario `future_forecasts`.

Required comparison columns include:

- `scenario_name`;
- `stream`;
- `stream_label`;
- `model`;
- `target_period`;
- `horizon`;
- `forecast`;
- `forecast_available`;
- `availability_status`;
- `gap_code`;
- `gap_reason`;
- `capability_status`;
- `scorer_version`;
- `source_artifact_hashes`;
- `parity_status`;
- `max_parity_delta`;
- `stored_replay_max_delta`;
- `fixed_finalist_only`;
- `broad_search_run`.

`forecast_scenario_capability_report.parquet` and `.csv` contain the row-wise union of scenario capability reports and must include `scenario_name`, stream identifiers, capability status, scorer version, parity status, artifact hashes, numeric row counts and gap codes.

`forecast_scenario_chart_rows.parquet` and `.csv` contain display rows with:

- `row_type` equal to `historical_actual` or `future_forecast`;
- `scenario_name`;
- `stream`;
- `stream_label`;
- `period`;
- `value`;
- `availability_status`.
- `capability_status`;
- `scorer_version`;
- `parity_status`.

Historical actual rows are de-duplicated by stream and period. Future forecast display rows keep missing `value` for governed gaps so the table/export can show the gap without plotting a fake forecast.

## Manifest Contract

`forecast_scenario_comparison_manifest.json` must include:

- comparison id;
- created timestamp;
- forecast runner version;
- scenario count;
- scenario records with name, run id, output directory, workbook metadata, horizon metadata and status;
- `fixed_finalists_only: true`;
- `broad_search_run: false`;
- `evidence_pack_modified: false`;
- `chart_sources_modified: false`;
- output file list.

## UI Contract

The Forecast Builder UI must:

- accept multiple workbook uploads;
- default each scenario name from the workbook filename suffix;
- allow each scenario name to be edited before validation or calculation;
- validate all uploaded workbooks;
- calculate all scenarios into isolated scenario run folders;
- render a combined table and chart;
- use `scenario_name` to distinguish line color/style;
- allow stream filtering across the combined table and chart;
- show capability status by scenario and stream;
- plot historical actuals as a distinct grey line;
- plot future numeric forecasts in scenario styles after the forecast-start marker;
- keep governed-gap streams visible in the table/capability report;
- show a governed-gap annotation when a selected stream has historical actuals but no numeric future forecast;
- provide an All/Numeric/Governed-gap row filter for the forecast table;
- offer each scenario pack and the combined comparison pack for download.

## Governance Invariants

- Scenario comparison must not modify `data/dashboard_evidence_pack`.
- Scenario comparison must not modify `artifacts/chart_sources`.
- Scenario comparison must not recalculate historical finalists, MAPE/R2, diagnostics, scenario, stress or benchmark values.
- Light RUC numeric forecasts must come from the fixed finalist forward scorer.
- PED and Heavy RUC governed gaps must remain explicit until executable forward scorers are available and parity-tested; current statuses are `parity_failed` for PED and `insufficient_artifacts` for Heavy RUC.
