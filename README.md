# NLTF Revenue Modelling — Stage 1 Governance Dashboard

Streamlit dashboard and production model pipeline for the NLTF Stage 1
revenue streams (PED VKT per capita, Light RUC volume, Heavy RUC volume).

**See [`REPO_GUIDE.md`](REPO_GUIDE.md) for the canonical repository map,
naming conventions and feed-through points.**

## Current state (evidence pack v7, vNext finalists)

| Stream | Finalist | Paper-style horizon MAPE | Paper annual MAPE |
|---|---|---:|---:|
| PED VKT per capita | `PED__VNEXT_SOLVED_CONVEX_TOP2` | 3.13% | 1.95% |
| Light RUC volume | `dynamic_RESID_GBR_n150_d1_lr0.05_w36` | 5.36% | 1.27% |
| Heavy RUC volume | `HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4` | 2.29% | 1.68% |

All three streams beat the Schiff specification benchmark (3/3 Promote) and
are **production forward-scoreable**: fitted state is saved, archived
predictions replay exactly (parity 1e-6 gates on every score call), and the
Forecast Builder produces numeric forecasts from completed assumption
workbooks for every stream.

## Run the dashboard

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

Pages: Overview, Diagnostics, Scenario Comparison, Schiff Benchmark,
Governance & Reproducibility. Data source: `data/dashboard_evidence_pack`
(Parquet-first, governed; never edited by hand).

## Run the model pipeline

```powershell
pwsh -File scripts\run_vnext_pipeline.ps1               # full: search -> evidence
pwsh -File scripts\run_vnext_pipeline.ps1 -Stage forecast -Workbook my_scenario.xlsx
```

Details: `docs/VNEXT_PIPELINE.md`. Promotion of new finalists into the
evidence pack: `scripts/promote_vnext_to_evidence_pack.py` (run `--check`
first; previous pack is backed up automatically).

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_vnext_parity.py -v
pwsh -File scripts\verify_dashboard.ps1 -Python .\.venv\Scripts\python.exe -DataRoot data\dashboard_evidence_pack -Port 8501
```

## Runtime data configuration

The dashboard's default data source is the curated Parquet dashboard pack at
`data/dashboard_evidence_pack`. Legacy run-folder CSV/XLSX outputs are retained only for review
via the Advanced controls and never feed governed charts.

Environment overrides (resolved in this order):

- `DASHBOARD_EVIDENCE_PACK_ROOT` - explicit evidence-pack root.
- `STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT` - legacy alias for the same override.
- `MODEL_DIAGNOSTIC_DATA_ROOT` - optional diagnostics data root for review tooling.

## Governance in one paragraph

Models are selected on the exact stored evidence keysets under two labelled
scorecards (paper-style horizon MAPE, operational pooled MAPE), fitted state
is saved and hash-manifested, every forecast call re-verifies that archived
training-fit predictions replay from the saved state within 1e-6, and any
gate failure produces governed missing values - never fabricated numbers.
Archived legacy finalists and the v6 evidence pack are retained as immutable
lineage (`REPO_GUIDE.md` lists what is current vs archived).
