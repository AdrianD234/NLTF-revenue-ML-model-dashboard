# Cone Landscape Review

Current Parquet refresh status: **pass**. The candidate cone is backed by `stage1_curated_candidate_cone.parquet`, and gates 21-30 passed against the curated Parquet candidate rows.

Reviewer: simulated cone landscape reviewer

## Verdict

Pass. The Candidate Search Landscape uses a curated optimisation-cone sample rather than plotting the full raw candidate universe by default.

## Sample structure

| Check | Result | Status |
|---|---:|---|
| Total curated rows | 300 | Pass |
| Hard cap | 400 | Pass |
| Recommended finalist rows | 3 | Pass |
| Pure Schiff benchmark rows | 5 | Pass |
| Previous PDF/reference rows | 14 | Pass |
| Distribution sample rows | 300 | Pass |
| Pareto/frontier rows | 2 | Pass |
| Top quarterly rows | 6 | Pass |
| Top annual rows | 10 | Pass |

## Stream coverage

| Stream | Recommended finalist | Pure Schiff | Distribution sample | Top candidate cluster | Frontier rows |
|---|---:|---:|---:|---:|---:|
| PED | 1 | 1 | 50 | 35 | 2 |
| Light RUC | 1 | 1 | 50 | 44 | 2 |
| Heavy RUC | 1 | 1 | 49 | 35 | 4 |

## Interpretation

The chart preserves the management story: weaker/noisier candidates define the outer cone, top candidates cluster closer to the lower-left optimum, the latest finalist is highlighted by a star, and pure Schiff is separated with an open-triangle marker.

## Evidence

- `CONE_LANDSCAPE_VALIDATION.lock.md`
- `CANDIDATE_LANDSCAPE_SAMPLING_SPEC.lock.md`
- `artifacts/chart_sources/overview_candidate_search_frontier.csv`
- `artifacts/data_schema_report.md`
- `tests/test_curated_data.py`
- `tests/test_filter_and_hover.py`
