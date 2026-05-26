# Test Summary

Status: **passed** for the v3 dual-scorecard evidence-pack migration, score-basis governance, visual conformance and browser verification pass.

## Data Root Used

`data\dashboard_evidence_pack`

The default dashboard source is the repo evidence pack at `data/dashboard_evidence_pack`. Legacy run folders, mini fixtures, old CSV/XLSX artifacts and previous diagnostic-pack paths are review-only and are not used by the default four-page dashboard.

## Latest Full Verifier Command

```powershell
pwsh -File scripts\verify_dashboard.ps1 -Python ".\.venv\Scripts\python.exe" -DataRoot "data\dashboard_evidence_pack" -Port 8501
```

## Results

| Check | Result |
| --- | --- |
| Compile | Passed |
| Full pytest | 123 passed, 46 skipped, 38 deselected |
| Schema inspection | Passed against `dashboard_evidence_pack_v3_dual_scorecard` and 14 required Parquet tables |
| Data validation | Passed |
| Chart source validation | Passed for 16 primary chart source tables |
| Semantic label validation | Passed |
| Chart-data reconciliation tests | 18 passed |
| Per-chart source-table tests | 6 passed |
| Existing browser e2e | 37 passed |
| Mandatory frontend interaction Playwright suite | 5 passed |
| Visual conformance validation | Passed |
| 100-gate validation | 100 passed, 0 failed, 0 supporting failures |
| 120-gate validation | 120 passed, 0 failed |
| Backlog | No unchecked items |

## V3 Score-Basis Checks

- `manifest.json` schema is `dashboard_evidence_pack_v3_dual_scorecard`.
- Default score basis is `schiff_paper_horizon_mean` / Paper-style horizon MAPE.
- Operational score basis is `current_grid_operational_pooled` and is exposed only through the explicit Score Basis selector.
- Source tables include `score_basis` and `score_basis_label`.
- Paper-style and operational metrics are not mixed silently.

## Default Paper-Style Finalists

- PED VKT per capita: quarterly MAPE 3.24%, annual MAPE 2.03%.
- Light RUC volume: quarterly MAPE 6.07%, annual MAPE 3.43%; current finalist `schiff_w36_OLS`.
- Heavy RUC volume: quarterly MAPE 2.81%, annual MAPE 2.06%.
- Stale default finalist values such as 5.49%, 9.15% and 12.38% are not visible as current default finalist metrics.

## Schiff Specification Benchmark

- PED VKT per capita: quarterly MAPE 4.67%, annual MAPE 3.59%.
- Light RUC volume: quarterly MAPE 8.52%, annual MAPE 2.70%.
- Heavy RUC volume: quarterly MAPE 8.76%, annual MAPE 8.88%.

## Scenario Semantics

- Scenario comparison defaults to paper-style full-sample gains and paired win rate.
- PED: +1.438 pp quarterly, +1.552 pp annual, paired win rate 69.05%.
- Light RUC: +2.456 pp quarterly, -0.723 pp annual, paired win rate 55.56%; shown as Promote with annual watch/caveat.
- Heavy RUC: +5.952 pp quarterly, +6.818 pp annual, paired win rate 62.70%.
- Full-sample gain charts are not labelled as paired gain.

## Browser Evidence

- Streamlit URL tested: `http://localhost:8501`.
- Playwright clicked all four top-level pages.
- Playwright clicked primary filters directly, changed non-default selections, reset filters and verified defaults returned.
- Playwright hovered major Plotly charts and verified human-readable hover text.
- Browser screenshots were regenerated under `artifacts/screenshots`.
- Browser console and Streamlit exception checks were clean in the passing verifier run.
