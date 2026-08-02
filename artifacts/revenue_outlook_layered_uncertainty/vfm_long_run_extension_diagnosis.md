# Why VFM Fast and Slow collapsed at FY2031

Pre-amendment head: `ac144a40d9eecf32c58533e6a916522fdb3abba5`

---

## 1. The cause

`apply_uptake_levers_to_chart_rows` in `model_dashboard/ev_uptake_levers.py`
derives the June years it will touch from the **rate lookup**, not from the
chart rows:

```python
rate_lookup = _drift_rate_lookup(drift_assumptions)
fys = sorted({fy for _, fy in rate_lookup})
```

`_drift_rate_lookup` reads `ev_phev_ped_light_drift_assumptions`, which is the
**econometric-window** rate table. Measured on the committed pack:

```
rate_lookup FY coverage: 2025 - 2030   (6 years)
scenarios: current_basecase, current_comparison_1
```

The allocation loop is `for (scenario, fy), rates in rate_lookup.items()`, so
**FY2031–FY2050 rows were never visited at all**. Every uptake basis therefore
left the post-model class values exactly as the pack wrote them, which is why
Fast and Slow were numerically identical from FY2031.

### What it was *not*

Three plausible explanations that the trace ruled out:

- **Not** a `post_model_extrapolation` segment filter. The overlay never tests
  `forecast_segment`; it simply never reaches those FYs.
- **Not** the post-model constructor freezing VFM Base composition. It writes
  governed km *and* revenue per class, with no basis pinned.
- **Not** a cache or path builder discarding the uptake basis after FY2030. The
  basis reaches the composition function intact; the FY set is what is short.

The eligibility mask (`is_june & is_forecast`) does include post-model rows —
they are June-year forecast rows — so the rows were always addressable. Only the
FY iteration set excluded them.

---

## 2. The fix

Extend the governed composition function rather than adding a parallel
implementation.

`_implied_post_model_rate_lookup` supplies per-class rates for the June years
the drift table does not reach, taken from the post-model rows themselves:

```
rate = existing post-model class revenue / existing post-model class km
```

Measured implied rates, `current_basecase`:

| FY | conventional | Light BEV | PHEV |
|---|---|---|---|
| 2031 | 0.093790 | 0.093790 | 0.046255 |
| 2040 | 0.128235 | 0.128235 | 0.063235 |
| 2050 | 0.166510 | 0.166510 | 0.082110 |

Those rows are already governed and already carry the single application of
Current policy, so re-multiplying reallocated km by the same rate changes the
**composition only** — the pool, the rates and the policy application are all
inherited untouched.

The extension is **bounded by the source's own coverage**
(`exact_vfm_share_coverage`). The chart runs to FY2055 for the official
comparators; the VFM202405 table stops at FY2050. Those later years get no
composition rather than an extrapolated share — inventing a share would be
inventing a scenario. This surfaced immediately as a `KeyError` for FY2051 on
the first run, which is the failure mode working.

---

## 3. What the source supports

`data/vfm_202405/vfm_vkt_shares.csv`, sha256
`81da2535b316245182abc416d1e43a418888eb9ff986b8f663b636a6e375abe8`.

| scenario | uptake basis | FY range | rows |
|---|---|---|---|
| `Base_EV` | MoT VFM base | 2025–2050 | 26 |
| `Fast_EV` | MoT VFM fast | 2025–2050 | 26 |
| `Slow_EV` | MoT VFM slow | 2025–2050 | 26 |

Shares sum to one within 1.0e-06 (the source-precision rule). Conventional
share, showing the scenarios genuinely diverge:

| FY | Base | Fast | Slow |
|---|---|---|---|
| 2030 | 0.732447 | 0.690103 | 0.783782 |
| 2040 | 0.322306 | 0.255155 | 0.420874 |
| 2050 | 0.119794 | 0.082622 | 0.172955 |

No runtime Excel access: the committed CSV is the source.

---

## 4. Result

| check | result |
|---|---|
| common Light pool identical across Base/Fast/Slow | **max difference 0.000e+00** at FY2031, FY2040, FY2050 |
| class km = common pool × canonical source share | matches on **every** row, both engines, independently computed |
| classes sum to the pool | exact |
| Current Base FY2001–FY2055 | **416 rows compared, 0 moved** |
| PED, Heavy RUC, Heavy BEV, MVR, TUC | **0.000e+00** across all three bases |
| formula identities | close through `FORMULA_DEFINITIONS` |

Fast–Slow spread, now carrying to FY2050:

| series | FY2031 | FY2040 | FY2050 |
|---|---|---|---|
| conventional Light RUC km | 15.65% | 51.42% | **75.41%** |
| Light BEV km | 35.30% | 26.82% | 10.81% |
| PHEV km | 35.88% | 14.24% | 2.61% |
| conventional Light RUC revenue | 15.65% | 51.42% | **75.41%** |
| Total RUC | 1.08% | 0.62% | **0.06%** |
| Total NLTF | 0.55% | 0.41% | **0.05%** |

### The aggregate spread is genuinely small, and that is the exact answer

Conventional Light RUC and Light BEV are charged the **same per-km rate**, so
moving kilometres between them is revenue-neutral. Only PHEV, at roughly half
rate, changes total revenue — and PHEV's share barely differs between Fast and
Slow by FY2050 (0.0594 vs 0.0579).

So the composition question is enormous at class level (conventional Light RUC
km differs by 75% between Fast and Slow at FY2050) and almost invisible at
Total NLTF level (0.05%). Both are reported. No width was fabricated to make the
aggregate look more interesting than it is.
