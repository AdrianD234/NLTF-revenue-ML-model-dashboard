# vNext production model pipeline — operator guide

The vNext pipeline (`pipeline/`) closes the PED and Heavy RUC forward-scoring
gaps with fit-and-save, parity-gated fixed finalists, built on the canonical
input history at `data/model_input_history` (schema-equal to the forecast
input template). The historical evidence pack at `data/dashboard_evidence_pack`
is never modified.

## Quick start (PowerShell)

```powershell
# Full pipeline (search is resumable; rerun if interrupted)
pwsh -File scripts\run_vnext_pipeline.ps1

# Stage by stage
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage search
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage select
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage finalize
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage scorecards
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage forecast -Workbook "templates\my_scenario.xlsx"
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage evidence

# Or directly
.\.venv\Scripts\python.exe -m pipeline.vnext_run all
.\.venv\Scripts\python.exe -m pipeline.vnext_run forecast --workbook "my_scenario.xlsx"

# Governance test suite (parity, anti-fake-forecast, determinism)
.\.venv\Scripts\python.exe -m pytest tests\test_vnext_parity.py -v
```

## Stages

| Stage | What it does | Outputs |
|---|---|---|
| `search` | Backtests the governed candidate grid (locked-spec refits + challengers) with rolling-origin, recursive-ylag evaluation. Resumable via `search_parts/` checkpoints. | `artifacts/vnext/<stream>/search_predictions.parquet`, `search_summary.parquet` |
| `select` | Scores every candidate on the exact stored evidence keysets (operational + paper), solves convex ensembles (SLSQP, zero-weight pruned), picks the finalist by paper-style horizon-mean MAPE. | `selection_leaderboard.parquet`, `selection.json` |
| `finalize` | Refits the finalist with per-origin state saving, exports training matrices and prediction feature rows, runs both parity gates. | `data/dashboard_evidence_pack_reproducibility/<stream>_vnext/` (fitted_state/, manifests, parity audit) |
| `scorecards` | Dual scorecards, horizon profiles, stress buckets, training-fit R2. | `scorecard_summary.parquet`, `horizon_profiles.parquet`, `stress_horizon.parquet`, `training_fit_*` |
| `forecast` | Scores a completed assumption workbook with the fixed finalists (no search). Builds a flat-forward baseline workbook if none supplied. | `artifacts/vnext/forecast_runs/<ts>_<scenario>/` |
| `evidence` | Registry, coefficients, importances, sensitivities, gap register, capability report, Light RUC state export, combined pack, audit report. | `<stream>_vnext/` packs, `artifacts/vnext/dashboard_evidence_pack_vnext/`, `artifacts/vnext/audit_report.md`, `forecast_runner_manifest.json` |

## Parity gates (all must pass before numeric forecasts)

1. **State replay** — every saved per-origin estimator replays its archived
   predictions from the saved prediction feature rows within `1e-6`.
2. **Recipe replay** — a fresh deterministic refit from the canonical history
   reproduces the archived validation predictions within `1e-6`.
3. **Runtime production-state gate** — on every forecast call, archived
   production training-fit predictions must replay from saved state within
   `1e-6`; otherwise the stream emits governed missing-value gaps.

After any environment change (Python/scikit-learn/numpy upgrade), rerun
`finalize` + `scorecards` and the test suite before relying on numeric output.

## Dashboard integration

`model_dashboard/vnext_forward_integration.py` resolves PED/Heavy capability
to the vNext scorer when the `*_vnext` packs are present and gates pass.
`evaluate_heavy_ruc_forward_scorer` / `evaluate_ped_forward_scorer` return the
vNext audit first; the legacy governance is unchanged as the fallback, and the
legacy finalists remain archived in the historical evidence pack.

The Forecast Builder (`run_forecast_workbook`) now emits numeric fixed-finalist
forecasts for all three streams when gates pass, with full scorer metadata
(`scorer_version`, `source_artifact_hashes`, `parity_status`,
`max_parity_delta`, `stored_replay_max_delta`, `capability_status`).

## Reproducibility contract (what is saved)

Per stream under `data/dashboard_evidence_pack_reproducibility/<stream>_vnext/`:
fitted estimators (per-origin + production, joblib with SHA256 manifest),
training feature matrices and exact prediction feature rows (column order =
fit order), validation and component predictions, training-fit predictions and
R2, scorecard summary, horizon profiles, stress buckets, model registry,
coefficients (original units), GBM feature importances, scenario
sensitivities, capability report, reproducibility gap register, parity audit,
and the audit report. Target transform: `y = ln(target)`, inverse `exp`;
lag recursion: `recursive_predicted`; seeds fixed at 42.
