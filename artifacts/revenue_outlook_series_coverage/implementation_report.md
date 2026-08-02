# Revenue Outlook series coverage and quarterly display

Branch `fix/revenue-outlook-series-quarterly-coverage`, from
`48a499bdfb6a4d85888b3f3c27af970814048e10`.

Two defects, one root cause: what the Revenue Outlook selector OFFERS and what
the runtime MATERIALISES are decided in different places, and they had drifted.

## A. The missing BEFU26 Light petrol VKT line

Full trace in [`befu26_light_petrol_diagnosis.md`](befu26_light_petrol_diagnosis.md).

The source was never the problem. `light_petrol_vkt` is published in both
registered vintages over FY2003-FY2055 in `million km`, under its own canonical
id, with no alias in the path. It is dropped at the runtime hop: every chart-row
builder in `revenue_outlook` filters on `DISPLAY_SERIES_ORDER` first, and the
series is not in that list. The selector offers it anyway because
`app._revenue_outlook_stream_options` adds the label by hand.

Evidence, in [`official_series_inventory.csv`](official_series_inventory.csv)
and [`series_alias_audit.csv`](series_alias_audit.csv):

| Check | Result |
| --- | --- |
| Selectable series | 18 |
| Selectable series with both official traces materialised | 17 |
| Selectable series with neither | 1 (`light_petrol_vkt`, in BOTH vintages) |
| Alias rows whose target lands on no source row | 0 |
| BEFU26 vs MBU26 `light_petrol_vkt` June years that differ | 26 of 53 |

MBU26 is missing for the same reason and is restored by the same change.

### Resolution: preference order B, not A and not C

An existing source row is materialised. No value is derived, copied between
vintages, substituted from the Current model, interpolated or extended past a
vintage's own source horizon; `official_rows_for_series` reads
`OfficialVintagePack.official_annual` and carries the published number through
in its published unit.

`DISPLAY_SERIES_ORDER` is deliberately **not** edited. Adding the id there would
also route the series through `_runtime_current_rows` - replacing the
PED-bridge-selected Current values with raw pack values - plus
`_fan_availability_frame`, `_runtime_future_revenue_forecasts`,
`_runtime_bridge_components` and `_series_order_index`. That reaches the
current-model path and chart presentation, which this branch does not own. The
rows are materialised additively instead: `missing_official_rows` emits only
`(series, trace, period)` keys the chart pack does not already carry, so no
published value can move. Asserted, not assumed - see
`test_restoring_the_series_moves_no_other_official_value`.

## B. The quarterly display contract

Before: three series carried native quarterly rows and only to 2030Q4; every
other series was disaggregated live on each Streamlit rerun by an undeclared
Denton solve inside `app.py`. Nothing recorded which series may be split, by
what rule, against what evidence, or how far.

[`quarterly_series_contract.csv`](quarterly_series_contract.csv) now carries one
row per selectable series - 18 of 18, each exactly once - and
`derive_quarterly_rows` is the single builder that reads it.

Classification of the 18:

| Class | Count | Series |
| --- | --- | --- |
| Native quarterly, annual sum | 2 | `light_ruc_net_km`, `heavy_ruc_net_km` |
| Native quarterly, annual rate | 1 | `ped_vkt_per_capita` |
| Annual flow, derived quarterly | 14 | the remaining activity and revenue series |
| Annual flow, derived by governed identity | 1 | `total_fed_ruc_net_revenue` |
| Annual end-of-period / level | 0 | none selectable |
| Annual rate schedule | 0 | none selectable |
| Fixed administrative component | 0 | none selectable |
| Unsupported for quarterly display | 0 | none |

The last four classes are part of the vocabulary and, for end-of-period, of the
code: `interpolate_end_of_period_quarters` is implemented and unit-tested on
synthetic anchors so a level series added later has a governed path rather than
being summed. No selectable series is classified into them today, and
`test_no_selectable_series_is_classified_end_of_period_or_fixed` records that as
a fact a future change has to come back through.

### Methods

* **Annual flow** - Denton proportional first difference against a governed
  seasonal indicator, benchmarked so the four quarters sum to the June-year
  value. The indicator mapping (PED family to `ped_vkt_per_capita`, Light/PHEV
  to `light_ruc_net_km`, Heavy to `heavy_ruc_net_km`) is the one already
  shipping; it is now declared rather than implied by string prefixes.
