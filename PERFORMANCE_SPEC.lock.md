# PERFORMANCE_SPEC.lock.md

This file defines the performance target for the Stage 1 Model Governance Dashboard.

Do not remove, weaken, or mark these requirements complete without benchmark evidence.

## Performance target table

| Metric | Target | Stretch |
|---|---:|---:|
| Cold load to first meaningful content | <= 5.0 sec | <= 3.0 sec |
| Warm load to first meaningful content | <= 2.0 sec | <= 1.0 sec |
| Overview page render | <= 2.0 sec | <= 1.0 sec |
| Candidate Landscape render | <= 2.0 sec | <= 1.0 sec |
| Ensemble Composition render | <= 2.0 sec | <= 1.0 sec |
| Forecasts and Errors render | <= 2.0 sec | <= 1.0 sec |
| Stress Checks render | <= 2.0 sec | <= 1.0 sec |
| Model Inventory render | <= 2.0 sec | <= 1.0 sec |
| Run Audit render | <= 2.0 sec | <= 1.0 sec |
| Primary filter-change latency | <= 2.0 sec | <= 1.0 sec |
| Tab-switch latency | <= 1.5 sec | <= 0.75 sec |

## Hard requirements

- [x] No repeated full CSV reads on every widget interaction. Evidence: `tests/test_no_unnecessary_data_reload.py`.
- [x] No repeated Excel parsing during ordinary dashboard interaction. Evidence: workbook cache contract test and ordinary app load prefers CSV outputs.
- [x] No regeneration of all page charts on every rerun. Evidence: selected-page dispatch plus lazy drilldown gates.
- [x] Inactive pages should not build expensive charts. Evidence: `test_heavy_drilldown_modules_are_lazy_gated`.
- [x] Dense tables should not render thousands of rows by default. Evidence: `display_table` default row cap and expandable/download detail.
- [x] Candidate Landscape should default to competitive/frontier/top-N view. Evidence: `_competitive_landscape_subset`.
- [x] Full detail should remain available through expanders, search, pagination, downloads, or explicit controls. Evidence: candidate/inventory downloads and lazy-loaded drilldowns.
- [x] Hover text polish must remain intact. Evidence: `tests/test_filter_and_hover.py`.
- [x] Dropdown/filter functionality must remain intact. Evidence: primary filter e2e tests.
- [x] All visual pages must remain present. Evidence: `tests/test_playwright_dashboard.py` and visual verifier.

## Data-loading requirements

- [x] Run data is loaded through cached functions. Evidence: `app.cached_load_run`.
- [x] CSV files are not reread on every widget interaction. Evidence: same-signature cached-load test.
- [x] Excel files are not parsed during normal page interaction unless explicitly requested or no CSV equivalent exists. Evidence: loader alias preference plus Excel cache test.
- [x] Cache invalidates when run-folder files change. Evidence: `run_signature` size and mtime test.
- [x] Missing/empty files remain gracefully handled. Evidence: data-loader tests and file-status warnings.

## Transformation requirements

- [x] Stream/model labels are prepared once per run load or cached by helper. Evidence: cached label helper test.
- [x] Candidate summaries are bounded for default render. Evidence: competitive subset benchmark.
- [x] Paired-vs-Schiff summaries are compact and charted only on active pages. Evidence: selected-page rendering.
- [x] Stress summaries use compact run output when available. Evidence: stress benchmark and line-chart data.
- [x] Ensemble composition summaries are grouped before plotting. Evidence: `ensemble_composition_data_prep` benchmark.
- [x] Model inventory summary metrics are bounded before display. Evidence: model inventory prep benchmark and table cap.

## Rendering requirements

- [x] Only active page charts are built. Evidence: primary page dispatch in `app.py`.
- [x] Hidden pages do not build all expensive figures. Evidence: lazy drilldown toggles.
- [x] Candidate Landscape defaults to competitive/frontier view. Evidence: benchmark payload and subset test.
- [x] Full candidate table is available, but not rendered as a huge default DOM table. Evidence: download button plus capped expander table.
- [x] Dense model inventory uses filtering, ranking, caps, and expanders. Evidence: inventory UI and table cap.
- [x] Plotly hover payload is not excessively large. Evidence: payload benchmarks and hover tests.
- [x] Screenshots and report artifacts are not regenerated during normal app interaction. Evidence: artifact scripts are verifier-only.

## Streamlit rerun requirements

- [x] Filter state uses session state. Evidence: top filter keys and reset callback.
- [x] Reset filters does not reload all data unnecessarily. Evidence: cached run-load contract.
- [x] Widget changes do not cause repeated file reads. Evidence: no unnecessary reload tests.
- [x] Fragments were considered; current measured tab/filter timings are already within stretch targets, so simpler selected-page dispatch is retained.

## Browser verification requirements

- [x] Browser benchmark measures cold load. Evidence: `artifacts/browser_performance_latest.json`.
- [x] Browser benchmark measures warm load. Evidence: `artifacts/browser_performance_latest.json`.
- [x] Browser benchmark measures tab-switch latency. Evidence: `tab_switch_sec`.
- [x] Browser benchmark measures filter-change latency. Evidence: `primary_filter_select_sec` and reset timing.
- [x] Browser benchmark checks console/network errors through Playwright console/page-error listeners.
- [x] Results are recorded in `artifacts/browser_performance_latest.json` and backend history is recorded in `artifacts/performance_history.json`.

## Completion rule

The performance sprint is not complete unless:

- targets are met or explicitly justified with evidence;
- at least 50 optimisation loops are completed, unless stretch targets are reached and at least 15 loops are complete;
- `PERF_DEFECT_BACKLOG.lock.md` has no unresolved items;
- all functionality and visual requirements still pass.

## Parquet refresh performance lock

The current 80-gate Parquet refresh must measure performance against the Parquet-backed data pack, not only the previous CSV curated preview.

Additional locked requirements:

- Parquet loading must be cached with `st.cache_data`.
- The cache key must include file path, modified timestamp, file size, and loader schema version.
- Diagnostic Excel parsing must not happen on ordinary filter interactions.
- `scripts/benchmark_dashboard.py` must write `artifacts/performance_review.md` or equivalent performance artifacts for the Parquet-backed run before gates are closed.
- `scripts/validate_80_gates.py` must fail performance supporting checks until current Parquet-backed performance evidence exists.
