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
- `forecast_run_manifest.json`
- `forecast_validation_report.md`

## Streamlit Use

Open `Governance & Reproducibility`, then expand `Forecast Builder`.

The section supports:

- downloading the blank 20-quarter template;
- uploading one or more completed workbooks;
- editing scenario names per upload;
- validating all uploaded workbooks;
- calculating forecasts;
- viewing a combined scenario table and chart;
- filtering output by stream;
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
- `forecast_scenario_comparison_manifest.json`

The comparison pack is generated for user review only. It does not alter evidence packs or chart-source calculations.

## Governed Gaps

The current repo contains replay predictions, training-fit rows, component traces and governance metrics. It does not contain all executable finalist scorers needed to score new assumption rows for every stream.

Current forward status:

- PED: governed gap, `ped_inner_hpo_static_solver_forward_scorer_missing`;
- Light RUC: numeric fixed-finalist forecast available from repo-local model-input history and the OLS-base plus GBM-residual recipe;
- Heavy RUC: governed gap, `heavy_ruc_component_forward_scorers_missing`.

Governed gaps are expected governance output, not zero forecasts and not hidden failures.

## Safety Checks

Forecast runs are generated under ignored artifact folders. User-filled workbooks must not be committed. The committed blank templates are the only workbooks intended for version control.
