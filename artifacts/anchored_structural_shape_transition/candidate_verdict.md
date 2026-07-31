# Candidate verdict — which transition schedule should become the default

This is a recommendation. Nothing is promoted; the production default remains
`unblended_current` until an owner decides.

## The decision table (Base case, Total NLTF)

| candidate | complete | FY2031 seam | FY2040 | FY2050 | ratio to BEFU26 FY2050 | petrol FY2050 | pool FY2050 | max annual growth | legacy curve (mean abs pp) | formula closure |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Current unblended | — | 5.115% | 10588.1 | 17264.7 | **1.3373** | 36198 | 52461 | 5.74% | 0.594 | < 1e-6 |
| Early structural | FY2040 | 5.087% | 9093.7 | 12820.2 | 0.9930 | 9861 | 50314 | 4.69% | 0.594 | < 1e-6 |
| Balanced structural | FY2045 | 5.102% | 9443.3 | 12820.2 | 0.9930 | 9861 | 50314 | 4.79% | 0.594 | < 1e-6 |
| Gradual structural | FY2050 | 5.108% | 9790.3 | 12820.2 | 0.9930 | 9861 | 50314 | 4.82% | 0.594 | < 1e-6 |

## How to read it

**FY2050 does not discriminate.** All three structural candidates reach w = 1
by FY2050, so they must converge there. The differences live in the path, and
**FY2040 is the column that separates them**: 9093.7 / 9443.3 / 9790.3 $m.

**The terminal ratio is 0.9930 for all three, not 1.0.** That is exactly
`Current_2030 / Official_2030`. It is evidence that the method adopts the
official growth shape while keeping Current's own level — not evidence that any
candidate is better calibrated.

**The legacy-curve column is identical across all four.** This is structural,
not coincidental: BEV share of the pool is set by the exact VFM shares in every
candidate, so the transition moves the pool total and never the class split.
The legacy workbook validated a *composition* path, so it has nothing to say
about which schedule to pick. It must not be used as a tie-breaker.

**The seam is flat across all four** (5.087%–5.115%). No candidate introduces a
kink at FY2031; that is the smoothstep's zero endpoint slope working.

## What is actually at stake

The unblended path is not a neutral default. By FY2050 it sits at 3.77x
BEFU26's light-petrol VKT, 1.29x its Heavy RUC, and 1.34x its Total NLTF, on a
petrol path that is still *rising* while both official vintages have it falling
to under 30% of FY2030. Whatever is chosen, "leave it alone" is itself a
substantive position that the FY2050 numbers make hard to defend.

## Assessment against the brief's criteria

| criterion | early | balanced | gradual |
|---|---|---|---|
| preserves the econometric anchor | yes (exact) | yes (exact) | yes (exact) |
| transparent structural interpretation | yes | yes | yes |
| smoothness at the seam | yes | yes | yes |
| economic plausibility of the path | drops model information fastest | balanced | still 1.07x BEFU26 at FY2040 while claiming a structural basis |
| consistency among activity classes | yes | yes | yes |
| stability under a later vintage | good (MBU26 shape ~= BEFU26) | good | good |
| absence of hidden calibration | yes | yes | yes |
| explainability | "the model owns one decade" | "equal weight around FY2037" | "the model owns two decades" |

## Recommendation

**`balanced_structural` (complete FY2045).**

It reaches equal weight around FY2037 — roughly a decade past the estimation
window. That is long enough not to discard the econometrics prematurely, and
short enough that the terminal decade is genuinely governed by an externally
published structural source rather than by a twenty-year extrapolation of a
short-run model.

`early_structural` discards the model's own information fastest, and there is
no evidence the econometrics stop being informative at FY2040.
`gradual_structural` leaves FY2040 at 1.07x BEFU26 while presenting itself as
structurally grounded, which is the weakest position to defend.

This is a judgement about how quickly reliance should shift between two
governed sources. It is **not** a fit: no candidate is closer to correct on any
statistic, none is selected for proximity to an official level, and none should
be selected for resembling an earlier chart.

## Stability caveat

The BEFU26 petrol structural index reaches 0.292 at FY2050 against a governed
minimum cumulative index of 0.25. All three candidates pass, but the margin is
thin. A future vintage with somewhat stronger electrification would trip the
guard — correctly. The response then should be to examine the vintage, not to
widen the guard.
