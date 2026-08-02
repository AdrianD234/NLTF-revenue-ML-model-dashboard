# Workshop Revenue Outlook build: fewer controls, horizon capped at FY2050

Branch `workshop/revenue-outlook-ui-slim-2050`, cut from `main` at
`48a499bdfb6a4d85888b3f3c27af970814048e10` (the PR #16 merge commit).

Four presentation changes. No modelled value moves: every change either hides a
surface, stops work that had no consumer, or filters rows the page displays.

## 1. The VFM petrol-retention sensitivity is no longer a reader control

The checkbox, its help text and its caption are gone from the lever accordion,
and no other Revenue Outlook surface mentions it.

The typed field `RevenueScenarioComputationKey.ped_retention_sensitivity` and
the backend overlay are untouched, for compatibility and audit. What changed is
that production never *builds* a key carrying `True`:
`_production_ped_retention_sensitivity()` returns `False` without consulting
session state at all, so a stale `True` persisted by a reader's browser cannot
reactivate the overlay. `_discard_withdrawn_revenue_outlook_state()` also drops
the key on page entry.

Both construction sites are covered: the single-view lever accordion and the
compare-mode Scenario B key.

## 2. The MoT VFM Fast/Slow analyst layers are paused

Withdrawn from the public dashboard:

- MoT VFM Fast uptake path
- MoT VFM Slow uptake path
- MoT VFM Fast–Slow structural range
- the Fast–Slow range audit toggle
- the envelope caption and its CSV download
- the corresponding "Show on chart" options and legend entries

This is a pause, not a deletion. `cached_vfm_scenario_paths`,
`cached_view_cone_band`, `_cone_preset_key`, the applicability audit, the
canonical Fast/Slow source data and the evidence all remain. One constant
restores the feature:

```python
# model_dashboard/revenue_outlook_presentation_policy.py
REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = False
```

**Hiding prevents runtime work.** `cached_revenue_outlook_view` no longer calls
`cached_view_cone_band` at all, which removes two full scenario-overlay passes
(one per preset) from every view build. `tests/test_revenue_outlook_ui_slim_2050.py`
monkeypatches all four entry points to raise and requires the default page —
including one carrying a stale VFM layer selection — to render cleanly.

`tests/test_revenue_outlook_vfm_envelope.py` and
`tests/test_revenue_chart_layers.py` now run with the gate deliberately held
open, so the retained backend and the restore path stay covered.

Current Base is unaffected: it still composes from the exact VFM202405 Base
shares (`uptake_basis = "MoT VFM base"`, `share_source = exact_vendored_vfm_table`).

## 3. Presentation horizon capped at FY2050

```python
REVENUE_OUTLOOK_DISPLAY_END_FY = 2050
```

Applied at `_filter_series_rows_with_fallback` — the single gate every
decision-facing row passes through (the Total path view, the VFM bounds and the
A/B paths all call it), so annual and quarterly are filtered by the same rule
and cannot disagree. Also applied to the FY marker options, the uncertainty band
rows and, defensively, the Total path figure builder.

The terminal quarterly period is derived, not guessed:
`fiscal_quarters_of_june_year(2050)[-1]` → `2050Q2`, from the project's
June-ended fiscal-year convention.

FY2051–FY2055 remain in the governed source packs as audit material; a test
asserts the pack still carries them, and another asserts FY2050's own values are
byte-identical after clipping.

## 4. Expanded-chart focus mode

An in-app "Expand chart" toggle at the top right of the Total path chart. No
browser fullscreen, no permission prompt, no new third-party component — a
keyed container plus CSS.

Measured at both workshop resolutions:

| Viewport | Collapsed chart | Expanded chart | Share of viewport | Card grows with it | Horizontal overflow |
|---|---|---|---|---|---|
| 1920×1080 | 316 px | 864 px | 80% | 939 px ✓ | none |
| 1440×900 | 316 px | 720 px | 80% | 795 px ✓ | none |

The card growing matters: the first implementation enlarged the Plotly SVG
while Streamlit's element container kept its old flex-basis, so the taller chart
was clipped rather than shown. Both the wrapper chain and the flex-basis are now
released.

### Does zoom survive? Measured, not assumed

`layout.uirevision` and `layout.selectionrevision` are derived from the figure's
*calculation* identity (the same values that key its cache) and deliberately not
from the expand/collapse state.

With that in place, a zoom set before expanding was still in force afterwards in
**4 of 4 trials**, including the first expand after a fresh page load, with the
element key and the uirevision unchanged. One reset was observed on an
intermediate build, when the zoom was applied before the chart had finished
settling; it did not reproduce on the final build.

`tests/test_playwright_revenue_outlook_expand.py::test_expanding_preserves_a_reader_zoom`
holds this.

## Performance

Fresh interpreter, `REVENUE_OUTLOOK_RUNTIME_MODE=fast`, ar1 engine, production
default key (`uptake_basis = "MoT VFM base"`, deferred 12c policy).

| Measurement | VFM layers on (before) | VFM layers off (after) |
|---|---|---|
| Revenue Outlook view, cold | 9 122 ms | **5 660 ms** |
| Cone band rows built | 26 | 0 |
| Revenue Outlook view, warm (median of 20) | — | **12.1 ms** |

Hiding the analyst layers removes **3 462 ms** from the cold view. That is a
conservative floor: the "before" measurement ran with the shared upstream stages
already warm, so a genuinely cold process saves more. Each preset overlay pass
costs ~4.9 s on its own (`cached_scenario_overlay_rows` with a production key),
and the band ran two of them.

The repo's own benchmark on the no-lever key is unchanged at 6.3 s cold /
12.4 ms warm, as expected — that key never built a cone band.

Browser-visible interaction timings (1920×1080, click to app idle):

| Interaction | Time |
|---|---|
| No-op rerun (re-click the selected View option) | 663 ms |
| Expand chart on / off | 667–717 ms |
| Layer visibility change (remove a band chip) | 985 ms |

**The 500 ms acceptance target is not met by any display-only interaction on
this page, and that is pre-existing.** A no-op rerun that touches none of this
work already costs 663 ms — Streamlit re-executes the whole page script per
interaction. The expand toggle costs essentially the same as that floor
(+4 to +54 ms), so the focus mode adds no measurable cost; it does not reach
500 ms because nothing on this page does. Server-side the warm view is 12.1 ms,
so the gap is Streamlit's rerun and re-render, not the model.

## Validation

- `compileall` over `app.py`, `model_dashboard/`, `scripts/`, `tests/` — clean
- `tests/test_revenue_outlook_ui_slim_2050.py` — 35 passed
- `tests/test_revenue_chart_layers.py` + `tests/test_revenue_outlook_vfm_envelope.py` — 57 passed (gate held open)
- `tests/test_playwright_revenue_outlook_expand.py` — 7 passed
- Zero page-originated browser console errors across the whole session

## Screenshots

`screenshots/`

| File | What it shows |
|---|---|
| `01-default-total-nltf-1920.png` | Default Total NLTF: no retention control, no VFM options, both bands, Expand toggle off |
| `03-expanded-total-nltf-1920.png` | Expanded Total NLTF at 80vh, full 2001–2050 axis |
| `04-expanded-after-zoom-1920.png` | Expanded chart after a zoom operation |
| `05-expanded-1440x900.png` | Expanded at 1440×900, no overflow |
| `06-light-petrol-vkt-1920.png` | Light petrol VKT |
| `07-light-ruc-revenue-1920.png` | Light RUC revenue, running to FY2050 |

## Out of scope, deliberately left alone

- The EV **uptake basis** selector still offers "MoT VFM fast"/"MoT VFM slow" as
  whole-scenario composition choices. That is a scenario input, not a chart
  layer, and section 2 of the brief requires the exact VFM202405 class
  allocation to be preserved. Only the chart *layers* were withdrawn.
- The R2 ladder artifact mutation and the stale legacy e2e contract are not
  touched here.
