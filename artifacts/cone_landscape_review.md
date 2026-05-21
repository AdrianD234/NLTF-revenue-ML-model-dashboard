# Cone Landscape Review

Status: pass for the current verification pass.

The current curated landscape contains 293 rows, below the 400-row hard cap. It includes the latest finalist, pure Schiff benchmark, previous PDF/reference marker, top candidate cluster, frontier candidates, and distribution sample rows for each stream.

## Role counts

| Stream | Recommended finalist | Pure Schiff | PDF/reference | Distribution sample | Top candidate | Frontier rows |
|---|---:|---:|---:|---:|---:|---:|
| PED | 1 | 1 | 1 | 50 | 35 | 2 |
| Light RUC | 1 | 1 | 1 | 50 | 44 | 2 |
| Heavy RUC | 1 | 1 | 1 | 49 | 35 | 4 |

## Minimum role coverage

| Required visual role | PED | Light RUC | Heavy RUC | Status |
|---|---:|---:|---:|---|
| Recommended finalist star | 1 | 1 | 1 | Pass |
| Pure Schiff benchmark marker | 1 | 1 | 1 | Pass |
| PDF/reference marker | 1 | 1 | 1 | Pass |
| Distribution/cone sample | 50 | 50 | 49 | Pass |
| Top-candidate cluster | 35 | 44 | 35 | Pass |
| Frontier evidence | 2 | 2 | 4 | Pass |

The cone view is not a full raw candidate dump: it is capped at 293 rows and includes the management-critical markers needed to read the optimisation path from weaker candidate distribution to finalist/frontier clusters.

## Browser read

The Candidate Search Landscape card describes the lower-left frontier and the management view distinguishes selected finalists from pure Schiff and distribution-sample candidates.

## Evidence

- `artifacts/curated_data/candidate_landscape_sample.csv`
- `artifacts/screenshots/mcp-01-overview.png`
- `artifacts/screenshots/hover-candidate-landscape.png`
- `tests/test_curated_data.py`
- `tests/test_cone_landscape_validation.py`
