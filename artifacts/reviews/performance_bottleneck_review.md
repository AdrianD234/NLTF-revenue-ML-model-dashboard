# Performance Bottleneck Review

Reviewer: performance bottleneck reviewer  
Sprint: Stage 1 Model Governance Dashboard performance sprint  
Date: 2026-05-21

## Evidence Reviewed

- `artifacts/performance_latest.json` timestamp `2026-05-21T08:45:22`.
- `artifacts/browser_performance_latest.json` with direct primary-filter timing.
- `scripts/benchmark_dashboard.py`, `tests/test_playwright_performance.py`, `app.py`, and `model_dashboard/*.py`.

## Slowest Current Backend Operations

| Operation | Latest max | Disposition |
|---|---:|---|
| `cached_load_run_first_call` | 0.92s | Meets stretch backend budget; expected first run-load cost |
| `load_run_uncached` | 0.74s | Meets target |
| `overview_page_render_proxy` | 0.73s | Meets stretch |
| `plot_ensemble_composition` | 0.48s | Slowest chart builder, still within stretch |
| `plot_candidate_landscape` | 0.07s | Bounded |
| `plot_error_distribution_json_bytes` | 0.05s | Bounded |

## Slowest Browser Interactions

| Interaction | Latest | Disposition |
|---|---:|---|
| Cold first meaningful content | 1.66s | Meets stretch |
| Warm first meaningful content | 0.94s | Meets stretch |
| Slowest top-level tab switch | 0.31s | Meets stretch |
| Primary Stream filter selection | 0.34s | Meets stretch |
| Reset filters | 0.05s | Meets stretch |

## Findings and Disposition

### PB-01: First-call run loading is the largest backend cost

Status: accepted by evidence.

The first cached call is under 1 second for the configured run and the warm cached call is about 0.07s. No current code change is required.

### PB-02: Ensemble composition is the slowest chart builder

Status: watch item.

At about 0.48s max, it remains inside stretch. If future `ensemble_weights.csv` files grow materially, cache grouped component weights and label mapping.

### PB-03: Large-run error-distribution computation

Status: fixed.

The 4.07M-row arbitration run previously pushed the full-frame error-distribution path over budget. Integer-coded grouped box statistics now pass the backend performance test while preserving exact quartiles and hovers.

### PB-04: Evidence freshness

Status: closed.

Current artifacts include page-render proxy labels, direct primary-filter timing, page render timings, backend payload sizes, and browser hover timing.

## Conclusion

No current measured performance breach remains. The dashboard qualifies for the stretch-target early-exit path with 15 documented loops, provided the final verifier pass succeeds.
