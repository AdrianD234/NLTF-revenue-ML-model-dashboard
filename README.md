# NLTF Stage 1 Model Governance Dashboard

This Streamlit app turns a completed Stage 1 model-discovery run folder into an interactive governance dashboard for the NLTF revenue forecasting work.

The dashboard covers:

- recommended finalists by stream
- quarterly and annual MAPE
- candidate search landscape
- Schiff structural benchmark comparisons
- ensemble composition and component weights
- forecast errors by horizon bucket
- stress and horizon checks
- model inventory, feature audit, file status, and run-health diagnostics

Stage 1 is an actual-driver test: realised future explanatory variables are used to test whether the volume model maps drivers to the target well. It does not yet include the vintage macro/fuel input-forecast-error layer.

## Run

```powershell
conda activate agts312
cd "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Code\Stage 1 Model Governance Dashboard"
streamlit run app.py
```

If `streamlit` is not on the active environment path, use:

```powershell
python -m streamlit run app.py
```

The environment used for the Codex smoke test was:

```powershell
& "C:\Users\Adrian Desilvestro\OneDrive\Documents\GitHub\Capital_Programme_Optimiser\.venv\Scripts\python.exe" -m streamlit run app.py --server.headless true
```

## Default Run Discovery

The sidebar starts from:

```text
C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs
```

It recursively discovers `run_*` folders with readable outputs and excludes the currently live folder:

```text
run_20260519_150434
```

The current source-of-truth run used for validation is the latest finalist arbitration run:

```text
C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339
```

The dashboard can also be forced to the latest arbitration run with either environment variable:

```powershell
$env:MODEL_RUN_DIR = "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339"
$env:STAGE1_MODEL_RUN_DIR = $env:MODEL_RUN_DIR
```

Older balanced or exploratory runs may remain useful for historical comparison, but they are not the current finalist source of truth and must not be presented as the latest governance finalist run.

The bespoke solver parent can still be entered as a parent or manual path when reviewing non-arbitration runs:

```text
C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\bespoke_solver_stage1_outputs
```

## Supported Output Names

The loader supports both current and older names, including:

- `recommended_finalists.csv`
- `final_summary.csv` or `all_model_summary.csv`
- `quarterly_predictions.csv` or `all_quarterly_predictions.csv`
- `annual_predictions.csv` or `all_annual_predictions.csv`
- `paired_vs_schiff.csv` or `paired_finalist_vs_schiff.csv`
- `stress_tests.csv` or `finalist_stress_tests.csv`
- `ensemble_weights.csv`
- `feature_audit_log_real_only.csv`
- `variant_feature_counts.csv`
- `leaderboards.csv`
- `errors.csv`
- `autogluon_final_robust_all_streams_results.xlsx`
- `stage1_bespoke_solver_results.xlsx`

If a file is missing, the page that depends on it shows a warning and the rest of the dashboard keeps running.

## Layout

The app is intentionally self-contained:

```text
app.py
model_dashboard/
  data_loader.py
  labels.py
  metrics.py
  plots.py
  schema.py
  ui.py
```

The visual treatment borrows the clean header, KPI cards, restrained colours, and Plotly-white chart style from the capital programme optimiser dashboard, while replacing the backend with model-search result loading and governance metrics.

## Closed-Loop Testing

Use the PowerShell verification loop before declaring dashboard work complete:

```powershell
.\scripts\verify_dashboard.ps1
```

The script uses the Codex bundled Python runtime by default, runs `compileall`, runs the fast pytest/AppTest suite, checks or starts Streamlit on `http://localhost:8501`, then runs the Playwright browser test. The project-level agent instruction is in `AGENTS.md`.
