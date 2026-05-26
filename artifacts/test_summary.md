# Test Summary

Status: **passed** for the v6 balanced-frontier evidence-pack migration, score-basis governance, semantic chart reconciliation, visual conformance and browser verification pass.

## Data Root Used

`data\dashboard_evidence_pack`

The default dashboard source is the repo evidence pack at `data/dashboard_evidence_pack`. Legacy run folders, mini fixtures, old CSV/XLSX artifacts and previous diagnostic-pack paths are review-only and are not used by the default four-page dashboard.

Slim v6 source root used for the current pack:

`C:\Users\Adrian Desilvestro\Downloads\stage1_dashboard_evidence_pack_dual_scorecard_gbm_light_v6_balanced_frontier\dashboard_evidence_pack`

The repo pack contains only root metadata files, `docs/`, and governed `data/*.parquet` files. Raw `sources/`, `tables_csv/`, logs, screenshots and CSV mirrors are intentionally absent from the committed evidence pack.

## Latest Full Verifier Command

```powershell
pwsh -File scripts\verify_dashboard.ps1 -Python ".\.venv\Scripts\python.exe" -DataRoot "data\dashboard_evidence_pack" -Port 8501
```

## Results

| Check | Result |
| --- | --- |
| Compile | Passed |
| Full pytest | 128 passed, 46 skipped, 39 deselected |
| Schema inspection | Passed against `dashboard_evidence_pack_v6_balanced_frontier` and 14 required Parquet tables |
| Data validation | Passed |
| Chart source validation | Passed for 16 primary chart source tables plus the Overview KPI source table |
| Semantic label validation | Passed |
| Chart-data reconciliation tests | 18 passed |
| Per-chart source-table tests | 7 passed |
| Existing browser e2e | 38 passed |
| Mandatory frontend interaction Playwright suite | 5 passed |
| Visual conformance validation | Passed |
| 100-gate validation | 100 passed, 0 failed, 0 supporting failures |
| 120-gate validation | 120 passed, 0 failed |
| Backlog | No unchecked items |

## V6 Score-Basis And Frontier Checks

- `manifest.json` schema is `dashboard_evidence_pack_v6_balanced_frontier`.
- Default score basis is `schiff_paper_horizon_mean` / Paper-style horizon MAPE.
- Operational score basis is `current_grid_operational_pooled` and is exposed only through the explicit Score Basis selector.
- Source tables include `score_basis` and `score_basis_label`.
- Paper-style and operational metrics are not mixed silently.
- Light RUC operational annual weakness versus Schiff remains visible as an annual-watch note.
- Overview Stress and Horizon Checks defaults to `1-4 qtrs`, `5-8 qtrs`, `9-12 qtrs` and `Annual`; policy windows remain available in source data but are excluded from the Paper-style Overview chart.
- Candidate Search Frontier explicitly describes the balanced all-stream frontier view: visual frontier samples are anchored to current finalists and Schiff specification benchmarks and excluded from governance scoring.
- Candidate Search Frontier plots 400 rows with balanced stream counts: PED 132, Light RUC 136 and Heavy RUC 132.
- Candidate Search Frontier source rows carry `frontier_sample_class` and `frontier_sample_note`; non-frontier chart sources are validated to exclude visual frontier sample rows.
- Ensemble Composition renders all three stream finalists from governed component rows, not demo weights.
- Overview KPI Cards source table reconciles the Annual KPI benchmark to `schiff_benchmark.parquet` `annual_mape`: Schiff annual mean 5.06%, finalist annual mean 1.79%, gain 3.27 pp.
- Ensemble Composition is browser-tested under both Paper-style horizon MAPE and Operational pooled MAPE so score-basis selection cannot hide PED or Heavy RUC components.

## Default Paper-Style Finalists

- PED VKT per capita: quarterly MAPE 3.24%, annual MAPE 2.03%; current finalist `PED__RESCUE_static_annual_weighted_top12_capnone`.
- Light RUC volume: quarterly MAPE 5.36%, annual MAPE 1.27%; current finalist `dynamic_RESID_GBR_n150_d1_lr0.05_w36`.
- Heavy RUC volume: quarterly MAPE 2.81%, annual MAPE 2.06%; current finalist `HEAVY_RUC__RECON_STATIC_REBUILT`.
- Stale default finalist values such as 5.49%, 9.15% and 12.38% are not visible as current default finalist metrics.

## Schiff Specification Benchmark

- PED VKT per capita: quarterly MAPE 4.67%, annual MAPE 3.59%.
- Light RUC volume: quarterly MAPE 8.52%, annual MAPE 2.70%.
- Heavy RUC volume: quarterly MAPE 8.76%, annual MAPE 8.88%.

## Scenario Semantics

- Scenario comparison defaults to paper-style full-sample gains and paired win rate.
- PED: +1.438 pp quarterly, +1.552 pp annual, paired win rate 69.05%.
- Light RUC: +3.158 pp quarterly, +1.428 pp annual, paired win rate 62.70%; operational annual MAPE is weaker than the Schiff specification benchmark and is flagged as an annual watch.
- Heavy RUC: +5.952 pp quarterly, +6.818 pp annual, paired win rate 62.70%.
- Full-sample gain charts are not labelled as paired gain.

## Browser Evidence

- Streamlit URL tested: `http://localhost:8501`.
- Playwright clicked all four top-level pages.
- Playwright clicked primary filters directly, changed non-default selections, reset filters and verified defaults returned.
- Playwright hovered major Plotly charts and verified human-readable hover text.
- Browser screenshots were regenerated under `artifacts/screenshots`.
- Browser console and Streamlit exception checks were clean in the passing verifier run.
