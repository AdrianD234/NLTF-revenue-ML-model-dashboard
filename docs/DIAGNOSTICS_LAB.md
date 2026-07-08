# Diagnostics Lab

An adaptive model-search pipeline that answers: *what MAPE do we give up to make a
stream's finalist pass the whole Diagnostic Pass Matrix?* Results and analysis live in
`artifacts/diagnostics_lab/` (headline: `frontier_report.md`).

## Pieces

- `pipeline/diaglab_battery.py` — governance-replica diagnostic battery. Reproduces the
  evidence pack's statistics to full float precision (residual scope: horizon-1 rolling-origin
  residuals on the operational grid; per-stream residual basis and heteroskedasticity
  regressors; exact threshold rules). Pinned by `tests/test_diaglab_battery.py`.
- `pipeline/diaglab_arms.py` — remedy arms: `arx` (dynamic OLS), `glsar` (AR-error GLS),
  `sarimax`, `ecm`, `light_recipe` (the production Light RUC two-stage recipe), plus composable
  WLS (`covid_down`, `regime_var`) and auto-detected pulse-dummy layers. All fit in log space and
  backtest on the governed origin/target grids via `pipeline/vnext_core.py` helpers.
- `pipeline/diaglab_orchestrator.py` — one adaptive round per invocation: seeds per-arm grids,
  ranks candidates lexicographically (core passes, then paper-grid horizon-mean MAPE), composes
  the remedy matching whichever test still fails, retires stalled arms, and writes
  `round_N/{candidates.parquet, report.md}` + `state.json` for human/Claude steering between rounds.

## Running

```powershell
.venv\Scripts\python.exe scripts/run_diagnostics_lab.py --stream PED            # next round
.venv\Scripts\python.exe scripts/run_diagnostics_lab.py --stream PED --steer s.json
.venv\Scripts\python.exe scripts/run_diagnostics_lab.py --stream PED --export   # winner artifacts
.venv\Scripts\python.exe scripts/run_diagnostics_lab.py --stream PED --reset    # start over
```

Steer JSON keys: `arm_quotas` (per-arm config budget), `retire_arms`, `extra_specs`,
`max_configs`.

## Honesty rules

- A candidate "passes" only on the same residual scope, formulations and thresholds governance
  uses; Jarque-Bera stays advisory.
- MAPE deltas are against the finalist on identical paper-grid pairs.
- Ljung-Box(8) is reported next to DW because DW is biased toward 2 for specs with lagged
  dependent variables.
- Everything is deterministic (no random search; `RANDOM_STATE=42` for the GBM arm).

Governed packs, finalists and the promoted Revenue Outlook runtime are untouched; the lab writes
only under `artifacts/diagnostics_lab/`.
