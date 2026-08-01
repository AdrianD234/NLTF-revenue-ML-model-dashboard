# Legacy structural method - reconstruction

Source workbook: `references/MBU26 v VFM202405_outputs_summary_V3 (1).xlsx`,
sheet `S-curve analysis (F&F)`. Every number below is read from a cell or recomputed from the
workbook's own series; none is taken on trust from the brief.

Regenerate with:

    .venv\Scripts\python.exe scripts\build_anchored_shape_legacy_reconstruction.py

## 1. The dashboard logistic, verified from cells

The curve is an ordinary logistic in the calendar year:

    share_fy = ceiling / (1 + exp(-steepness * (fy - midpoint)))

read verbatim from `E154`:

    =$C$105/(1+EXP(-$C$106*(B154-$C$107)))

| dial | cell | value |
|---|---|---|
| Peak uptake speed (share points/year) | `C104` | 0.0425 |
| Saturation ceiling | `C105` | 0.920487 |
| Steepness (derived, `=4*C104/C105`) | `C106` | 0.18468484617381886 |
| Midpoint (year of fastest uptake) | `C107` | 2038 |

The four values in the brief are confirmed. Steepness is **derived**, not
independently set: `4 x 0.0425 / 0.920487` reproduces `C106` to 1e-12, so the
dials are mutually consistent rather than four separately typed numbers.

Rebuilding the logistic in Python from those dials reproduces the workbook's
own curve column for every year 2015-2050 to within 1e-12.

## 2. The published fit, re-derived

The workbook linearises the logistic. For `ds/dt = r*s*(1 - s/K)`,

    (ds/dt)/s = r - (r/K)*s

so regressing the mid-point growth rate (`AE`) on the mid-point share (`AD`)
over the projection era gives the steepness as the intercept and the ceiling as
the x-intercept. Recomputing that regression from the same two columns:

| statistic | workbook | recomputed | agrees |
|---|---|---|---|
| Straight-line fit R-squared | 0.9525105818966445 | 0.9525105818966449 | yes |
| Steepness off the line | 0.1894305334181923 | 0.1894305334181923 | yes |
| Ceiling off the line | 0.9073143029903090 | 0.9073143029903089 | yes |

Observations: 26 (projection era 2025-2050).

The fitted values are close to but not identical with the dials - steepness
0.189431 against a dial of
0.184685, ceiling 0.907314
against a dial of 0.920487. The dials are a
rounded, human-settable version of the fit, and the workbook says so by
printing both side by side.

## 3. MBU26, VFM and the curve compared

June-year BEV share of the Light RUC pool, from the workbook's own comparison
block (rows 154-179):

| June year | MoT MBU26 | VFM Base | Dashboard curve | MoT - VFM (pp) | MoT - curve (pp) |
|---|---|---|---|---|---|
| 2030 | 0.160400 | 0.172989 | 0.171034 | -1.2589 | -1.0634 |
| 2050 | 0.822060 | 0.821498 | 0.830000 | +0.0562 | -0.7940 |

Worst absolute disagreement across FY2025-FY2050:
MoT vs VFM Base **1.8385 pp**;
MoT vs the dashboard curve **2.6830 pp**.

Both published delta columns are reproduced exactly by recomputation.

The three sources agree on the *shape* of light-fleet electrification to within
about two percentage points of share across a twenty-five year horizon. That
agreement is what the workbook establishes, and it is a statement about
**composition**, not about levels or revenue.

## 4. What lambda actually was

From the committed investigation evidence
(`artifacts/fleet_allocation_semantics/`), restated in
`legacy_lambda_allocation_summary.csv`:

- **Lambda was an allocation weight.** It decided how much of a single
  migration total `M` was subtracted from the Light RUC stream and how much
  from the PED stream.
- **It split a migration total between PED and Light RUC.** At FY2030,
  lambda = 0.377758, M = 4262.750 million km,
  taken from Light RUC 1610.289 and from PED
  2652.462. The two deductions sum to M exactly.
- **It was not a weight on Current versus MoT.** No such parameter existed in
  the pipeline, and the workbook contains no analogue of one.
- **The workbook validates the structural composition path, not the lambda
  coefficient.** The S-curve sheet compares BEV *shares*. Lambda appears
  nowhere in it.
- **The old implementation applied EV-inclusive proportions to an incompatible
  conventional-only envelope and therefore changed econometric levels.** The
  conserved universe was built from two conventional-only streams while the
  shares applied to it described a universe containing BEV and PHEV
  kilometres. At FY2030 that universe gap is
  5465.715 million km, and the optimiser had nothing to
  build EV kilometres from except the two conventional streams.

The old allocation is **not restored**. The transition weight introduced by
this branch is a different object with a different job: it is a governance
schedule moving reliance from a short-run econometric extrapolation to a
structural long-run source, it never touches a level, and it is bounded,
monotonic and exactly zero at the FY2030 anchor.

## 5. What carries forward, and what does not

See `defensible_vs_retired_method.csv`. In short: the separation of demand from
composition, VFM as the fleet-transition source, the official vintage as an
external structural cross-check, transparent Base/Fast/Slow composition,
explicit curve parameters and a preserved activity identity all carry forward.
Lambda-as-behaviour, EV-inclusive shares on a conventional-only envelope,
deductions from raw econometric streams, selection by proximity to an official
level, and shrinking-share expansion do not.
