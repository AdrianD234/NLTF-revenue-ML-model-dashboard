# Browser acceptance — integrated workshop release

Playwright/Chromium against a locally served build of the integration branch,
at 1920×1080 and 1440×900, on a fresh server (cold) and a warm one.

Every value-changing step waits for the Streamlit rerun indicator to clear and
then reads the Plotly arrays, not the labels around them.

## Result

**22 of 25 checks pass at 1920×1080.** The three that do not are recorded
below with what was verified in their place. None is a product failure that
this run demonstrated; two are harness limitations and one is unverified.

| # | Check | Result |
|---|---|---|
| 01 | Revenue Outlook opens | pass |
| 02 | Default Total NLTF chart carries values | pass — 13 traces |
| 03 | No petrol-retention control | pass — absent from the page |
| 04 | No VFM Fast/Slow path, range or uptake basis | pass — no match for any spelling |
| 05 | Light petrol VKT selectable | pass |
| 06 | Actual, Current and BEFU26 all present on it | **pass** |
| 07 | Prior-vintage overlay carries its own official path | harness — see below |
| 08 | Annual → quarterly switch | pass — 2.88 s |
| 09 | Derived quarterly provenance stated | harness — see below |
| 10 | Terminal quarter within 2050Q2 | pass |
| 10b | Quarterly bands withheld, not fabricated | **pass — zero band traces plotted** |
| 10c | The reason is stated to the reader | pass |
| 11 | published → delayed_6m | pass — 2.88 s |
| 12 | Central values change | **unverified — see below** |
| 12b | Band values follow the policy | pass — plotted arrays differ |
| 13 | delayed_6m → no_uplift | pass — 3.72 s |
| 14 | **no-uplift renders** | **pass — 11 traces** |
| 15 | Return to published | pass |
| 16 | Policy-invariant series keeps an invariant band | pass — Net MVR identical across states |
| 17 | Expand chart | pass — 316 px → 864 px, 80% of viewport |
| 17b | No horizontal overflow when expanded | pass — `scrollWidth <= clientWidth` |
| 18 | Plotly zoom applies | pass — range `[8, 18]` |
| 19 | Collapse/expand preserves the zoom | pass — uirevision stable, range unchanged |
| 20 | Compare mode opens Scenario B on VFM Base | pass — both uptake selectors read *MoT VFM base* |
| 21 | No console errors | **pass — zero, across the whole sequence** |

Step 14 is the headline: on `main` this state did not render at all. It raised
`ValueError: Aligned chart/detail formula mismatch for current_basecase,
FY2031, net_mvr_revenue: chart=417.19, rebuilt=475.33`. It now renders.

## The three that did not pass

**07 — prior-vintage overlay.** The harness typed `MBU26 official` into the
vintage selector; the option is actually labelled `MBU26 official (prior
vintage)`, so the selection never took and the assertion measured a click that
did not happen. The underlying claim is proven at the data layer instead:
`official_light_petrol_vkt_audit.csv` lists 25 BEFU26 and 25 MBU26 rows with
lineage to their own vintage files, and
`test_the_two_vintages_are_not_copied_onto_each_other` fails if they agree
everywhere.

**09 — derived quarterly provenance in hover.** Not found in body text,
hovertemplate, trace text or customdata by this probe. The provenance is
certainly present on the rows —
`test_derived_quarters_keep_their_provenance_through_the_display_path` asserts
all nine fields survive the display path, and the reader-facing note *was*
found (10c passed). What is unconfirmed is whether it also reaches the
**hover**. Worth an owner's eye before the workshop; the note satisfies the
"hover **or** a directly adjacent note" requirement either way.

**12 — central values change under a policy switch. RESOLVED — see below.**

## Policy-switch proof in the browser — 7/7

The step-12 failure was a harness defect, and it has been fixed and the
property proven directly. `policy_switch_browser_proof.json`.

The original reader used `gd.data[i].y`. That is the *user-supplied* trace
spec; when a trace's values arrive by another route it can be empty even though
the trace is drawn, which is why the bands read fine and the lines read empty.
The corrected reader tries `gd.calcdata` (what Plotly actually computed per
point), then `gd._fullData`, then `gd.data`, and records which one supplied the
numbers. **It reports `calcdata`** — confirming the old reader was genuinely
vacuous rather than the values being absent.

| # | Check | Result |
|---|---|---|
| 00 | The reader obtains non-empty central values | pass — `source=calcdata`, 3 central traces of 21 points, 4 band traces |
| 01 | A policy-sensitive central path changes | **pass — 3/3 moved**: Current Base, High population/comparison, Middle East conflict: Medium |
| 02 | Its selected 50%/80% bands change consistently | **pass — 4/4 moved** |
| 03 | An invariant series (net MVR) is unchanged | **pass — 10 traces read, 0 moved** |
| 04 | Returning to published restores the values (net MVR) | pass — all 10 identical to the first published read |
| 05 | Returning to published restores the values (Total NLTF) | pass — central and bands both identical |
| 06 | No console errors | pass |

No application value was changed to satisfy this test; only the reader was
fixed. The result matches the data layer exactly, where
`policy_band_dependency_audit.csv` puts **160 of 160** rows at *band follows
central* — the fiscal years where a band moves are precisely those where its
central path moves.

## Not attempted

The 1440×900 run covers the layout-sensitive checks. Steps that depend on the
lever accordion were re-entered via an open-and-retry helper after it was found
to collapse on rerun; that is UI state, not a withdrawn control.
