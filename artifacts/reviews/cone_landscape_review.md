# Cone Landscape Review

Reviewer: simulated cone landscape reviewer

## Verdict

Pass. The Candidate Search Landscape uses a curated optimisation-cone sample rather than plotting the full raw candidate universe by default.

## Sample structure

| Check | Result | Status |
|---|---:|---|
| Total curated rows | 293 | Pass |
| Hard cap | 400 | Pass |
| Recommended finalist rows | 3 | Pass |
| Pure Schiff benchmark rows | 3 | Pass |
| Previous PDF/reference rows | 3 | Pass |
| Distribution sample rows | 149 | Pass |
| Pareto/frontier rows | 8 | Pass |
| Top quarterly rows per stream | 15 | Pass |
| Top annual rows per stream | 15 | Pass |

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
- `artifacts/curated_data/candidate_landscape_sample.csv`
- `tests/test_curated_data.py`
- `tests/test_filter_and_hover.py`
