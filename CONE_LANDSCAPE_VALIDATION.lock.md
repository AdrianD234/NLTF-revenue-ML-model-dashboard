# CONE_LANDSCAPE_VALIDATION.lock.md

This locked file defines the candidate-landscape validation gate for the Stage 1 Model Governance Dashboard.

The candidate landscape must be a curated optimisation-cone view, not a raw dump of every candidate row.

## Required evidence

- `artifacts/curated_data/candidate_landscape_sample.csv` exists.
- The curated landscape has no more than 400 rows by default.
- Each stream has a recommended latest finalist.
- Each stream has a pure Schiff benchmark marker.
- Each stream has distribution-sample rows to show the broader search cone.
- Each stream has top-quarterly and top-annual candidate rows.
- Pareto-frontier rows are identified where available.
- Candidate roles are populated and management-readable.
- Hover labels use human names and no raw internal column names.

## Marker contract

- Recommended latest finalist: star marker.
- Pure Schiff benchmark: open triangle.
- Previous PDF/reference finalist: diamond or open marker.
- Frontier candidate: medium dot.
- Distribution sample: small transparent dot.
- Weak/outlier sample: pale dot.

## Completion rule

Do not mark this validation complete unless both tests and browser evidence confirm that the chart uses the curated sample and the latest arbitration finalist values.