* **No governed indicator** - `total_ruc_net_revenue`, `net_mvr_revenue` and
  `total_nltf_net_revenue` use a flat indicator. That is the documented neutral
  allocation (minimum quarter-to-quarter movement subject to exact closure), not
  a divide-by-four: a rising annual path still produces a rising quarterly path.
* **Accounting identity** - `total_fed_ruc_net_revenue` is composed from the
  derived `net_fed_revenue` and `total_ruc_net_revenue` quarters, so the
  identity holds at every quarter and not merely on the annual total.
* **Rate** - `ped_vkt_per_capita`. The published annual km/person is annual VKT
  over mean-year population, so the NATIVE quarters sum to within 0.07-0.29% of
  it rather than exactly. Derived quarters, where a trace has none, partition the
  annual anchor exactly. Both facts are in the contract's `limitation` column.
* **Rate-priced revenue** - a volume-only indicator puts a mid-year price step
  in the wrong quarters. The planned PED path steps +12c at **2027Q1** and +6c
  at **2028Q1**, both inside a fiscal year, so benchmarking FED revenue on VKT
  alone spread each uplift back across the two quarters *before* it took
  effect. `gross_ped_revenue`, `gross_fed_revenue` and `net_fed_revenue` are
  now timed on `volume x governed quarterly $/L`, read from
  `rate_paths.ped_quarterly_rate_schedules`. Measured on the BEFU26 path, the
  implied effective-rate step is now 1.1702 against a governed 1.1714 at
  2027Q1 and 1.0733 against 1.0731 at 2028Q1, while the volume path moves less
  than 2% across the same pair - a step, not a ramp.
* **RUC revenue** - deliberately *not* rate-timed. `rate_paths` derives
  quarterly RUC factors only for the FED policy counterfactuals, not a base
  nominal path, so there is no governed quarterly RUC rate schedule to time
  against. Inventing one is exactly what section 3 forbids. The limitation is
  recorded in the contract instead: a mid-year RUC rate change would appear
  spread across its fiscal year.
* **Policy steps** - the step calendar is read from
  `rate_paths.fed_policy_affected_periods` and never restated. The FY2027 12c
  window stays at 2027Q1-Q2.

### Closure

Annual reconciliation is a hard constraint, not a target. The Denton constraint
is exact in exact arithmetic; the remaining double-precision remainder is
removed by solving the last free quarter as `benchmark - math.fsum(rest)`. Over
the built pack:

* 2,093 (series, trace, June year) groups reconciled;
* worst relative residual **2.2e-16** - about one ulp;
* declared tolerance 1e-12 relative, four orders above the observed worst, so a
  real break cannot hide inside it;
* 0 negative derived quarters. Denton's smoothness objective drove the near-zero
  BEV and PHEV histories below zero; clipping alone would have broken closure, so
  the two are resolved together (clip, re-spread proportionally over the quarters
  still free, repeat).

### Horizon

`display_horizon_filter` cuts on the FISCAL year containing a quarter, not its
calendar year - 2050Q3 is an FY2051 quarter. Official annual sources publish to
FY2055; nothing beyond FY2050/2050Q2 reaches the pack. The cut is doing real
work, not filtering an empty tail
(`test_official_source_extends_past_the_display_horizon`).

### What changed for the reader

| Series class | Quarterly before | Quarterly after |
| --- | --- | --- |
| `light_ruc_net_km`, `heavy_ruc_net_km`, `ped_vkt_per_capita` | native to 2030Q4, then nothing | native unchanged to 2030Q4, derived FY2031-FY2050 |
| Official comparators, all series | derived live per rerun, to FY2055 | derived once offline, cut at FY2050 |
| `light_petrol_vkt` | no official annual, so no official quarters | Actual FY2003-2025, BEFU26 and MBU26 FY2026-2050, quarters to 2050Q2 |

Native rows are never rewritten or shadowed: no derived row shares a
`(series, trace, period)` key with a published one
(`test_native_quarterly_rows_are_not_shadowed_or_rewritten`).

## Deliverables

| Path | What it is |
| --- | --- |
| `model_dashboard/revenue_outlook_series_coverage.py` | contract, builders and the pure API |
| `data/revenue_outlook_quarterly_display/` | materialised pack, 387 KB, hash-backed |
| `scripts/build_revenue_outlook_quarterly_display_pack.py` | the builder |
| `scripts/build_revenue_outlook_series_coverage_diagnosis.py` | the diagnosis evidence |
| `tests/test_revenue_outlook_series_coverage.py` | 45 tests |

