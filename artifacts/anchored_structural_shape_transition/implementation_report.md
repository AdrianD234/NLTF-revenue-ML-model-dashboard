# Anchored Structural Shape Transition — implementation report

Branch `feature/anchored-structural-shape-transition`, from `main` at
`82d2db67459226a9445fa50b7049c7cebc4032be` (the PR #11 merge).

PR #11 is not unwound. BEFU26 remains the default comparator and
bridge-assumption vintage, MBU26 remains registered and selectable, and the
exact-VFM composition is still the production source.

## What this branch changes

The merged FY2031–FY2050 extrapolator anchors each stream on its own FY2030
econometric level and carries it forward on a single growth source: the Current
model's own long-horizon path for PED and Heavy RUC, and the vendored VFM pool
index for the Light RUC pool. Nothing in it moves toward the selected official
vintage's long-run shape.

This branch adds that transition, as a third independently governed vintage
role, and nothing else about the method changes:

- the econometric models still own the short-run level and dynamics;
- the FY2030 Current level remains the exact anchor;
- the selected **long-run shape vintage** supplies a growth SHAPE, never a
  level;
- VFM202405 still supplies the fleet composition;
- a transparent, monotonic governance weight moves reliance from the Current
  extrapolation to the structural source;
- λ is not restored.

## The method

For each stream, both legs are normalised to the FY2030 anchor so both equal
1.0 there:

    I_current_t     = unblended Current post-model level_t / Current FY2030
    I_structural_t  = shape-vintage level_t / shape-vintage FY2030

and blended geometrically:

    log(I_hybrid_t) = (1 - w_t)·log(I_current_t) + w_t·log(I_structural_t)
    Current_hybrid_t = Current_FY2030_anchor × I_hybrid_t

The weight is a cubic smoothstep over `u = clamp((t - 2030)/(T - 2030), 0, 1)`:

    w_t = 3u² - 2u³

chosen over a linear ramp because it has zero slope at both ends, so the path
leaves the anchor and arrives at the structural shape without a kink in level
**or** in growth rate. Both endpoints are exact (0 at FY2030, 1 at completion),
which is what makes the endpoint gates testable as equalities.

Three governed schedules — `early_structural` (T=2040), `balanced_structural`
(T=2045), `gradual_structural` (T=2050) — plus `unblended_current` (w≡0), which
is the control and the current production default.

### Why geometric, and why indices

Blending indices in log space is scale invariant, keeps a positive path
positive, and blends compound growth rates rather than kilometres or dollars.
It also makes the FY2030 anchor an exact fixed point: both indices are 1.0
there, so `1^(1-w) · 1^w = 1` for every weight. The anchor cannot drift under
any schedule.

### Shape, not level

At and after completion `w = 1`, so

    Current_hybrid_t / Official_t  ==  Current_2030 / Official_2030

identically. Current adopts the official growth shape while keeping its own
level. Measured on the Base case: the terminal Total NLTF ratio to BEFU26 is
**0.9930** for all three structural candidates, which is exactly the FY2030
anchor ratio. If the constructor ever started substituting official levels that
ratio would move to 1.0. It is asserted as a gate.

## The three governed roles

`official_comparator_vintage_id`, `bridge_assumption_vintage_id` and the new
`long_run_shape_vintage_id` are independent. The permanent matrix
(`role_independence_matrix.csv`) measures each leg:

| comparator | bridge | shape | max activity Δ | max Total NLTF Δ |
|---|---|---|---:|---:|
| BEFU26 | BEFU26 | BEFU26 | 0.000000 | 0.000000 |
| MBU26 | BEFU26 | BEFU26 | 0.000000 | 0.000000 |
| BEFU26 | MBU26 | BEFU26 | 0.000000 | 0.147130 |
| BEFU26 | BEFU26 | MBU26 | 77.689586 | 20.702425 |

Swapping the **comparator** changes nothing in Current. Swapping the **bridge**
changes revenue only — activity is bit-identical, because activity is built
from Current anchors and growth indices and the bridge supplies neither.
Swapping the **shape** changes long-run activity, and revenue follows.

Each leg asserts both that the expected thing changes and that the unexpected
thing does not, so no cell can pass vacuously.

### Plug-and-play

Shape capability is **derived** from what a pack publishes — the contiguous FY
window over which all five required activity series are positive and finite —
so a later PREFU/MBU/BEFU drop becomes shape-capable with no code change, and
one that stops short is refused. Both current vintages derive FY2024–FY2055.
Tested: a vintage missing a series is refused, one stopping before the anchor is
refused, one running to FY2060 registers the longer window, and a PREFU26-style
fixture with a materially different shape drives the constructor as data only.

The **pack manifest is authoritative**: a built pack replays on the shape
vintage recorded in its own manifest, mirroring what PR #11's closure amendment
established for the bridge. The registry default selects a shape source only
when a NEW pack is constructed.

## The legacy method, reconstructed

Read from `references/MBU26 v VFM202405_outputs_summary_V3 (1).xlsx`, sheet
`S-curve analysis (F&F)`, from cells rather than from the brief.

All four dials confirmed: peak uptake speed **0.0425**, ceiling **0.920487**,
midpoint **2038**, steepness **0.18468484617381886**. Steepness is *derived*
(`=4*C104/C105`), not independently typed — so the dials are mutually
consistent. The logistic is read verbatim from its cells, and the workbook turns
out to evaluate it on **two year conventions**: the June-year block uses the
June year, the calendar-year block adds half a year to centre a calendar
observation. Both are asserted, so a future edit to either fails loudly rather
than shifting the reconstruction six months.

Re-running the workbook's own logistic-linearisation regression reproduces its
published statistics to ~1e-15: R² **0.9525105818966445**, steepness off the
line **0.18943053341819233**, ceiling off the line **0.907314302990309**.

The three composition sources agree to within about two percentage points of
BEV share across FY2025–FY2050: max |MoT − VFM Base| **1.8385 pp**, max
|MoT − dashboard curve| **2.6830 pp**. That agreement is what the workbook
establishes, and it is a statement about **composition**, not about levels or
revenue.

### λ

From the committed investigation evidence, restated in
`legacy_lambda_allocation_summary.csv`:

- λ was an **allocation weight**, splitting one migration total `M` between the
  Light RUC and PED streams. At FY2030, λ = 0.377758, M = 4262.750 million km,
  taken from Light RUC 1610.289 and from PED 2652.462 — summing to M exactly.
- It was **not** a weight on Current versus MoT. No such parameter existed.
- The workbook validates the **composition path**, not the λ coefficient. λ
  appears nowhere in it.
- The old implementation applied EV-inclusive proportions to a
  conventional-only envelope — a universe gap of 5465.715 million km at FY2030 —
  so the optimiser had nothing to build EV kilometres from except the two
  conventional streams. That is why it changed econometric levels.

λ stays retired. The transition weight is a different object with a different
job: a governance schedule moving reliance between two growth sources, bounded,
monotonic, exactly zero at the anchor, and never touching a level.

## Candidate results — Base case, Total NLTF

| candidate | completion | FY2031 seam | FY2040 | FY2050 | ratio to BEFU26 FY2050 | max annual growth |
|---|---|---:|---:|---:|---:|---:|
| Current unblended | — | +5.115% | 10588.08 | 17264.69 | 1.3373 | 5.74% |
| Early structural | FY2040 | +5.087% | 9093.71 | 12820.21 | 0.9930 | 4.69% |
| Balanced structural | FY2045 | +5.102% | 9443.27 | 12820.21 | 0.9930 | 4.79% |
| Gradual structural | FY2050 | +5.108% | 9790.33 | 12820.21 | 0.9930 | 4.82% |

The three structural candidates necessarily converge at FY2050 — all reach
w = 1 by then. They differ only in the path taken, which is what the FY2040
column shows.

The FY2031 seam is nearly identical across all four (5.087%–5.115%), which is
the smoothstep's zero slope at the anchor doing its job: no candidate introduces
a kink at the join.

### What is actually at stake

BEFU26's own light-petrol VKT falls to **29.2%** of its FY2030 level by FY2050
while its Light RUC pool grows **2.61×**. The Current extrapolation has petrol
VKT still *rising*. By FY2050 the unblended Current petrol path sits at
**3.77×** BEFU26's, and Heavy RUC at **1.29×**.

MBU26 agrees with BEFU26 closely on both shapes (petrol index 0.2920 vs 0.2919;
pool 2.6130 vs 2.6081), which is evidence the structural shape is stable under a
change of vintage rather than an artefact of one release. That matters for the
"stability under a later official vintage" criterion.

## Deliberately NOT done

- **No production default is changed.** Every committed pack still records
  `unblended_current`, and a rebuild today reproduces merged main.
- Exact-VFM composition is **not** replaced with official embedded shares. PR
  #11's composition-refresh candidate remains an opt-in owner decision, and the
  embedded shares appear here as audit-only comparisons.
- λ, the mobility-universe optimiser, PED retention and the declining-share
  expansion are **not** restored.
- No P1.3 or other model-development programme was started.

## A limit worth an owner's eye

The BEFU26 petrol structural index reaches **0.292** at FY2050, against a
governed minimum cumulative index of **0.25**. It passes, but the margin is
thin: a future vintage with somewhat stronger electrification would trip the
guard. That is a deliberate fail-closed, and the correct response would be to
examine the vintage, not to widen the guard.

## Two precision defects found and fixed at source

Writing the preservation gates surfaced two issues that would have quietly
turned "unchanged exactly" into "unchanged to ~1e-12":

- the frozen baseline was written with pandas' default float formatting, which
  drops the last bits — now written at `%.17g`;
- pandas' default C parser loses precision *reading* 17-digit floats — the
  baseline is now read with `float_precision="round_trip"`.

Neither was absorbed into a tolerance. Gates 2–6 are exact equalities.

## Regeneration

    .venv\Scripts\python.exe scripts\build_anchored_shape_preconditions.py
    .venv\Scripts\python.exe scripts\build_anchored_shape_workbook_inventory.py
    .venv\Scripts\python.exe scripts\build_anchored_shape_legacy_reconstruction.py
    .venv\Scripts\python.exe scripts\migrate_official_vintage_registry_long_run_shape.py
    .venv\Scripts\python.exe scripts\build_anchored_shape_merged_baseline.py
    .venv\Scripts\python.exe scripts\build_anchored_shape_candidates.py
    .venv\Scripts\python.exe scripts\build_anchored_shape_closure_evidence.py
