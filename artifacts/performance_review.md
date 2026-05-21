# Performance Review

Status: strict performance gate ready for final verification against the latest arbitration run. Fifteen performance loops are documented and latest backend/browser timings meet the stretch-target early-exit rule.

## Latest Measured Timings

Backend benchmark command: `python scripts/benchmark_dashboard.py --run-dir <configured run> --out-dir artifacts --repeats 3`.

Configured run: `run_20260520_002339`.

| Metric | Latest | Target | Stretch | Status |
|---|---:|---:|---:|---|
| Cold load to first meaningful content | 1.66s | 5.00s | 3.00s | Meets stretch |
| Warm load to first meaningful content | 0.94s | 2.00s | 1.00s | Meets stretch |
| Max top-level tab switch | 0.31s | 1.50s | 0.75s | Meets stretch |
| Primary filter selection | 0.34s | 2.00s | 1.00s | Meets stretch |
| Primary filter reset | 0.05s | 2.00s | 1.00s | Meets stretch |
| Overview page render proxy | 0.73s | 2.00s | 1.00s | Meets stretch |
| Candidate Landscape chart build | 0.07s | 2.00s | 1.00s | Meets stretch |
| Ensemble Composition chart build | 0.48s | 2.00s | 1.00s | Meets stretch |
| Forecasts and Errors render proxy | 0.08s | 2.00s | 1.00s | Meets stretch |
| Stress Checks chart build | 0.03s | 2.00s | 1.00s | Meets stretch |
| Model Inventory chart build | 0.03s | 2.00s | 1.00s | Meets stretch |
| Run Audit prep | <0.01s | 2.00s | 1.00s | Meets stretch |

## Completed Optimisations

- Cached run-folder loading is keyed by run path, file size/mtime signature, and loader schema version.
- CSV and workbook same-signature reloads are covered by tests.
- Default run discovery is cached.
- Active top-level page dispatch avoids building hidden pages.
- Heavy drilldown modules are lazy-gated.
- Candidate Landscape defaults to a competitive/frontier subset.
- Forecast error distribution uses exact grouped box statistics and compact Plotly traces.
- Large-run error-distribution computation now passes the backend budget on the 4.07M-row arbitration run.
- Residual diagnostics are sampled to a bounded payload.
- Shared tables have row caps and full-data downloads/expanders.
- Browser performance tests now time direct primary filter selection, reset, page switches, first meaningful content, and hover.
- The app honours `MODEL_RUN_DIR` / `STAGE1_MODEL_RUN_DIR` so configured deployments and performance verification load the same run folder.
- The performance verifier fallback run now points to the latest arbitration source-of-truth run, preventing stale balanced-run artifacts from being regenerated during performance checks.

## Reviewer Disposition

- `artifacts/reviews/performance_bottleneck_review.md`: no current timing breach; first run load and ensemble chart remain watch items.
- `artifacts/reviews/cache_review.md`: cache posture acceptable; broad file-signature invalidation and cache entry count remain watch items.
- `artifacts/reviews/rerun_review.md`: selected-page dispatch and lazy drilldowns satisfy current rerun requirements.
- `artifacts/reviews/frontend_render_review.md`: current Plotly payloads are bounded; no visual-functionality regression is accepted.

## Open Performance Work

No unchecked performance backlog items remain. Future work should only add page-level view-model caches if a larger selected run folder misses the locked targets in measured browser or backend artifacts.
