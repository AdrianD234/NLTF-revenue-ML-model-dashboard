# Alternate engine: "AR(1) model" (default) vs "ML ensemble"

The dashboard can run on either of two model engines. The engine is a per-session
setting (radio in the filter strip's **More** popover on the executive pages, and in the
Revenue Outlook controls panel); the masthead page chip always shows the active engine.

| | AR(1) model (default) | ML ensemble |
|---|---|---|
| PED finalist | `PED__DIAGLAB__B__glsar__ylag1__ar1__wexp` — GLSAR AR(1)-error regression, Schiff-style levels + one lagged log target | `PED__VNEXT_SOLVED_CONVEX_TOP2` — convex GBM ensemble |
| PED paper-grid MAPE | 3.22% quarterly / 2.17% annual | 3.13% / 1.95% |
| PED diagnostics | **all six core tests pass**; Jarque-Bera advisory Watch → Overall **Watch** | Durbin-Watson + White **Fail** → Overall **Fail** |
| Light RUC / Heavy RUC | identical finalists under both engines | — |

## Architecture: engine = pack selection

No chart special-cases anything. The engine choice maps only to pack directories:

| Surface | AR(1) model | ML ensemble |
|---|---|---|
| Evidence pack | `data/engine_ar1/dashboard_evidence_pack/` | `data/dashboard_evidence_pack/` |
| Revenue Outlook runtime | `data/engine_ar1/current_revenue_outlook/` | `data/current_revenue_outlook/` |
| PED reproducibility pack | `data/dashboard_evidence_pack_reproducibility/ped_ar1/` | `.../ped_vnext/` |

Resolvers live in `model_dashboard/engine.py` (`active_engine()`,
`engine_evidence_root()`, `engine_revenue_outlook_dir()`, `engine_repro_pack_dirs()`);
`model_dashboard/governance_constants.py` exposes the engine-aware
`current_finalist(stream, engine)` / `current_repro_pack_dirs(engine)`. All heavy loaders
are keyed on path + signature, so both engines cache side by side and switching is instant
after first load.

Default: **AR(1)**; override with env `DASHBOARD_ENGINE_DEFAULT=ensemble` (the incumbent
runtime rebuild CLI pins this automatically). `DASHBOARD_EVIDENCE_PACK_ROOT` still wins
over the engine for the evidence root when set explicitly.

## How the AR(1) packs are minted (deterministic, incumbent packs untouched)

```powershell
.venv\Scripts\python.exe scripts/build_ar1_engine_state.py     # ped_ar1 repro pack (fit + parity)
.venv\Scripts\python.exe scripts/build_ar1_runtime_pack.py     # Revenue Outlook runtime pack
.venv\Scripts\python.exe scripts/build_ar1_evidence_pack.py    # evidence pack
```

- The engine state is plain JSON (betas, rho, features); a refit-from-committed-inputs
  gate (`pipeline/ar1_engine.state_replay_max_delta`) runs before every forecast and must
  match to 1e-6 — the linear analog of the vNext joblib parity gate.
- The runtime pack passes the standard scenario-input **replay gate** with
  `engine="ar1"`: `replay_forecast_from_scenario_inputs` re-scores PED with the AR(1)
  engine from the committed workbook-hashed scenario inputs and the committed rows must
  match exactly. Manifest carries `engine: ar1` + fresh output hashes.
- The evidence pack is template-merged from the incumbent: PED finalist rows are replaced
  on identical (score_basis, origin, target_period) grids; diagnostics recomputed with the
  governance-replica battery (`pipeline/diaglab_battery.py`); Light/Heavy rows
  byte-identical. PED SHAP/scenario-sensitivity rows are dropped (linear engine — the
  coefficients table is the interpretability surface).

## Known level shifts under AR(1) (expected, not bugs)

The AR(1) PED path is more conservative: FY2050 PED VKT/capita 5,155 vs 5,799, pulling
Total NLTF FY2050 to ~$12.8b vs ~$13.5b. The λ-migration split moves slightly with PED
(by design); Heavy RUC and the MBU26 official comparator are engine-invariant (pinned in
`tests/test_ar1_engine.py`).

## Tests

`tests/test_ar1_engine.py` (determinism, parity, pack integrity, engine invariants),
`tests/test_engine_switcher.py` (default, both-engine page sweep, flip consistency,
matrix follows engine), `tests/test_view_invariant_sweep.py` (all structural invariants
parametrized over BOTH runtime packs).
