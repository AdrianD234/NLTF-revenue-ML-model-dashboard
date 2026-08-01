# Browser acceptance — layered scenarios and uncertainty

Playwright against a live server on the branch build. Every figure below was
read from the rendered chart's decoded Plotly arrays (`_fullData`), not from
page text, a caption or a spinner. Engine is the app default (AR(1)) with the
default Current 12c policy (Deferred 6 months).

Screenshots in `screenshots/`.

---

## 1. Default view — 1920×1080

`layered_default_total_nltf_desktop.png`

| check | result |
|---|---|
| chart width | 1836 px of 1920 (full width) |
| `Show on chart` control present | yes, one multiselect |
| default layers | 80% band, 50% band, Actual, BEFU26 official, Current Base, High population, conflict Medium, behavioural comparison |
| caption | "6 of 8 selected · 2 band layer(s)" |
| separate `Uncertainty fan` card | **absent** |
| legend | 7 entries, one per selected layer |

---

## 2. All layers — worst case

`layered_all_layers_total_nltf_desktop.png` (1920×1080),
`layered_all_layers_total_nltf_laptop.png` (1440×900)

Caption reads **"All 8 selected · 3 band layer(s)"**. Ten legend entries.

Trace order as rendered, confirming the governed z-order:

```
80% conditional band upper
80% conditional modelled uncertainty      <- outer band
MoT VFM fast bound
MoT VFM fast–slow range                   <- structural envelope
50% conditional band upper
50% conditional modelled uncertainty      <- inner band
Actual, BEFU26 official, Current Base, High population,
conflict Medium, MoT VFM Fast uptake, MoT VFM Slow uptake
```

### Total NLTF revenue, FY2030

| quantity | value |
|---|---|
| Current Base | 6.408493240540763 |
| MoT VFM Fast uptake | 6.391134834034494 |
| MoT VFM Slow uptake | 6.422641844708518 |
| 80% band | 5.767471109596391 → 6.593651018473789 |
| 50% band | 5.973105812390058 → 6.431544310861606 |

Base lies between the two VFM paths. The 50% band is nested inside the 80%.
The band is visibly asymmetric about the Current line, as the evidence
requires.

### FY2050 (inferred long run)

80% band 10.615092783145185 → 13.550588319848838, held on the FY2030
distribution under the plateau rule.

---

## 3. Light RUC revenue — the governed contract, rendered

`layered_all_layers_light_ruc_laptop.png`

| quantity | rendered | governed basis | match |
|---|---|---|---|
| 80% span at FY2030 | **32.1877%** | 32.19% | yes |
| lower distance | **26.0798%** | 26.08% | yes |
| upper distance | **6.1079%** | 6.11% | yes |
| FY2030 band | 0.967712 → 1.389091 $b | — | — |
| Current Base FY2030 | 1.309130 $b | — | inside the 80%, near the top |
| FY2050 band | 0.764088 → 1.096801 $b | plateau | — |

This is the wide Light RUC band the owner approved, uncapped and unnarrowed,
rendering exactly at its governed width. The 50% inner band is darker, the 80%
outer band lighter, so a reader controls how much uncertainty is visible.

---

## 4. Layout and errors

| check | 1920×1080 | 1440×900 |
|---|---|---|
| main chart width | 1836 px | 1366 px |
| horizontal overflow | none | none |
| all-layers legibility | legible | legible |
| console errors | **0** | **0** |

Three lazy audit toggles are present and default off: *Show
forecast-uncertainty fan detail*, *Show modelled-uncertainty audit*, *Show MoT
VFM Fast–Slow range audit*. None constructs anything until switched on.

---

## 5. Terminology on the page

- Bands are labelled **"conditional modelled uncertainty"**, never "confidence
  interval".
- The chart note states the rolling-origin evidence uses observed future
  drivers and therefore **excludes Treasury-driver forecast uncertainty**.
- The VFM range note states it is a **structural scenario range, not
  probabilistic**, and not a confidence, credible or prediction interval.
- The multiselect help text repeats all three distinctions at the point of
  choice.
