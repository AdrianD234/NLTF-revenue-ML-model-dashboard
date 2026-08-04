# Implementation report — PED activity publication through FY2050 / 2050Q2

Branch `fix/revenue-outlook-ped-activity-through-2050`, from
`31b74615d9d91bb001516282fd3a1177292f1e08` (PR #20).

**Status: implementation and targeted validation complete. Isolated full suite,
push, draft PR and clean-clone CI outstanding.**

## Outcome

Verified end to end through the running application, both engines, from
rendered Plotly data:

| series | annual | quarterly |
|---|---|---|
| `ped_vkt_per_capita` | FY2025–FY2050 | **2026Q1–2050Q2** |
| `light_petrol_vkt` | FY2026–FY2050 | **2025Q3–2050Q2** |

Each Current path renders as an econometric segment plus a post-model segment
sharing FY2030 (annual) or 2030Q2 (quarterly) — one continuous line, not two.
No 2050Q3 or 2050Q4 point exists. Quarterly uncertainty stays withheld (zero
band traces). The short-coverage note is absent because coverage is complete,
not because it was suppressed.

## What was wrong, in the order it was found

1. **The diagnosis in the merged report was wrong about the layer.**
   `ped_vkt_per_capita` annual already reached FY2050 on merged main.
   `light_petrol_vkt` failed at the additive view-time layer, not at
   `post_model_chart_rows`, because it is absent from `DISPLAY_SERIES_ORDER`
   and so no runtime chart-row builder ever emitted it. Four layers were being
   conflated; `publication_layer_coverage.csv` separates them.

2. **The quarterly fallback tested the wrong thing.** It asked whether a whole
   trace was missing, so a trace with any native quarters counted as complete
   and the last twenty years were never derived at all.

3. **Cross-engine contamination.** Resolving the pack directory from the
   process-wide active engine read one engine's raw quarterly path against
   another engine's annual targets (FY2032 raw shape differs ~5%). Caught by
   the annual-closure guard, which is why that check is an error and not a
   tolerance.

4. **The PED identity did not close against the scenario population** — the
   Option B investigation. Root cause below.

5. **The joint construction was not authoritative.** Light petrol VKT has no
   native quarters, so the generic per-trace fallback split its whole horizon
   with the Denton rule first. Each series still reconciled to its own annual,
   so nothing looked wrong, but the pair was free to drift apart quarter by
   quarter.

6. **Trace identity and period stamping** — found only by browser acceptance.
   The comparison line rendered as two differently-named traces, and fixing
   that exposed that the period fields were never stamped explicitly.

## The population restatement (the Option B answer)

First identity-changing stage, named exactly:

    fuel_price_scenario.apply_treasury_macro_to_chart_rows

Its factors come from `baseline_macro_annual_factors`, which publishes a
**separate factor per series**. At FY2030:

| | value |
|---|---|
| `light_petrol_vkt` factor | 1.014896 |
| `ped_vkt_per_capita` factor | 1.000916 |
| ratio | **1.013967** |
| measured Treasury ÷ legacy population | **1.013970** |

The ratio of the two published factors **is** the Treasury-versus-legacy
population ratio, on both engines and both scenarios, to a systematic −3e-6.
The replay is internally consistent — `factor(total) = factor(per_capita) ×
factor(population)` — and it restates the population path, so the
`scenario_input_wide` population is the **legacy pre-replay** one.

**The identity is preserved against the Treasury-baseline-restated population
basis. It is not preserved against the unadjusted legacy population.** That
distinction is carried in eight provenance fields on every derived row, not
left to the reader to infer.

The migration/lambda path was independently ruled out: the default
`fixed_light_only` bridge moves petrol km by 0.0.

## Non-blocking limitation (inherited, not introduced)

`baseline_macro_annual_factors` covers FY2025–FY2030, and the overlay carries
the terminal FY2030 factor forward unchanged through FY2050. The independently
observed Treasury ÷ legacy population relationship would otherwise continue
rising, reaching a ~0.14% difference by FY2050.

> The long-run macro overlay currently carries the terminal FY2030
> population-restatement factor through FY2050. This is inherited repository
> behaviour rather than a new quarterly-publication assumption. Reviewing the
> long-run factor continuation is outside the scope of this PR because changing
> it would move governed annual Light petrol VKT.

## Non-movement

The publication helper is strictly additive: **2673 pre-existing rows compared,
0 changed, max absolute change 0.0**; 40 rows added, all `light_petrol_vkt`
june_year. `ped_vkt_per_capita` annual, `ped_volume`, PED revenues, Actual
history and official comparators are unchanged. **No annual value moved**, so
the owner's authorised exception permitting decision-facing
`ped_vkt_per_capita` to move was not needed and not used.

One governed exception exists, in the uncertainty pack: Light petrol VKT
FY2031–FY2050 band rows are **re-centred** onto the now-published Current line.
All six columns move by exactly the same factor (1.014895961), so relative
widths, draws, copula, quantile map, seam and plateau are unchanged and 50%
stays nested inside 80%. The test now holds this to a rigid-rescale assertion
rather than exempting it.

## Identity residuals

| check | worst relative residual |
|---|---|
| annual VKT-per-capita / petrol closure | 3.4e-16 |
| quarterly → annual reconciliation (98 combinations) | 3.5e-16 |
| cross-series quarterly identity (80 quarters × 2 engines) | 4.0e-16 |

No negative quarter, no duplicate native/derived key, native quarters
unchanged.

## Packs

Rebuilt in the required order and each built twice with no source change
between, after the final source edit:

| pack | files | byte differences |
|---|---|---|
| replay cache | 72 | 0 |
| quarterly display | 8 | 0 |
| policy runtime (last) | 202 | 0 |

The quarterly-display pack reported OK rather than stale but its own contract
changed (the new population-lineage columns), so it was rebuilt on the "stale
**or** affected" rule.

## Tests

New module `tests/test_revenue_outlook_ped_activity_2050.py`, 34 tests across
macro-restatement lineage, annual publication and non-movement, quarterly
identities and seam, the sum-preserving convention, and engine isolation.

Two existing contracts were updated rather than deleted:

- `test_light_petrol_vkt_current_rows_really_do_stop_at_fy2030` →
  `test_light_petrol_vkt_current_rows_now_reach_fy2050`. Its docstring had
  anticipated exactly this change.
- `test_ped_bridge_modes_materialize_raw_optimized_and_reconcile` scoped to the
  econometric window, with the post-model rows asserted to be correctly
  labelled so nothing escapes the check by lacking a bridge audit row.

Targeted results against current packs: **299 passed** (182 + 117), zero
failures.

## Outstanding

- Isolated complete pytest suite (running at time of writing).
- Extract validation, deployment readiness, replay-seed diagnostic, sign
  guards, replay parity.
- Screenshots (the Browser pane was not compositing frames, so rendered values
  were captured from Plotly `calcdata` instead — the values are recorded above
  and in the browser acceptance notes).
- Push, draft PR, clean-clone CI.
