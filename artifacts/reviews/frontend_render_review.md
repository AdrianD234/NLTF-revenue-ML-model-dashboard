# Frontend Render Review

Reviewer: frontend render reviewer  
Sprint: Stage 1 Model Governance Dashboard performance sprint  
Date: 2026-05-21

## Evidence Reviewed

- `artifacts/performance_latest.json` timestamp `2026-05-21T08:45:22`.
- `artifacts/browser_performance_latest.json` from the current direct-filter Playwright performance test.
- `model_dashboard/plots.py`, `model_dashboard/ui.py`, `app.py`, and performance tests.

## Current Frontend Timings and Payloads

| Surface | Evidence | Disposition |
|---|---:|---|
| Cold first meaningful content | 1.66s | Meets stretch |
| Warm first meaningful content | 0.94s | Meets stretch |
| Max tab switch | 0.31s | Meets stretch |
| Primary filter selection | 0.34s | Meets stretch |
| Candidate Landscape payload | 63,592 bytes | Bounded |
| Error distribution payload | 9,967 bytes | Bounded |
| Residual diagnostics payload | 621,921 bytes | Bounded |
| Forecasts and Errors render proxy | 0.08s | Meets stretch |

## Findings

### FR-01: Candidate Landscape payload

Status: closed.

The default landscape uses a competitive/frontier subset while preserving finalists and Schiff anchors. Current payload is about 64 KB, well below the prior 200 KB-plus risk.

### FR-02: Residual diagnostics payload

Status: closed.

Residual scatter is bounded through deterministic sampling. Current payload is about 622 KB, well below the 2 MB verifier cap and far below the original multi-megabyte risk.

### FR-03: Forecast error distribution payload and computation

Status: closed.

The chart uses grouped box statistics and compact hover customdata. Current default payload is about 10 KB. The large arbitration run path also passes the backend performance budget after integer-coded aggregation.

### FR-04: Dense table rendering

Status: closed.

The shared table helper has a default row cap, and full-detail data remains available through expanders and CSV downloads.

### FR-05: Hover and filter preservation

Status: closed.

The filter/hover test suite remains part of the main verifier. The current performance test also exercises direct Stream filter selection and candidate hover timing. No optimisation removed the polished hover templates or direct dropdown controls.

## Watch Items

- Ensemble Composition remains the slowest chart builder at about 0.48s max, still inside stretch. If future weight files grow materially, cache the grouped composition view model by run signature and selected ensemble mode.
- Page-level view-model caches are not necessary for the current measured run; add them only if a target is missed.

## Conclusion

Frontend rendering is within the locked performance targets and stretch targets for the configured run. No current frontend render finding requires a backlog item.
