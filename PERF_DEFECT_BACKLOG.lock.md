# PERF_DEFECT_BACKLOG.lock.md

This backlog is for performance defects. Do not delete or weaken items.

Every performance finding must be either fixed and checked off with evidence, or explicitly rejected with reason and benchmark evidence.

## Closure status

Status: pass for the current verification pass. All performance backlog items are checked with benchmark, test, or reviewer evidence, and the active performance baseline/latest artifacts now point to `run_20260520_002339`.

## Seed performance defects

- [x] Cold load is not benchmarked. Evidence: `tests/test_playwright_performance.py` writes `cold_load_sec`.
- [x] Warm load is not benchmarked. Evidence: `warm_load_sec`.
- [x] Tab-switch latency is not benchmarked. Evidence: `tab_switch_sec` and `max_tab_switch_sec`.
- [x] Primary filter-change latency is not benchmarked. Evidence: `primary_filter_select_sec` and `primary_filter_reset_sec`.
- [x] File loading cache has not been proven. Evidence: `tests/test_cache_contracts.py` and `tests/test_no_unnecessary_data_reload.py`.
- [x] CSV files may be reread on every widget interaction. Evidence: cached same-signature load reads CSV once.
- [x] Excel files may be parsed during ordinary app interaction. Evidence: workbook fallback is cached and ordinary run uses CSV aliases first.
- [x] Label/model-name transformations may be recomputed on every rerun. Evidence: label/model formatting helpers now use bounded `lru_cache`; tested in `test_label_formatting_helpers_are_cached`.
- [x] Candidate summaries may be recomputed on every rerun. Evidence: default render is bounded by `_competitive_landscape_subset`; backend prep measured under target.
- [x] Stress summaries may be recomputed on every rerun. Evidence: stress summary prep benchmark is under target and active-page only.
- [x] Ensemble summaries may be recomputed on every rerun. Evidence: grouped composition prep benchmark and active-page rendering are under target.
- [x] Inactive tabs/pages may still build charts. Evidence: four-page selected dispatch and lazy drilldown gates.
- [x] Candidate Landscape may render too many points by default. Evidence: candidate landscape data prep returns a competitive/frontier subset and payload is measured.
- [x] Model Inventory may render too many rows by default. Evidence: display table row cap plus ranking/filtering before display.
- [x] Plotly customdata payloads may be too large. Evidence: payload measurements for candidate landscape, error distribution, and residual diagnostics.
- [x] Dense tables may slow frontend rendering. Evidence: capped shared table renderer and downloads for full detail.
- [x] Browser performance artifacts are missing. Evidence: `artifacts/browser_performance_latest.json`.
- [x] Performance improvement history is missing. Evidence: `artifacts/performance_history.json` and `artifacts/performance_improvement_loops.json`.
- [x] Cache/rerun/frontend reviewer reports are missing. Evidence: reviewer reports under `artifacts/reviews/`.

## Additional investigated defects

- [x] Performance verifier previously allowed fewer than 15 loops even under the stretch-target early-exit rule. Evidence: verifier now requires either 50 loops or 15 loops plus stretch evidence.
- [x] Browser performance test previously timed the More panel rather than the real primary filters. Evidence: browser test now times direct Stream dropdown selection and reset.
- [x] Benchmark script did not name the required backend prep operations. Evidence: `summary_generation_prep`, `candidate_landscape_data_prep`, `ensemble_composition_data_prep`, `stress_summary_prep`, `model_inventory_prep`, and `run_audit_prep`.
- [x] Backend benchmark did not cover page-render proxies for Overview and Forecasts/Errors. Evidence: `overview_page_render_proxy` and `forecasts_and_errors_render_proxy`.
- [x] Browser app and backend benchmark could load different default runs. Evidence: app now honours `MODEL_RUN_DIR` / `STAGE1_MODEL_RUN_DIR`; performance verifier exports `MODEL_RUN_DIR` before starting Streamlit.
- [x] Browser cold-load timing was conflated with full chart completion. Evidence: Playwright performance test now measures first meaningful content separately from page render timing.
- [x] Full-frame error distribution on the 4.07M-row arbitration run exceeded the soft backend budget. Evidence: integer-coded grouped box statistics and `test_backend_core_operations_have_soft_regression_budget`.
- [x] Reviewer watch item: broad direct-file cache invalidation. Disposition: accepted with evidence because it is correctness-preserving and current cold/warm timings meet stretch targets.
- [x] Reviewer watch item: no `max_entries` on `cached_load_run`. Disposition: accepted with evidence because current workflow and timings show no measured cache pressure.
- [x] Reviewer watch item: ensemble composition remains the slowest chart builder. Disposition: accepted with evidence because latest max is about 0.48s, under the 1.0s stretch threshold.
- [x] Reviewer watch item: active-page view models are not separately cached. Disposition: accepted with evidence because selected-page render timings meet stretch targets and broad DataFrame hashing could add cost before benefit.

## Rule

No unchecked item may remain at completion.
