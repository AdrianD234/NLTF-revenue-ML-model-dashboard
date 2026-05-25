# Performance Review

Status: **measured**.
Generated: 2026-05-21T23:41:02

The Parquet backed dashboard loader benchmark completed successfully after the browser pass.

## Source

- Run dir: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`
- Data root: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack`

## Benchmarks

| Benchmark | Median | Max | Result |
| --- | ---: | ---: | --- |
| load_parquet_dashboard_uncached | 0.188s | 0.281s | LoadedRun |
| cached_load_parquet_first_call | 0.102s | 0.102s | LoadedRun |
| cached_load_parquet_warm_call | 0.007s | 0.007s | LoadedRun |

## Notes

- Parquet-backed dashboard benchmark path.