## Performance

No workbook is loaded at runtime. A named lookup is a boolean filter over an
already-loaded frame:

| Operation | Cost |
| --- | --- |
| Cold pack load (once per process) | 55 ms |
| `quarterly_rows_for_selected_series` | 3.5-5.8 ms |
| Section 8 budget | 50 ms |

The source digest is memoised per process (hashing the vintage tree is ~15 ms
and a rerun would otherwise pay it every lookup); `build_quarterly_display_pack`
and the tests call `clear_caches()`. A pack whose sources have moved raises
`QuarterlyDisplayPackStale` with the rebuild command rather than serving old
numbers.

## Validation

Run in an isolated `git worktree` at this branch's head, so the concurrent
edits present in the development working tree could not contaminate the result.

| Check | Result |
| --- | --- |
| Full pytest | **1,596 passed, 50 skipped, 44 deselected, 0 failed** |
| New coverage suite | 45 passed |
| Official-vintage / series-identity / rate-paths | 121 passed |
| Revenue Outlook / trace-identity / runtime-manifest | 64 passed |
| `compileall` over `model_dashboard`, `scripts`, `tests`, `app.py` | clean |
| Pack built twice | byte-identical |
| Committed pack vs fresh build | identical (asserted by test) |
| Diagnosis artifacts regenerated | byte-identical |

Two notes on how that run was obtained, because both look like defects and
neither is one:

* A bare worktree fails 19 tests in `test_cone_landscape_validation`,
  `test_curated_data` and `test_ensemble_composition_validation` with
  `FileNotFoundError` on `artifacts/curated_data/*`. Those files are gitignored
  and generated locally. **The same 19 fail identically on `main`** - it is an
  environment prerequisite, not a regression. Seeding the worktree with the
  locally generated artifacts makes all 20 pass.
* Three attempts at a single-process full run died mid-suite with exit 127 (a
  process kill, no failure summary), at 15%, 17% and 66% - a different point
  each time, which is the signature of memory pressure rather than a failing
  test. Running the same 121 test files as 13 separate processes completed
  green end to end, which is the result above.

## Handoff to the integration agent

`app.py`, `revenue_chart_layers.py`, the UI controls, chart presentation, the
policy-state runtime and the uncertainty methodology are untouched. The API to
wire in:

```python
from model_dashboard.revenue_outlook_series_coverage import (
    canonical_series_id,          # label or alias -> canonical id, raises on unknown
    missing_official_rows,        # official rows the chart pack lacks; concat, never merge
    quarterly_rows_for_selected_series,   # pack lookup, plus derivation for runtime-only traces
    quarterly_coverage_status,    # the owner-facing table
    display_horizon_filter,       # the FY2050 cut, applied on fiscal not calendar year
)
```

Two things the integration must carry:

1. **`light_petrol_vkt` current-model quarters are not in the pack.** The
   Current annual rows for that series are built at runtime by
   `_append_selected_light_petrol_vkt_rows` from the PED bridge audit, so the
   offline build cannot see them. Pass them as `annual_rows=` and they are
   derived under the identical contract. The same applies to conflict paths and
   policy states.
2. **Derived rows must stay visibly derived.** Every row carries
   `coverage_row_type=derived_quarterly_from_governed_annual`,
   `empirical_or_derived=derived`, its `derivation_method`, `seasonal_basis`,
   `annual_source_period`, `annual_source_value` and closure residual. Official
   comparator quarters carry
   `source_basis="derived quarterly presentation from official annual source"`.
   A hover or download that drops those columns would present a benchmarked
   interpolation as published official data.

## Not done, and why

* `DISPLAY_SERIES_ORDER` is unchanged - see A above.
* The live `_disaggregate_annual_rows_to_quarterly` path in `app.py` is still
  there. Replacing it is the integration agent's call; this branch supplies the
  governed equivalent and leaves the switch to the branch that owns `app.py`.
* Conflict-path and FED-policy quarterly lineage stays with the policy runtime.
  The builder accepts those annual rows and applies the same contract; it does
  not reimplement the policy replay.
* The deferred R2/e2e maintenance tasks are untouched.
