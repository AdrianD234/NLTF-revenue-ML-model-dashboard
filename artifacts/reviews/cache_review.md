# Cache Review

Reviewer: cache reviewer  
Sprint: Stage 1 Model Governance Dashboard performance sprint  
Date: 2026-05-21

## Scope

Reviewed `model_dashboard/data_loader.py`, `app.py`, `tests/test_cache_contracts.py`, `tests/test_no_unnecessary_data_reload.py`, `PERFORMANCE_SPEC.lock.md`, `PERF_DEFECT_BACKLOG.lock.md`, and current performance artifacts.

## Assessment

The cache posture is acceptable for the performance sprint. Run data is loaded through `app.cached_load_run`, keyed by run path, direct file size/mtime signature, and `LOADER_SCHEMA_VERSION`. Run discovery is cached through `cached_discover_run_folders`. Same-signature CSV and workbook fallback paths are covered by tests.

## Evidence

- `test_cached_load_run_does_not_reread_csv_for_same_signature`: proves repeated cached calls do not reread CSVs.
- `test_cached_load_run_invalidates_when_signature_changes`: proves file changes invalidate the cache.
- `test_cached_load_run_does_not_reparse_workbook_for_same_signature`: proves workbook fallback is cached.
- `test_cached_discover_run_folders_reuses_same_parent_signature`: proves discovery caching.
- Latest `cached_load_run_warm_call`: about 0.07s.

## Findings

### C-01: Broad direct-file signature

Status: accepted watch item.

The signature includes all direct child files, so unrelated direct-file churn can invalidate the active run cache. This is conservative and correct. Consider a dashboard-input-only signature only if future measured cold loads regress.

### C-02: Cache entry count

Status: accepted watch item.

`cached_load_run` does not set `max_entries`. Current workflow keeps a small active run set, and no memory issue is measured. Add a cap if run-comparison or frequent run switching expands usage.

### C-03: Browser timing evidence

Status: closed.

The latest browser artifact includes `primary_filter_select_sec`, `primary_filter_reset_sec`, `page_render_sec`, cold load, warm load, tab switches, and hover timing.

## Conclusion

No cache finding requires a current backlog item. The cache contracts are tested and current timings meet stretch targets.
