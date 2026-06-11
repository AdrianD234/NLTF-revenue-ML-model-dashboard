# Repository Guide

The canonical map of this repository: what each directory is for, its
lifecycle, and where changes feed through. If a folder or file is not
described here, it is runtime scratch (git-ignored) and safe to delete.

## Lifecycle vocabulary

- **current** — drives the dashboard, forecasts and governance views.
- **archived** — immutable lineage kept for audit; never feeds current charts.
- **scratch** — regenerated on demand; git-ignored.

## Feed-through points (change these, everything follows)

| Change | Where |
|---|---|
| Current finalist / reproducibility pack per stream | `model_dashboard/governance_constants.py` (`CURRENT_REPRO_PACK_DIRS`; finalist names resolve from pack manifests) |
| Pipeline output generation suffix | `pipeline/__init__.py` (`GENERATION`) |
| Evidence-pack values | `scripts/promote_vnext_to_evidence_pack.py` (rebuilds every finalist-dependent table; verify first with `--check`) |
| Stream labels / score-basis labels | `model_dashboard/governance_constants.py`, `model_dashboard/score_basis.py` |

A finalist promotion = run the pipeline (search → select → finalize →
scorecards → evidence), update `CURRENT_REPRO_PACK_DIRS` + `GENERATION` if
the generation changed, run the promotion script, then the validators.

## Directory map

| Path | Lifecycle | Purpose |
|---|---|---|
| `app.py` | current | Streamlit dashboard (5 pages). |
| `model_dashboard/` | current | Dashboard library: loaders, charts, labels, score-basis, R2 ladder, diagnostics, forecast runner, vNext integration, `governance_constants.py` (single source of naming truth). |
| `pipeline/` | current | Production model pipeline (vNext generation): feature engine, candidate grids, orchestrator CLI, fixed-finalist forward scorer, evidence emitters. Run via `scripts/run_vnext_pipeline.ps1` or `python -m pipeline.vnext_run`. |
| `scripts/` | current | Build/validate/export utilities. Key: `promote_vnext_to_evidence_pack.py`, `run_vnext_pipeline.ps1`, `verify_dashboard.ps1`, `validate_*.py`. |
| `tests/` | current | Pytest suite incl. Playwright e2e (browser tests need a local run via `verify_dashboard.ps1`). `test_vnext_parity.py` enforces the production-reproducibility contract. |
| `data/dashboard_evidence_pack/` | current | Governed evidence pack **v7 (vNext finalists)** — the only data source for dashboard charts. `manifest.json` carries the promotion record. |
| `data/dashboard_evidence_pack_v6_backup/` | archived | Byte-exact pre-promotion pack; restore = copy over the pack. Git-ignored (local only). |
| `data/dashboard_evidence_pack_reproducibility/ped_vnext`, `heavy_ruc_vnext` | current | Saved fitted state, matrices, parity audits and Page-5 audit tables for the current PED / Heavy RUC finalists. |
| `data/dashboard_evidence_pack_reproducibility/light_ruc` | current | Governed pack for the (unchanged) Light RUC fixed recipe; `light_ruc_vnext` holds its production-state export. |
| `data/dashboard_evidence_pack_reproducibility/ped`, `heavy_ruc`, `ped_inner_hpo` | archived | Legacy finalists' replay evidence (historically reproducible, not forward-scoreable). |
| `data/model_input_history/` | current | Canonical input basis (schema-equal to the forecast template); actuals verified identical to the evidence pack. |
| `templates/` | current | Governed forecast input templates (12q/20q). |
| `docs/` | current | Operator docs: `VNEXT_PIPELINE.md`, `SCHIFF_SPECIFICATION_BENCHMARK.md`, `ARCHITECTURE.md`, etc. `BASELINE_ACCEPTANCE.md` is a superseded historical record (banner inside). |
| `artifacts/` | scratch | Regenerated outputs: chart-source CSVs, validation reports, screenshots, pipeline run outputs (`artifacts/vnext/`), forecast runs. Only `heavy_ruc_forward_parity_debug/` is committed (legacy parity evidence). |
| `test-output/`, `.uv-cache/`, `__pycache__/` | scratch | Local caches and test scratch; safe to delete. |
| `*.lock.md` (repo root) | mixed | Governance lock files — see index below. |

## Lock-file index

Lock files are frozen specs from governed work passes. Active ones constrain
behaviour today; historical ones document accepted past states.

| Lock | Status |
|---|---|
| `FORECAST_FORWARD_SCORER_SPEC.lock.md` | historical (legacy finalists) — **superseded by** `FORECAST_FORWARD_SCORER_VNEXT_AMENDMENT.lock.md` |
| `FORECAST_FORWARD_SCORER_VNEXT_AMENDMENT.lock.md` | **active** — vNext succession rules, parity gates, promotion record |
| `FORECAST_RUNNER_SPEC.lock.md`, `FORECAST_INPUT_TEMPLATE_SPEC.lock.md`, `FORECAST_SCENARIO_COMPARISON_SPEC.lock.md` | active (runner/template contracts; capability rows superseded by the amendment) |
| `PARQUET_DASHBOARD_DATA_SPEC.lock.md`, `DIAGNOSTIC_DATA_SPEC.lock.md`, `DASHBOARD_PAGE_CHART_SPEC.lock.md`, `PAGE5_GOVERNANCE_VISUAL_SPEC.lock.md` | active (data/chart contracts) |
| Remaining `*.lock.md` | historical work-pass records (visual/perf/validation sprints) |

## Naming conventions

- Streams: `PED`, `LIGHT_RUC`, `HEAVY_RUC`; labels via `STREAM_LABELS`.
- Score bases: `schiff_paper_horizon_mean` (default), `current_grid_operational_pooled`; never mix unlabelled.
- Reproducibility packs: `<stream>_<generation>` (current generation: `vnext`).
- Model ids: `<STREAM>__<GENERATION>__<feature_set>__<kind>_<params>__<ylag>__<window>`; ensembles `<STREAM>__VNEXT_SOLVED_CONVEX_TOPk`.
- Parity tolerance everywhere: `1e-6` (`governance_constants.PARITY_TOLERANCE`).

## Verification entry points

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_vnext_parity.py -v          # parity + anti-fake-forecast
.\.venv\Scripts\python.exe scripts\validate_dashboard_data.py               # pack invariants
.\.venv\Scripts\python.exe scripts\validate_chart_sources.py                # all 16 charts
pwsh -File scripts\verify_dashboard.ps1 -Python .\.venv\Scripts\python.exe -DataRoot data\dashboard_evidence_pack -Port 8501   # full gate suite incl. browser
```
