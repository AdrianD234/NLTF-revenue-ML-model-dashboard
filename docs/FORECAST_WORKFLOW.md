# Forecast Workflow

## Scope

The Forecast Builder is an operational forward-forecast workflow beside the governed historical evidence pack. It does not change existing finalists, MAPE/R2, KPI values, scenario outputs, stress outputs, diagnostics or chart-source calculations.

## Create A Blank Template

```powershell
.\.venv\Scripts\python.exe scripts\create_forecast_input_template.py
```

This writes:

`templates/NLTF_forecast_input_template_12q.xlsx`

## Fill The Workbook

Open the workbook and fill only the user-entry columns on:

- `PED Inputs`
- `Light RUC Inputs`
- `Heavy RUC Inputs`

Leave the generated period/year/quarter/horizon columns and formula columns unchanged. The README sheet states the forecast window and workbook rules.

## Run A Forecast Pack

```powershell
.\.venv\Scripts\python.exe scripts\run_forecast_pack.py path\to\completed_workbook.xlsx
```

The runner writes:

`artifacts/forecast_runs/<timestamp>/`

with:

- `future_forecasts.parquet`
- `component_forecasts.parquet`
- `forecast_assumptions.parquet`
- `forecast_run_manifest.json`
- `forecast_validation_report.md`
- optional CSV mirrors for download.

## Streamlit Use

Open `Governance & Reproducibility`, then expand `Forecast Builder`.

The section supports:

- downloading the blank 12-quarter template;
- uploading a completed workbook;
- validating inputs;
- calculating forecasts or governed gaps;
- filtering output by stream;
- viewing future forecast rows and component traces;
- downloading the forecast-run pack.

## Governed Gaps

The current repo contains replay predictions, training-fit rows, component traces and governance metrics. It does not contain all fitted finalist model states needed to score new assumption rows.

When fitted state is missing, the runner writes explicit gap rows:

- PED: `ped_inner_hpo_static_solver_fitted_state_missing`
- Light RUC: `light_ruc_ols_gbm_fitted_state_missing`
- Heavy RUC: `heavy_ruc_component_fitted_state_missing`

These gaps are expected governance output, not zero forecasts and not hidden failures.

## Safety Checks

Forecast runs are generated under ignored artifact folders. User-filled workbooks must not be committed. The committed blank template is the only workbook intended for version control.
