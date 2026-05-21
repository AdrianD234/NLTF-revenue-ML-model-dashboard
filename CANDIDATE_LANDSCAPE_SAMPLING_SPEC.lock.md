# CANDIDATE_LANDSCAPE_SAMPLING_SPEC.lock.md

This file defines the deterministic candidate-landscape sample for the optimisation-cone plot.

The goal is to show the shape of the search space without plotting every raw candidate.

## Required sampled rows

For each stream, include:

1. All recommended latest finalists.
2. Pure Schiff benchmark rows.
3. Previous PDF/reference finalist rows, if identifiable.
4. Top 15 by quarterly MAPE.
5. Top 15 by annual MAPE.
6. Top 15 by governance score.
7. Top 10 by lowest absolute quarterly bias, only where MAPE is competitive.
8. Pareto-frontier candidates where no other candidate has both lower quarterly and annual MAPE.
9. Distribution/cone sample:
   - compute `distance = sqrt(quarterly_mape^2 + annual_mape^2)`;
   - bin candidates by distance quantiles;
   - from each bin and stream, select up to five deterministic medoid candidates closest to bin-median distance.
10. A small weak/outlier sample from the upper tail, capped at five per stream, only where useful.

## Caps

- Target default landscape rows: `<= 250`
- Hard cap: `<= 400`

## View modes

The dashboard should support:

- Competitive frontier
- Curated cone sample
- Top candidates only
- Full loaded sample

Default must be `Curated cone sample` or `Competitive frontier`, not all raw candidates.

## Marker rules

- Recommended finalist: star marker, largest size.
- Pure Schiff benchmark: open triangle.
- PDF/reference finalist: diamond or hollow circle.
- Frontier candidates: medium dots.
- Distribution sample: small dots with transparency.
- Weak/outlier sample: small pale dots.

## Hover rules

Hovers must be clean and management-readable:

- Stream
- Model short label
- Candidate role
- Quarterly MAPE
- Annual MAPE
- Bias
- Source family
- Feature set

No underscores, no raw internal column labels, and no excessive decimals.
