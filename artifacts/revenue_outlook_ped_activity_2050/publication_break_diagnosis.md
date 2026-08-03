# Publication break diagnosis — PED VKT per capita and Light petrol VKT

Starting main SHA: `31b74615d9d91bb001516282fd3a1177292f1e08` (PR #20).
Evidence: `publication_layer_coverage.csv`, produced by
`scripts/diagnose_ped_activity_publication.py`. Both engines return identical
spans, so every statement below holds for `ensemble` and `ar1` alike.

## Why the merged report was misleading

The workshop validation concluded Light petrol VKT "has no Current path after
FY2030". That is true of the **generic persisted chart rows** and of the
**final rendered rows**, but it was read as evidence that no governed forecast
existed. It does exist. Four layers were being conflated, and they disagree:

| Layer | What it is | `ped_vkt_per_capita` | `light_petrol_vkt` |
|---|---|---|---|
| **L1** generic persisted chart rows | `data/*/revenue_chart_rows.parquet` | FY2025–FY2050 | **EMPTY** (no row in any role or grain) |
| **L2** additive view-time rows | `cached_scenario_overlay_rows` + `_append_missing_official_rows` | FY2025–FY2050 | Current **FY2026–FY2030**; official FY2026–FY2050; Actual FY2003–FY2025 |
| **L3** governed post-model source | line reconciliation + `build_post_model_extrapolation_annual` | FY2025–FY2050 (post-model FY2031–FY2050) | FY2025–FY2050 (post-model **FY2031–FY2050**) |
| **L4** final rendered rows | `_filter_series_rows_with_fallback` | annual FY2025–FY2050; **quarterly 2026Q1–2030Q4** | annual **FY2026–FY2030**; quarterly 2025Q3–2030Q2 |

L3 carries governed FY2031–FY2050 Current values for **both** series. Nothing
needs to be forecast; the values are already constructed and already reconciled.

## First layer at which each series disappears

The two series do **not** fail at the same layer, and neither fails where the
merged report implied.

**`ped_vkt_per_capita` — annual: does not fail at all.** It already publishes
FY2025→FY2050, stamped `forecast_segment = post_model_extrapolation`. Sections 6
and 7 of the brief, and annual blocking tests 1–18, are already satisfied for
this series on merged main. Its only defect is quarterly.

**`ped_vkt_per_capita` — quarterly: fails at L4.** Native quarters stop at
2030Q4. The diagnostic records `L4_quarterly_used_fallback = False`: the
fallback in `_filter_series_rows_with_fallback` is keyed **per trace**, not per
period. The Base trace *has* native quarters, so it never enters
`missing_traces` and the governed derivation is never invoked for FY2031–FY2050
at all. This is a per-period gap being tested by a per-trace condition.

**`light_petrol_vkt` — annual: fails at L2.** The series is absent from the
governed 14-row `series_trace_contract` and from `DISPLAY_SERIES_ORDER`, and
every runtime chart-row builder in `revenue_outlook` filters on that list — so
it never becomes a persisted chart row (L1 empty). The rendered FY2026–FY2030
Current values come from the additive view-time PED-bridge path, whose
econometric horizon ends at FY2030. That additive path never consults the L3
post-model rows, so the Current line stops at FY2030 while the officials run to
FY2050.

`post_model_chart_rows` is therefore **not** the break for either series. For
`ped_vkt_per_capita` it works correctly. For `light_petrol_vkt` it is merely the
last of several layers that drop the series; it is unreachable because the
series has no FY2030 chart row to template from, and it has none because
`DISPLAY_SERIES_ORDER` excluded it twenty layers earlier.

## Section 5 checklist

- **Do both series fail at the same layer?** No. `ped_vkt_per_capita` fails only
  at quarterly L4; `light_petrol_vkt` fails at annual L2.
- **Is a missing FY2030 chart template involved?** Yes for `light_petrol_vkt`,
  but as a *consequence*, not a cause — it has no chart row at any year.
  Not involved for `ped_vkt_per_capita`, which templates correctly.
- **Is `DISPLAY_SERIES_ORDER` involved?** Yes, and it is the root cause for
  `light_petrol_vkt`. Documented deliberately at
  `revenue_outlook_series_coverage.py:7-16`.
- **Does `app.py` add one series through a special path?** Yes — two.
  `_revenue_outlook_stream_options` adds the "Light petrol VKT" label by hand
  once its two PED companions are present, and `_append_missing_official_rows`
  restores its BEFU26/MBU26 official rows at view time. Neither restores a
  Current post-FY2030 path.
- **Does the fast policy runtime reproduce the omission?** Yes — it materialises
  the same chart rows, so it inherits both gaps.
- **Do annual values exist while quarterly derivation receives truncated rows?**
  Yes, and this is the `ped_vkt_per_capita` defect exactly.
- **Does a cache key or filter remove the rows?** No. No cache key drops them;
  the membership filter on `DISPLAY_SERIES_ORDER` does.

## Constructor identity (verified, not assumed)

The annual constructor derives `scenario_population` as exactly
`petrol_fy / vktpc_fy` from the same raw path
(`post_model_extrapolation.py:290-297`). Consequently, for one common
per-fiscal-year scale factor

```
scale_fy = target_petrol_fy / sum_q(raw_petrol_q)
```

both annual constraints close **exactly and simultaneously**:

```
sum_q(scale_fy * raw_petrol_q) = target_petrol_fy      (by construction)
sum_q(scale_fy * raw_vktpc_q)  = target_vktpc_fy       (because
    target_vktpc = target_petrol * 1e6 / (petrol_fy/vktpc_fy))
```

and the per-quarter identity `petrol_q = vktpc_q * pop_q / 1e6` is preserved
because both series are scaled by the same factor. **No constrained correction
or KKT solve is required**; section 12's preferred construction closes in closed
form, leaving only floating-point residual. The section 12 fallback is therefore
implemented as a guard, not a code path expected to run.

## Governed inputs confirmed present through FY2050

- `raw_quarterly_forecast_audit`: `ped_vkt_per_capita`, 2026Q1–2050Q4, both
  scenarios, `decision_facing = False`.
- `scenario_inputs/scenario_input_wide`: PED `population`, 2026Q1–2050Q4, 200
  rows, zero nulls, both scenarios.
- Annual convention is **sum-preserving**: FY2027–FY2030 annual values equal the
  exact sum of their four native quarters. Note that
  `_is_average_preserving_unit` would classify the unit string "VKT per capita"
  as average-preserving; the raw-shape scaling construction bypasses that helper
  entirely and is sum-preserving by construction.

## Consequence for the fix

Two distinct corrections are required, not one:

1. **`light_petrol_vkt` annual** — extend the additive view-time publication
   path so it also carries the L3 post-model Current rows for FY2031–FY2050,
   leaving the rendered FY2026–FY2030 values byte-identical and without
   touching `DISPLAY_SERIES_ORDER` or the series-trace contract.
2. **Both series, quarterly** — make the fallback gap-aware per period rather
   than per trace, and derive FY2031–FY2050 quarters jointly from the governed
   raw shape and scenario population by the single-scale-factor construction
   above.
