# Closure pass — response to the consultant review

The review held PR #12 for a bounded amendment. This records what each item
turned out to be and what was done. The architecture was not reopened.

## 1. The analyst preview was a no-op — confirmed, fixed

`_render_long_run_shape_controls` returned state that nothing consumed.
`long_run_shape_state` appeared exactly once in `app.py`: its own assignment.
The finding was exactly right.

**Why 22 tests passed anyway.** They tested option availability, session-key
separation, labels and wording. Not one asserted a plotted value. A feature can
be comprehensively "tested" and still do nothing, and that is a lesson about
what those tests were worth rather than about how many there were.

**The fix.** The selection enters at the PACK, upstream of the whole overlay
chain. That placement is load-bearing: the sensitivity, macro-replay, VFM and
FED-policy overlays *do* modify FY2031–FY2050 rows (measured: 40 rows per
series), so substituting after them would have discarded the macro and policy
treatment on exactly the years the preview is about.

- slots 8/9 on `ev_uptake_key` carry the schedule and shape vintage;
- the selection is folded into the pack **signature**, because the frames it
  changes are cached on the signature rather than the uptake key;
- only rows already labelled `post_model_extrapolation` are replaced, so
  actuals, the econometric window and official rows are untouched by
  construction;
- the candidate is built through the same governed constructor the pack builder
  uses, so preview and production cannot diverge.

**34 behavioural tests** now assert on values through the real path: FY2040
differs across all four schedules and orders as predicted
(early < balanced < gradual < unblended); FY2030 and earlier are bit-identical;
official and actual rows are bit-identical; the only segment that changes is
`post_model_extrapolation`; Base and comparison keep their own anchors; the
MBU26 audit leg differs from BEFU26; and the hidden leaf `light_petrol_vkt` —
which the chart does not publish past FY2030 — moves in the line reconciliation
with residuals still closing under 1e-6.

## 2. Owner decision and promotion — done

`balanced_structural` is the production default, held in one governed constant,
`PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID`. Both packs rebuilt; the promotion
audit reports **840 changed rows per engine, all FY2031–FY2050 post-model**,
with actuals, the econometric window, fitted states and both official spines
unchanged. The audit fails if anything else moves *and* if nothing moves.

### A real bug the promotion introduced, caught by the evidence gate

The preview short-circuited whenever the selected schedule was `unblended` — 
correct only while the pack itself was unblended. With `balanced` promoted,
selecting "Current unblended" fell through to the pack and displayed the
balanced path under the wrong label. Fixed: the skip is keyed on whether the
selection *matches what the pack was built with*, and the cache marker is
appended for every explicit selection.

No test caught this. The screenshot gate's distinctness check did — which is
the argument for tying visual evidence to numbers.

## 3. Conflict convergence — added

15 tests. The conflict effect is real inside the governed window and exhausted
by FY2031, and each Low/Medium/High path converges to the **selected hybrid**
Base path. The decisive assertion is that it must *not* equal the unblended
Base — the signature of a partially wired preview.

One correction: the 20-quarter window ends 2030Q4, which is **FY2031** under
the repo's June-year convention, so the input window and the post-model layer
overlap by one FY. My first assertion claimed the window ended at FY2030. The
test now pins the real window and proves convergence on values rather than
inferring it from the calendar.

## 4. Reconciliation driven by the governed registry — done

The hardcoded identity dictionary is gone. Expected identities are evaluated
generically from `FORMULA_DEFINITIONS`' signed `terms`. The audit stays separate
from the constructor — the constructor writes each aggregate longhand, the
audit evaluates the registry — so agreement is evidence, not tautology. A
non-vacuity check fails if any governed aggregate the layer emits was not
reconciled. All 14 checked; worst residual 0.0.

## 5. Circular activity evidence — replaced

- Expected Light pool is now the FY2030 anchor × hybrid pool index, compared
  against the three emitted classes (146 distinct expected values across 160
  rows), instead of comparing the class sum against itself.
- The PED identity is tested against the scenario-input population path
  weighted by the raw-audit VKTpc — both **inputs** — instead of a population
  derived by dividing the two outputs under test.
- The hardcoded `class_sum_residual = 0.0` is gone. Residuals are computed and
  land at ~7e-12 (1.5e-16 relative), i.e. float noise on real arithmetic.

## 6. Future-vintage eligibility — tightened

`supports_long_run_shape` now requires coverage through FY2050, not merely past
the anchor. Tests: a vintage ending FY2044 is refused; one reaching exactly
FY2050 is accepted.

## Browser evidence

Eight screenshots, desktop 1920×1080 and laptop 1440×900, zero console errors,
against the promoted packs. FY2040 Total NLTF read from the rendered figure:

| candidate | FY2040 Total NLTF ($bn) |
|---|---:|
| Current unblended | 10.484 |
| early | 9.143 |
| **balanced (production)** | **9.461** |
| gradual | 9.774 |

The capture fails rather than reports success if the values are not distinct,
if the long-run segment is not dashed, if the FY2030 seam point differs between
the solid and dashed segments, or if any console error appears.

Three defects in the capture itself had to be fixed first, each of which would
have produced convincing but false evidence: reading `trace.y` (undefined under
this Plotly build's binary encoding), an exact-string option matcher that
selected nothing, and — worst — waiting on the caption, which renders *above*
the chart and so updates while the figure below is still the previous render.
That last one photographed one stale chart four times.

## Validation after promotion

| Gate | Result |
|---|---|
| Full local pytest | **1266 passed**, 50 skipped, 41 deselected, **0 failed** |
| Streamlit AppTest | 38/38 |
| Deployment readiness | PASS |
| Replay-seed diagnostic | PASS |
| Extract validation | 34 PASS, 0 FAIL |
| Promotion impact audit | PASS - 840 rows per engine, all FY2031-FY2050 post-model |
| Browser evidence | 8 screenshots, 4 distinct paths, 0 console errors |
| Runtime hash re-freeze | 13 of 71, each audited |

New test counts: 34 preview behaviour, 15 conflict convergence, 18 role
independence, 33 transition/blend, 31 hard gates, 22 front end.
