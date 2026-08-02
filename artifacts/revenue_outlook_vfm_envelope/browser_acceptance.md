# Browser acceptance — Integrated VFM Scenario Envelope

Driven with Playwright against a live Streamlit server on the branch build.
Every figure below was read from the rendered chart's `_fullData` (the decoded
Plotly arrays actually plotted), not from a caption, a spinner or a snapshot of
the page text. The engine in the browser is the app default, **AR(1)**, with
the app default Current 12c policy, **Deferred 6 months — 1 Jul 2027** — which
is why the levels differ from the ensemble-engine numbers in
`applicability_audit.csv` while the Fast/Slow gaps are identical.

Screenshots: `screenshots/`.

## Numeric verification

### Total NLTF revenue — 1920x1080

| check | plotted | independent recompute | match |
|---|---|---|---|
| band span | FY2025–FY2030 (6 points) | FY2025–FY2030 | yes |
| upper, FY2030 | 6.422641844708518 ($b) | 6422.641844708518 ($m) | to 9e-13 |
| lower, FY2030 | 6.391134834034494 ($b) | 6391.134834034494 ($m) | to 9e-13 |
| band width, FY2030 | 31.507011 ($m) | 31.507011 | yes |
| Current Base, FY2030 | 6.408493240540763 ($b) | — | strictly inside the band |
| FY2030 anchor / post-model seam | econometric last = 6.408493240540763; post-model first (FY2030) = 6.408493240540763 | — | continuous, no jump |
| chart runs to | FY2050 (post-model FY2050 = 12.997261591337160 $b) | — | band correctly stops at FY2030 |
| legend | exactly one VFM entry, `MoT VFM fast–slow range` | — | yes |
| boundary traces | 2, both `dash: dot`, `mode: lines` (no markers) | — | yes |
| draw order | band at trace indices 0,1; first line trace at index 2 | — | band behind every line |
| chart width | 1836 px of a 1920 px viewport | — | full width |
| horizontal overflow | `document.body.scrollWidth` 1920 = viewport | — | none |

All six FY2025–FY2030 lower and upper values were compared against an
independent exact-Fast/Slow min/max recomputation; maximum absolute difference
**9.09e-13** on both bounds.

### Light RUC revenue — 1920x1080 and 1440x900

| FY | lower ($b) | upper ($b) |
|---|---|---|
| FY2025 | 0.8120864140613921 | 0.8258263836615536 |
| FY2026 | 0.8556829132801796 | 0.8825315244160641 |
| FY2027 | 0.8510812116459697 | 0.8959290455153185 |
| FY2028 | 1.0653208639477072 | 1.1488666114393960 |
| FY2029 | 1.1625446108480944 | 1.2857407390758484 |
| FY2030 | 1.2334473490338850 | 1.4008833900453650 |

FY2030 width 167.436041 ($m) — identical to the audited value, and identical at
both viewport widths. At 1440x900 the chart is 1366 px of 1440, with no
horizontal overflow.

This is the series where the envelope is clearly legible: the Fast/Slow gap
reaches 12.71% of level.

### PED volume and Net FED revenue — 1920x1080

Both correctly render **no** band, with the caption:

> No MoT VFM Fast–Slow range for this series. The MoT VFM Fast and Slow
> compositions produce the same values for this series under the selected
> controls, so no range is drawn. Width is never fabricated for visual
> consistency.

## Selector behaviour

| interaction | result |
|---|---|
| official comparator BEFU26 → MBU26 | `MBU26 official` plotted; band values **byte-identical** (all 6 upper and 6 lower to < 1e-12) |
| MBU26 → BEFU26 | comparator restored, band unchanged |
| Series → PED volume → Net FED → Light RUC → Total NLTF | plotted band values changed on each step and returned **identical** to the first render |
| stale-chart check | the assertion is on plotted band arrays, not on a caption; a mid-rerun poll was observed still holding the previous series' values and was re-polled until the plotted values changed |

## Presentation contract

| check | result |
|---|---|
| `Uncertainty fan` card on the default page | absent |
| `Fan source details` (the fan figure's own control) on the default page | absent — the fan figure is not constructed |
| `Show forecast-uncertainty fan detail` gate | present, defaults off |
| `Show MoT VFM Fast–Slow range audit` gate | present, defaults off |
| after opening the fan gate | fan card, `Fan source details`, the 50%/80% empirical traces, the numeric table and `Download fan band rows (CSV)` all render; the "stops at FY2030" wording is on the page |
| non-probabilistic wording under the chart | present in full |

## Console

**Zero** console errors and zero warnings on the page under test.

(Six `ERR_CONNECTION_REFUSED` entries exist in the all-session log; they are
from the deliberate server restart between the styling change and the final
capture, not from the page under test. A same-navigation query returns 0.)

## Styling note

The envelope fill was raised from `rgba(0,111,173,0.10)` to `0.16` and the
dotted boundaries from `rgba(0,111,173,0.28)` / width 0.8 to `0.55` / width 1.2.
At the original values the boundaries were sub-pixel on an 1836 px plot and the
envelope was invisible even on Light RUC. Both values are single constants —
`VFM_ENVELOPE_FILL_COLOR` and `VFM_ENVELOPE_BOUNDARY_LINE` — so this is a
one-line revert if the owner prefers the original weight.

**Even at the raised opacity, the envelope is not visually apparent on Total
NLTF revenue.** That is a property of the data, not the rendering: the widest
Fast/Slow gap on that series is 0.48% of level against a y-axis spanning
$0–$15b. The screenshot is included precisely so the owner can see that.
