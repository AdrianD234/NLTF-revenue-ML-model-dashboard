# Forecast Workflow

## Scope

The Forecast Builder is an operational forward-forecast workflow beside the governed historical evidence pack. It does not change existing finalists, MAPE/R2, KPI values, scenario outputs, stress outputs, diagnostics or chart-source calculations.

Forecast runs are isolated generated artifacts. They use fixed finalists only and never run a broad candidate search.

## Create A Blank Template

Default 20-quarter template:

```powershell
.\.venv\Scripts\python.exe scripts\create_forecast_input_template.py
```

This writes:

`templates/NLTF_forecast_input_template_20q.xlsx`

Other horizons:

```powershell
.\.venv\Scripts\python.exe scripts\create_forecast_input_template.py --quarters 1
.\.venv\Scripts\python.exe scripts\create_forecast_input_template.py --end-period 2050Q4
```

Generated filenames include the requested horizon, for example `NLTF_forecast_input_template_1q.xlsx` or `NLTF_forecast_input_template_to_2050Q4.xlsx`.

The historical backtest support window remains H1-H12. Longer templates, including a 2050Q4 template, are allowed for technical projection, but H13 onward is labelled as long-range extrapolation and must not be described as validated 2050 accuracy.

## Fill The Workbook

Open the workbook and fill only the user-entry columns on:

- `PED Inputs`
- `Light RUC Inputs`
- `Heavy RUC Inputs`

Leave the generated period/year/quarter/horizon columns and formula columns unchanged. Users may fill 1 quarter, all 20 default quarters, or a longer continuous horizon. Blank trailing rows are ignored.

The runner scores only valid rows present across all three sheets. Valid rows must begin at the first forecast quarter after the latest actual and must match across PED, Light RUC and Heavy RUC.

## Run A Forecast Pack

```powershell
.\.venv\Scripts\python.exe scripts\run_forecast_pack.py path\to\NLTF_forecast_input_template_basecase.xlsx --scenario-name basecase
```

Optional horizon checks:

```powershell
.\.venv\Scripts\python.exe scripts\run_forecast_pack.py path\to\workbook.xlsx --quarters 20
.\.venv\Scripts\python.exe scripts\run_forecast_pack.py path\to\workbook.xlsx --end-period 2050Q4
```

If `--scenario-name` is omitted, the scenario defaults from the workbook filename after stripping common prefixes such as `NLTF_forecast_input_template_`.

The runner writes:

`artifacts/forecast_runs/<timestamp>_<scenario_name>/`

with:

- `future_forecasts.parquet` and `.csv`
- `component_forecasts.parquet` and `.csv`
- `forecast_assumptions.parquet` and `.csv`
- `forecast_capability_report.parquet` and `.csv`
- `forecast_chart_rows.parquet` and `.csv`
- `forecast_run_manifest.json`
- `forecast_validation_report.md`

`forecast_chart_rows.*` is for display and export only. It combines historical actual rows with future forecast rows so charts can show the historical path and forecast start. Historical actuals are not written to `future_forecasts.*`.

## Streamlit Use

Open `Governance & Reproducibility`, then expand `Forecast Builder`.

The section supports:

- downloading the blank 20-quarter template;
- uploading one or more completed workbooks;
- editing scenario names per upload;
- validating all uploaded workbooks;
- calculating forecasts;
- viewing a combined scenario table and chart;
- seeing historical actuals, a forecast-start marker, and future scenario lines on the chart;
- filtering output by stream;
- filtering table rows by `All rows`, `Numeric forecasts only`, or `Governed gaps only`;
- viewing future forecast rows and component traces;
- viewing capability status by scenario and stream;
- downloading each scenario pack and a combined comparison pack.

## Combined Scenario Comparison

When multiple scenarios are uploaded, the dashboard writes:

`artifacts/forecast_runs/<timestamp>_scenario_comparison/`

with:

- `forecast_scenario_comparison.parquet`
- `forecast_scenario_comparison.csv`
- `forecast_scenario_capability_report.parquet`
- `forecast_scenario_capability_report.csv`
- `forecast_scenario_chart_rows.parquet`
- `forecast_scenario_chart_rows.csv`
- `scenario_input_delta_audit.parquet`
- `scenario_input_delta_audit.csv`
- `forecast_scenario_comparison_manifest.json`

The comparison pack is generated for user review only. It does not alter evidence packs or chart-source calculations.

If a workbook named `high_population` is used as the smoke fixture, the comparison pack writes `scenario_input_delta_audit.csv` showing that every required user input is 2% above base, including unemployment, prices and starting target lags. That fixture is not decision-grade and not population-only.

## Forward Scorer Governance

Current forward status:

- PED: numeric fixed-finalist forecast available from the parity-gated `PED__VNEXT_SOLVED_CONVEX_TOP2` saved production states when manifest SHA256 checks, parity audit and runtime state replay pass;
- Light RUC: numeric fixed-finalist forecast available from repo-local model-input history and the fixed OLS-base plus GBM-residual recipe;
- Heavy RUC: numeric fixed-finalist forecast available from the parity-gated `HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4` saved production states when manifest SHA256 checks, parity audit and runtime state replay pass.

Every forecast run and scenario comparison carries scorer governance fields including `scorer_version`, `source_artifact_hashes`, `parity_status`, `max_parity_delta`, `stored_replay_max_delta`, `horizon_support_status` and `horizon_support_note`.

If a required artifact, manifest hash check, parity audit or runtime state gate fails, the runner writes governed gaps instead of numbers. Governed gaps are expected governance output, not zero forecasts and not hidden failures.

The Forecast Builder chart plots numeric forecast lines, keeps governed-gap streams visible in the table and capability report if any gate fails, shows the forecast-start marker, and marks the H13 long-range-extrapolation boundary.

## Safety Checks

Forecast runs are generated under ignored artifact folders. User-filled workbooks must not be committed. The committed blank templates are the only workbooks intended for version control.
