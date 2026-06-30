# Governance Story Review

Status: PASS WITH EXPLICIT CAVEATS

Generated: 2026-06-24T20:09:55.270666+00:00
Commit reviewed: `e3a9fea`

Evidence reviewed:

- `docs/revenue_source_pack_contract.md` documents the governed Revenue Outlook architecture.
- `data/revenue_model_source_pack/2026_05_19/source_gap_register.csv` records runtime source gaps.
- `data/revenue_model_source_pack/2026_05_19/remaining_decisions_handoff.csv` links unresolved decisions to dashboard treatment.
- `data/current_revenue_outlook/manifest.json` records promoted-pack source policy, workbook hashes, bridge statuses, and output hashes.

Findings:

- The dashboard defaults to Total NLTF revenue while preserving the workbook's legacy Total RUC+PED current-selection provenance.
- Direct modeled activity streams and revenue bridge roles are separated for PED, Light RUC, and Heavy RUC.
- Missing release values, FED path values, PED bridge history, and top-up rows remain visible governed gaps.
- The R2 ladder and reproducibility pages distinguish training-fit, calibration, and forecast/net R2.

Residual risk:

- Native Playwright verification must pass before calling the entire dashboard release-ready under AGENTS.md.

Semantic validation excerpt:

```text
# Semantic Label Validation Report

Status: **passed**.

| Check | Status | Evidence |
| --- | --- | --- |
| Candidate count label is precise | PASS | Overview KPI and frontier caption identify plotted candidate rows rather than vague loaded/model counts. |
| Frontier label explains balanced v6 frontier coverage | PASS | Candidate frontier title/caption makes clear that v6 has balanced all-stream visualization samples excluded from governance scoring. |
| Candidate frontier has no dotted efficient-frontier line | PASS | Candidate Search Frontier uses candidate dots and explicit finalist/Schiff markers without a dotted connecting line. |
| Default stress chart excludes policy windows | PASS | Overview stress subtitle and bucket filtering keep 2024+/2022-23 out of Paper-style default. |
| Calibration R2 is not labelled adjusted R2 | PASS | Diagnostics KPI title inspected in app.py. |
| Forecast R2 and calibration R2 are distinguished | PASS | Diagnostics and Governance labels distinguish net forecast R2 from calibration R2. |
| R2 ladder distinguishes training fit from forecast R2 | PASS | R2 ladder note inspected in app.py and model_dashboard/r2_ladder.py. |
| Full-sample gain chart is not labelled paired | PASS | Schiff gain chart title inspected in app.py. |
| Decision table separates full-sample gains from paired win rate | PASS | Scenario and Schiff summary labels inspected in app.py. |
| Benchmark and decision summary fields expose governance tooltips | PASS | Schiff Benchmark and Scenario recommendation summaries have accessible hover/focus copy. |
| Residual vs fitted axis does not use misleading million-unit label | PASS | Residual axis title inspected in app.py/plot helpers. |
| Diagnostic pass matrix headers and cells expose plain-English tooltips | PASS | Diagnostic matrix tooltips are centralized, keyboard focusable, and rendered by the dashboard. |
| Light RUC paper gains are not hidden by full-sample gain label | PASS | paired_gain=2.93220519190978; full_qtr_gain=3.158190316211643; full_annual_gain=1.4282266818971854 |
| Light RUC operational annual watch is visible | PASS | App text contains the visible operational annual watch note. |
| Page 5 panel contract prevents component weights being labelled feature importance | PASS | Contract CSV and app panel labels separate component contribution from true feature importance. |
| Page 5 unavailable explainability panels render governance caveats | PASS | PED/Heavy coefficients and sensitivities are rendered as styled missing-data cards, not empty charts. |
| Dashboard chart spec uses current semantic labels | PASS | No stale chart-spec labels found. |
| Screenshot review does not describe the full-sample chart as paired | PASS | artifacts/screenshot_review.md label wording inspected. |
| Model hovers use management-friendly descriptions | PASS | Hover templates use Model detail/Component detail and helper translations for Heavy RUC ElasticNet and Light RUC residual GBM. |
```
