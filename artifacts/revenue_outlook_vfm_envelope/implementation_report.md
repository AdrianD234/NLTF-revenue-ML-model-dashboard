# Integrated VFM Scenario Envelope

Restores the governed MoT VFM Fast–Slow range onto the main Revenue Outlook
Total path chart, takes that chart to full page width, and removes the
separately rendered uncertainty-fan card from the default layout.

Branch: `ui/revenue-outlook-integrated-vfm-envelope`
Base: `28ee2e3` (main, after PR #11, #12 and #13)

Bounded presentation and runtime-wiring change. No model, forecast, scenario,
policy, official-vintage value, long-run shape method or formula was changed.

---

## 1. The exact cause of the missing integrated band

The cone pipeline was never disconnected. It was **out-scaled by the long-run
horizon**, and the diagnosis has three separate parts.

### 1a. The band was still being drawn — at zero width for 20 of its 26 years

`cached_view_cone_band` → `cached_revenue_outlook_view["cone_band"]` →
`cached_revenue_outlook_total_path_figure` → `revenue_outlook_total_path_figure`
was intact end to end on `main`. Both dotted boundary traces and the filled
`MoT VFM fast–slow range` legend entry were present in every rendered figure.

What changed underneath it was the x-axis. Measured on `main` at `28ee2e3`,
Total NLTF revenue, default controls:

| FY | lower | upper | width | width % of level |
|----|-------|-------|-------|------------------|
| FY2025 | 4277.83 | 4280.14 | 2.30 | 0.054% |
| FY2027 | 5016.90 | 5026.92 | 10.03 | 0.200% |
| FY2030 | 6497.90 | 6529.41 | 31.51 | 0.484% |
| FY2031 | 6848.33 | 6848.33 | **0.00** | **0.000%** |
| … | | | **0.00** | **0.000%** |
| FY2050 | 13043.46 | 13043.46 | **0.00** | **0.000%** |

The VFM composition overlay reaches **FY2025–FY2030 only**. Verified directly:
diffing every june-year row between an exact `MoT VFM fast` run and an exact
`MoT VFM slow` run moves 320 rows, and every one of them falls in FY2025–FY2030.
The FY2031–FY2050 `forecast_segment = post_model_extrapolation` layer (680 rows
in the committed pack) is **composition-invariant by construction** — it is
anchored and shaped independently of the VFM scenario, so Fast and Slow produce
byte-identical values there.

So the band covered 6 of the 26 plotted forecast years and was drawn as a flat
zero-width line across the other 20.

### 1b. Which commit caused it

Not the anchored-shape promotion, and not a selector, cache-key or filter
regression. The ordering:

- `690a5dd` (2026-07-08) introduced the cone. At that commit the Total path
  chart **ended at FY2030**, so the band spanned the entire forecast horizon —
  which is what the historical screenshots show.
- `55d76a8` (2026-07-30) restored the Revenue Outlook long run and extended the
  chart to FY2050 with the composition-invariant post-model layer.
- `96237a7` / `1f44da0` (PR #12) later swapped which long-run construction that
  layer uses. That changed the *shape* of the invariant tail, not its
  invariance, so PR #12 is not the cause.

`55d76a8` is the commit that turned a full-horizon envelope into a 6-year one.

### 1c. Why the remaining 6 years read as "no band"

Two compounding factors:

- **Intrinsic width.** On the default series, Total NLTF revenue, the widest
  Fast/Slow gap is 0.484% of level at FY2030. Against a y-axis spanning roughly
  $4.3b–$13.0b that is about 0.35% of plot height — on the order of one or two
  pixels.
- **Layout.** The chart sat in a `st.columns([0.64, 0.36])` split next to the
  uncertainty-fan card, so those pixels were compressed into 64% of the page.

### Honest summary

The wiring was not broken. The band is genuinely narrow on the default series
and genuinely undefined past FY2030. The fix is real but it is a fix to
*presentation and applicability*, not a repair of a severed pipeline. See §9 for
the two consequences an owner has to accept.

---

## 2. Restored, not replaced

The existing governed cone code was **restored and corrected in place**. No
second cone builder exists.

`cached_view_cone_band` keeps its name, its position in the view pipeline, its
`Current finalist Base case` bound selection and its min/max semantics. Two
defects in it were fixed:

**(i) The band was not inheriting the live controls.** It rebuilt a 5-slot
preset key:

```python
preset_key = (preset_name, (), tuple(eruc_values),
              _normalise_fed_policy_state(current_fed_policy_state),
              FED_POLICY_PUBLISHED)
```

The production key has **ten** slots. Slots 5–9 — the PED retention
sensitivity, the official comparator vintage, the overlay flag, the long-run
transition schedule and the long-run shape vintage — were silently dropped, so
the envelope was computed under a differently-configured run than the line it
wrapped. It now carries the live key through verbatim and swaps only slot 0:

```python
def _cone_preset_key(preset_name, band_controls):
    return (preset_name, *band_controls)   # band_controls is ev_uptake_key[1:]
```

Only the VFM Fast/Slow composition assumption varies. Nothing else can.

**(ii) The zero-width tail is now cut.** `_clip_cone_band_to_supported_periods`
keeps the contiguous span the composition actually moves and drops leading and
trailing composition-invariant runs. Interior periods are retained so the fill
stays one continuous shape. A series the VFM assumption never moves returns
empty — width is never fabricated.

---

## 3. Why the band is non-probabilistic

It is the pair of governed MoT VFM fleet-composition scenarios — Fast and Slow —
run through the same engine, vintages, schedule, policy and macro settings as
the Current path. It says what the composition assumption is worth. It says
nothing about how likely any value is.

It is **not** a confidence interval, a credible interval, a prediction interval
or any probabilistic statement, and `VFM_ENVELOPE_NOT_PROBABILISTIC_NOTE` says
so verbatim in the chart note, the caption under the chart and the audit
surface. `test_the_vfm_envelope_is_never_described_as_probabilistic` blocks any
interval word appearing outside the sentence that denies it.

Three distinct concepts remain separate:

| | source | horizon | probabilistic |
|---|---|---|---|
| Blue VFM range | governed VFM Fast/Slow composition scenarios | FY2025–FY2030 | no |
| Grey 50%/80% fan | empirical forecast error | to FY2030 | yes, within its support |
| Post-FY2030 long-run spread | scenario envelope | FY2031–FY2050 | no |

The grey fan is **not** drawn on top of the blue envelope. Combining the two
visual languages needs a separate owner decision and was not taken here.

---

## 4. Which controls enter the band's calculation

Carried through verbatim from the live key (any change recomputes the band):

- sensitivity key — fleet efficiency, PT mode shift, freight rail shift,
  elasticities, cost-per-km ratio;
- PED bridge mode;
- e-RUC transition levers (slot 2);
- Current 12c policy state (slot 3);
- official-comparator policy state (slot 4);
- PED retention sensitivity (slot 5);
- official comparator vintage and overlay flag (slots 6/7);
- long-run transition schedule and shape vintage (slots 8/9);
- the pack signature, hence the engine.

**Deliberately excluded:** the displayed VFM basis (slot 0). The envelope always
evaluates Fast and Slow, so it is basis-invariant by construction and switching
Base/Fast/Slow reuses the cached band. Proven in
`test_value_changing_controls_invalidate_the_band`.

The cache key is the compact `ev_uptake_key[1:]` tuple. No DataFrame is hashed
to identify the band.

Measured (`control_sensitivity.csv`):

| control change | band identical | correct? |
|---|---|---|
| displayed VFM basis = Fast / Slow | yes | yes — basis-invariant by design |
| official comparator = MBU26 | yes | yes — display-only |
| official comparator overlay on | yes | yes — display-only |
| long-run schedule = unblended | yes | yes — see §9b |
| Current 12c policy = no uplift | **no** | yes — value-changing |
| PED retention sensitivity on | **no** | yes — value-changing |
| back to the original controls | yes | yes — no stale band |

---

## 5. Which series get a band, and which do not

From `applicability_audit.csv`, default controls, both engines:

| series | band | span | max width % of level |
|---|---|---|---|
| Total NLTF revenue | yes | FY2025–FY2030 | 0.48% (ensemble) / 0.49% (ar1) |
| Total RUC+PED revenue | yes | FY2025–FY2030 | 0.52% / 0.53% |
| Total RUC all classes | yes | FY2025–FY2030 | 0.97% |
| Light RUC revenue | yes | FY2025–FY2030 | 12.71% |
| Light RUC net km | yes | FY2025–FY2030 | 12.71% |
| Heavy RUC revenue | yes | FY2026–FY2030 | 1.05% |
| Net FED revenue | **no** | — | composition-invariant while PED retention is off |
| PED volume | **no** | — | as above |
| PED revenue | **no** | — | as above |
| Net MVR revenue | **no** | — | never composition-dependent |

The PED-family absences are correct, not a gap: with the PED retention
sensitivity **off** (the default), the VFM composition does not move
light-petrol VKT, PED litres or FED revenue at all. Switching that sensitivity
**on** gives every one of them a band — Net FED revenue 5.01%, PED volume 4.89%,
Total NLTF revenue 2.54% — which is the direct evidence that the absence is a
property of the selected controls and not of the wiring.

---

## 6. Independent verification of the band values

`band_values.csv` recomputes, for every displayed row and both engines:

```
lower = min(exact VFM Fast result, exact VFM Slow result)
upper = max(exact VFM Fast result, exact VFM Slow result)
```

directly from the exact VFM overlay rows, filtered independently of the band
constructor, with all non-VFM controls held fixed. Every row matches to
< 1e-9 absolute, and the builder asserts it. `upper >= lower` holds on every row.

The blocking tests recompute the same way rather than deriving the expectation
from the constructor under test, and assert the parity join is non-vacuous
(row counts equal and non-zero) so no check can pass on an empty selection.

---

## 7. Before/after page timing

Measured cold (`page_timings.csv`, ensemble engine, Total NLTF revenue):

| stage | ms |
|---|---|
| selector metadata (pack load + signature) | 336.3 |
| view construction (cold) | 10 335.97 |
| VFM band construction | 50.28 |
| main Total path figure | 107.52 |
| separate fan figure — **before** | 23.59 |
| separate fan figure — **after** | **0.00** (not constructed) |

**Stated plainly: this is not a performance fix.** The separate fan figure cost
about 24 ms. Removing it is worth 24 ms of compute plus one avoided figure
serialisation and one fewer Plotly mount in the browser. The ~103 s cold start
is dominated by view construction, and this PR does not address it — that is
the compiled-scenario performance workstream. What this PR guarantees is that
the page is **not slower** and no longer eagerly pays the fan cost. No AppTest
timeout was raised.

---

## 8. Confirmations

- **No forecast value moved.** `test_the_band_is_display_only_and_moves_no_chart_value`
  builds the figure with and without the band and asserts every plotted line
  point is identical. The band is a separate frame consumed only by the figure.
- **Published vintages unchanged.** BEFU26 and MBU26 rows are compared against
  the committed `revenue_chart_rows.csv`.
- **Fan source data remains available.** `fan_band_rows`, `fan_availability`,
  the 50/80 values, the empirical-support cutoffs, the FY2030 empirical rule and
  the non-probabilistic labelling of long-run rows are all unchanged and
  asserted. The fan figure, its source selector, the numeric 50/80 table and a
  CSV download all live behind the "Show forecast-uncertainty fan detail"
  toggle. The toggle defaults to off, so the figure is never constructed or
  serialised on the default render — asserted structurally
  (`test_the_fan_figure_is_only_built_behind_the_request_gate`) and in the
  browser (the fan's own strings must be absent from the default page text).

---

## 8a. Browser acceptance

Full detail in `browser_acceptance.md`; screenshots in `screenshots/`.

Driven with Playwright against a live server on the branch build, reading the
rendered chart's decoded Plotly arrays rather than any caption. Headlines:

- Total NLTF revenue, FY2030: plotted upper `6.422641844708518` $b and lower
  `6.391134834034494` $b match an independent exact Fast/Slow recomputation to
  **9.09e-13**; the Current Base point `6.408493240540763` sits strictly inside.
- The FY2030 anchor and the post-model seam are continuous: the econometric
  segment's last point and the post-model segment's first point are the same
  number.
- Light RUC revenue FY2030 width `167.436041` $m — identical at 1920x1080 and
  1440x900, and identical to the audited value.
- PED volume and Net FED revenue render **no** band and show the governed
  absence caption.
- Changing the official comparator BEFU26 → MBU26 leaves all twelve band values
  byte-identical; cycling through four series and back returns the original band.
- Chart width 1836 px of 1920, and 1366 px of 1440. No horizontal overflow at
  either width.
- The default page contains neither `Uncertainty fan` nor `Fan source details`,
  so the fan figure is genuinely not constructed. Opening the gate renders the
  fan, the 50%/80% traces, the numeric table and the CSV download.
- **Zero** console errors.

### Styling

The envelope fill was raised from `rgba(0,111,173,0.10)` to `0.16` and the
dotted boundaries from `rgba(0,111,173,0.28)` / width 0.8 to `0.55` / width 1.2.
At the original weights the boundaries were sub-pixel on an 1836 px plot and the
envelope was invisible even on Light RUC. Both are single constants —
`VFM_ENVELOPE_FILL_COLOR`, `VFM_ENVELOPE_BOUNDARY_LINE` — so this is a one-line
revert. Flagged as a judgement call because the reference screenshots were not
available to match against directly.

---

## 9. Two things the owner has to decide

### 9a. The envelope stops at FY2030 — it is not carried to FY2050

The brief asked for a band that stays visually continuous across the
FY2030/FY2031 seam. **That is not deliverable without changing the model.** The
post-model layer is composition-invariant, so past FY2030 there is no Fast/Slow
range to draw. The options were:

1. draw zero width to FY2050 — reads as certainty about the long run, and is
   what `main` was doing;
2. taper the band to a point at FY2031 — implies the range genuinely closes;
3. **truncate at FY2030** and say why.

Option 3 was implemented: the range is undefined past FY2030, not zero. This is
flagged rather than changed silently, per the brief's instruction to report a
discrepancy before altering economic meaning. Making the long-run tail
composition-dependent is a model change and belongs in its own PR.

### 9b. "Changing the long-run schedule invalidates the band" is only half true

The schedule now genuinely enters the band's cache identity, and
`test_the_selected_long_run_schedule_enters_the_band_identity` proves slots 8/9
reach the constructor. But the band **values** are identical across schedules —
correctly, because the schedule only reshapes FY2031–FY2050, exactly the window
the envelope is clipped away from. The test asserts the reachable, non-vacuous
fact rather than a value change that would be wrong to expect.

---

## 10. Separate defect found and NOT fixed here

`ev_uptake_key` slot 6 is read by two different helpers:

- `_official_vintage_scope` (app.py:999) reads it as the official comparator
  vintage id, a string such as `"BEFU26"`;
- `_heavy_bev_transition_enabled` (app.py:829) reads it as a boolean Heavy BEV
  transition flag, documented as "Off by default".

The production key always carries a non-empty vintage id in that slot, so
`_heavy_bev_transition_enabled` returns `True` on **every** real render and
Heavy BEV reclassification is silently on, against the settled
`HEAVY_RUC: not_reclassified` contract. Measured:

```
heavy_ruc_net_km, basecase, FY2030
  slot 6 = "BEFU26"  ->  4191.862234058749
  slot 6 = ""        ->  4230.412228687553      (0.91% apart)
```

`tests/test_canonical_base_composition.py::_key` does not catch it because it
builds a 7-slot key with the heavy flag in slot 6 and no vintage id — a key
shape production never produces.

Fixing it moves published Heavy RUC and Total NLTF values, which this PR is
explicitly forbidden to do. It is filed as separate work and needs its own
baseline re-freeze and an owner decision.

---

## 11. Files

| file | change |
|---|---|
| `app.py` | band inherits the live key; degenerate-tail clip; applicability audit; full-width chart; fan behind a request gate; fan detail table + CSV; envelope caption and audit surface |
| `tests/test_revenue_outlook_vfm_envelope.py` | new — 37 blocking tests |
| `tests/test_revenue_outlook_long_run.py` | fan pin rewritten to "governed but not eagerly rendered"; legend-label and non-probabilistic assertions |
| `tests/test_streamlit_smoke.py` | primary-layout and cloud-toggle pins updated |
| `tests/test_playwright_dashboard.py` | above-the-fold and page-text expectations updated |
| `scripts/build_revenue_outlook_vfm_envelope_evidence.py` | new — rebuilds every CSV below |
| `.gitignore` | one exception pair for the new artifacts directory, following the existing convention |
| `artifacts/revenue_outlook_vfm_envelope/*` | applicability, parity, control sensitivity, timings, browser acceptance, screenshots, this report |

### Third-place note on the visual result

The envelope is legible on Light RUC revenue and Light RUC net km (12.71% of
level) and, at a squint, on Total RUC all classes (0.97%). On the **default**
series, Total NLTF revenue, it is 0.48% of level against a $0–$15b axis and
remains effectively invisible even after the opacity bump. That is what the
data says; it is not a rendering fault, and no width was invented to make the
chart look like the reference. The Total NLTF screenshot is included precisely
so the owner can judge whether a decision-facing default that shows a
technically-present but unreadable band is the right presentation, or whether
the default series or the y-axis policy should change — both of which are
outside this PR.
