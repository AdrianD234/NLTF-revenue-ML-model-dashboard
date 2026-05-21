# Streamlit Rerun Review

Reviewer: Streamlit rerun reviewer  
Sprint: Stage 1 Model Governance Dashboard performance sprint  
Date: 2026-05-21

## Scope

Reviewed `app.py`, `model_dashboard/ui.py`, `tests/test_performance_budget.py`, `PERFORMANCE_SPEC.lock.md`, `PERF_DEFECT_BACKLOG.lock.md`, and latest backend/browser artifacts.

## Assessment

The app has a sound rerun architecture for the current measured workflow. The raw run folder is cached, run discovery is cached, top-level page routing uses selected-page dispatch rather than hidden `st.tabs`, and heavy supporting modules are guarded by lazy toggles.

## Evidence

- Top-level pages dispatch through `render_overview`, `render_diagnostics`, `render_scenario_comparison`, and `render_schiff_benchmark_page`.
- Lazy gates exist for Model Inventory, Run Audit, Forecast/Stress drilldowns, and Candidate/Ensemble drilldowns.
- `test_heavy_drilldown_modules_are_lazy_gated` protects the lazy-gate contract.
- Latest max tab switch: about 0.31s.
- Latest direct primary filter selection: about 0.34s.

## Findings

### R-01: Inactive pages building charts

Status: closed.

Inactive top-level pages are not built during ordinary navigation. Heavy supporting modules are explicitly lazy-loaded.

### R-02: Active page recomputation

Status: accepted watch item.

The selected page still rebuilds its compact figures on rerun. Current timings are under stretch targets, so page-level view-model caches are deferred until a measured target is missed.

### R-03: Fragments

Status: considered and deferred.

`st.fragment` is not needed for current measured latency. It can be considered later for deliberately loaded heavy drilldowns.

## Conclusion

No rerun finding requires a current backlog item. The selected-page and lazy-gate design satisfies the performance spec without adding unnecessary complexity.
