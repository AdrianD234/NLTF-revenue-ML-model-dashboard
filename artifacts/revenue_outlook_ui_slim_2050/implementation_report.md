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

## 2a. The uptake basis is paused with its layers

Hiding the chart layers while leaving VFM Fast and VFM Slow selectable in the
**EV uptake-basis** control left the whole-scenario composition reachable: a
reader could still run Fast or Slow through the entire engine, they just could
not see the dedicated lines. The pause therefore covers the basis selector too.

Public uptake options are now:

```
MoT VFM base
Custom levers
Parametric approximation to VFM Base (audit sensitivity)
```

The pause is deliberately narrow. The parametric approximation to VFM **Base**
also mentions VFM and survives, as do the custom levers and every official
comparator label; only the Fast/Slow pair is withdrawn.

Three surfaces were carrying it:

| Surface | Before | After |
|---|---|---|
| Single-view "Uptake basis" | full `EV_UPTAKE_MODE_OPTIONS` | `_public_uptake_basis_options()` |
| Compare-view "Uptake basis" (A and B) | full options minus Custom | gated options minus Custom |
| Compare **Scenario B default** | **`"MoT VFM fast"`** | `MoT VFM base` |

That third one mattered most: Scenario B *opened* on VFM Fast, so simply
switching to Compare A vs B ran a paused composition without the reader
choosing anything.

Stale session state is reset rather than dropped, on three keys
(`revenue_outlook_ev_uptake_basis_v2`, `ro_cmp_a_uptake`, `ro_cmp_b_uptake`):
these selectors must always resolve to a legal composition, and Base is the
governed default. The two remaining reads of the page's basis are sanitised at
the point of use as well, so the guarantee does not depend on entry-time
cleanup alone.

### Proofs

| Requirement | Test |
|---|---|
| Fast/Slow absent from single-view controls | `test_the_single_view_uptake_selector_offers_no_paused_basis` |
| Fast/Slow absent from compare-view controls, and B opens on Base | `test_compare_mode_offers_no_paused_basis_and_opens_on_base` |
| Stale session values reset to VFM Base | `test_a_stale_paused_basis_is_reset_to_vfm_base` (per key) and `test_a_stale_paused_basis_does_not_survive_a_real_render` |
| No Fast/Slow scenario-overlay calculation runs | `test_no_fast_or_slow_overlay_is_computed_on_a_production_render` — every overlay pass carrying a paused basis raises, and a default render seeded with a stale Fast selection must still complete |
| Current Base byte-identical | `test_current_base_is_unmoved_by_the_uptake_gate` — the Current Base series computed with the gate closed and open is compared with `assert_series_equal` |
| Retained backend still passes with the gate enabled | `test_the_fast_slow_backend_still_works_when_the_gate_is_open` plus the three suites that run gate-open |

### One thing deliberately left alone

The **Fleet Mix Explorer's "Source" selector** still lists
`VFM 202405 - Fast scenario` and `- Slow scenario`. Those are MoT's published
vendored extract shown side by side with the dashboard path — reference
material, not a composition the engine runs: `fleet_mix.load_dashboard_frame`
always builds its dashboard column with `EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]`.
Withdrawing them would drop published source material the pause was never
about. `test_the_fleet_mix_vfm_reference_is_display_only` pins that distinction
so it cannot drift into an engine path unnoticed.

### Verified in the browser

Uptake-basis dropdown lists exactly the three options above; both compare-mode
selectors open on `MoT VFM base`; no `MoT VFM fast`/`slow` text anywhere on the
page in either view mode; zero console errors.

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
- The six suites this change touches, run together — **238 passed**
  (`test_revenue_outlook_ui_slim_2050`, `test_revenue_chart_layers`,
  `test_revenue_outlook_vfm_envelope`, `test_vfm_long_run_composition`,
  `test_view_performance_caches`, `test_streamlit_smoke`)
- `tests/test_playwright_revenue_outlook_expand.py` — 7 passed
- Zero page-originated browser console errors across the whole session
- Streamlit deploy readiness PASS; extract validation 21/21; replay-seed
  diagnostic PASS; replay parity fingerprint written (both CI parity jobs green)

### Existing tests this change required updating, and why

| Test | Change |
|---|---|
| `test_streamlit_smoke::..._cloud_hides_debug_toggles...` | The toggle inventory changed by design: "Expand chart" added, "Show MoT VFM Fast–Slow range audit" withdrawn. |
| `test_streamlit_smoke::..._compare_mode_swaps_total_path...` | It asserts the chart card's title is absent while comparing. A CSS comment in `inject_theme` contained that title verbatim, and the injected `<style>` block is part of the rendered markdown — the comment was reworded rather than the assertion weakened. |
| `test_revenue_outlook_vfm_envelope`, `test_revenue_chart_layers`, `test_vfm_long_run_composition` (module-wide) and `test_view_performance_caches::test_cone_band_is_uptake_key_invariant` (one test) | These protect the retained Fast/Slow backend, which the pause deliberately stops running. They now opt in to the shared `vfm_analyst_layers_enabled` fixture in `tests/conftest.py`, so the restore path stays covered instead of being deleted. The fixture is module-scoped because several of these suites build their figure through a module-scoped fixture, and pytest sets higher-scoped fixtures up first. |

### On the full local suite

A full `pytest` run inside an isolated clean worktree reports ~35 additional
failures in `test_curated_data`, `test_schiff_purity`, `test_visual_artifacts`,
`test_recursive_audit_log`, `test_cone_landscape_validation`,
`test_ensemble_composition_validation` and `test_stress_horizon_validation`.
These read `artifacts/` files that are gitignored and therefore absent from a
fresh checkout; they are unrelated to this change. CI's clean-clone suite, which
provisions those inputs, failed only on the two smoke tests listed above — both
now fixed.

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

- The EV uptake-basis selector was withdrawn in a follow-up amendment; see
  section 2a. The Fleet Mix Explorer's published VFM 202405 reference columns
  are retained and explained there.
- The R2 ladder artifact mutation and the stale legacy e2e contract are not
  touched here.
