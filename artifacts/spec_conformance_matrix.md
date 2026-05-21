# Spec Conformance Matrix

Source: `ORIGINAL_DASHBOARD_SPEC.lock.md`

| Spec item | Implemented evidence | Verification evidence | Status |
|---|---|---|---|
| Build Streamlit dashboard for Stage 1 model-discovery results | `app.py`, `model_dashboard/` | AppTest, Playwright, screenshots | Complete |
| Select completed model-run folder | Sidebar run discovery and manual path controls | Playwright load checks and data-loader tests | Complete |
| Read CSV/XLSX outputs robustly | `model_dashboard/data_loader.py`, alias maps | `tests/test_data_loader.py` | Complete |
| Recommended finalists by stream | Executive Summary and governance cards | `test_governance_story_matches_source_csv_metrics` | Complete |
| Quarterly and annual MAPE | KPI cards, finalist chart, inventory rows | finalist metric tests | Complete |
| Candidate search landscape | Candidate Landscape page with frontier, annotations, hover, filters | Playwright and chart tests | Complete |
| Schiff benchmark comparison | Schiff Comparison page with decision cards, paired charts, pure-Schiff classifier | Schiff label and classifier tests | Complete |
| Ensemble composition | Ensemble Composition page with C-label mapping, method readout, weight path | ensemble tests and browser assertions | Complete |
| Forecast error distribution by horizon bucket | Forecasts and Errors page box plot | forecast chart tests | Complete |
| Stress and horizon checks | Stress Checks page with horizon buckets, 2020-21, 2022-23, 2024+, annual, high-risk band | stress tests and browser assertions | Complete |
| Paired comparisons versus Schiff | Paired gain and scatter charts plus stream summaries | paired rows and Playwright checks | Complete |
| Model diagnostics and run health | Run Audit health cards, file status, error-type chart | run-health and error-type tests | Complete |
| Feature sets and candidate inventory | Run Audit feature chart; Model Inventory cards, visuals, download | inventory and feature evidence | Complete |
| Stage 1 actual-driver framing | Header info panel and management export | browser assertions and screenshots | Complete |
| File aliases and missing-file resilience | Alias map, empty/missing tests, warnings | data-loader tests | Complete |
| File-read status panel | Run Audit and sidebar expander | screenshot evidence | Complete |
| Flexible column mapping | Schema aliases and normalisers | loader/metrics tests | Complete |
| Percentage error, MAPE, bias, P90, horizon bucket, June year calculations | `model_dashboard/metrics.py` | `tests/test_metrics.py` | Complete |
| Executive Summary cards and finalist accuracy chart | Executive Summary page | final screenshot and Playwright checks | Complete |
| Candidate filters for stage, stream, family, variant, Schiff/finalist visibility | Sidebar controls | filter tests and browser checks | Complete |
| Schiff badges using gain/win-rate rules | `schiff_result_label` and governance cards | tests and screenshots | Complete |
| Ensemble static/prequential handling | method toggles, method readout, origin path chart | tests and screenshots | Complete |
| Forecast controls and charts | stream/model/origin/horizon controls, actual/predicted, percent error, box plot, horizon line | browser and chart tests | Complete |
| Stress commentary for Light RUC and RUC stress windows | Stress Checks copy and readout | browser checks | Complete |
| Model Inventory filters, ranking, CSV download | Model Inventory page | browser assertions | Complete |
| Run Audit errors and feature audit | Run Audit page | run-health and error tests | Complete |
| Plotly interactive charts and report style | `model_dashboard/plots.py`, `model_dashboard/ui.py` | screenshots | Complete |
| Closed-loop verification and browser screenshots | `scripts/verify_dashboard.ps1`, Playwright tests | final screenshots and verifier | Complete |
| Management questions answered | Executive, Schiff, Stress, Ensemble, Run Audit pages | management-readiness report | Complete |

Conformance result: all locked specification items have implemented evidence and verification evidence.
