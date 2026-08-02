# VFM Base / Fast / Slow extended through FY2050

Bounded amendment to PR #15. Pre-amendment head
`ac144a40d9eecf32c58533e6a916522fdb3abba5`.

The uncertainty methodology, draw engine, typed scenario key, layer registry
and FY2050 modelled-uncertainty bands are untouched.

---

## 1. The cause of the FY2031 collapse

`apply_uptake_levers_to_chart_rows` derived the June years it would visit from
the **rate lookup**, not from the chart rows:

```python
rate_lookup = _drift_rate_lookup(drift_assumptions)   # FY2025-FY2030 only
fys = sorted({fy for _, fy in rate_lookup})
for (scenario, fy), rates in rate_lookup.items(): ...
```

`ev_phev_ped_light_drift_assumptions` is the econometric-window rate table and
stops at FY2030, so **FY2031-FY2050 rows were never visited by any basis**.

Ruled out by trace: it is not a `post_model_extrapolation` segment filter (the
overlay never tests `forecast_segment`), not the post-model constructor pinning
Base composition (it writes governed km *and* revenue per class with no basis
fixed), and not a cache discarding the basis (the basis arrives intact). The
eligibility mask already included post-model rows; only the FY iteration set
excluded them.

Full detail: `vfm_long_run_extension_diagnosis.md`.

---

## 2. The construction

`_implied_post_model_rate_lookup` supplies per-class rates for the June years
the drift table does not reach, from the post-model rows themselves
(`revenue / km`). Those rows are already governed and already carry the single
application of Current policy, so re-multiplying reallocated km by the same
rate changes **composition only**.

```
LightPool_t   = unchanged governed post-model pool
Conventional_t = LightPool_t x VFM_ConventionalShare_s,t
LightBEV_t     = LightPool_t x VFM_BEVShare_s,t
PHEV_t         = LightPool_t x VFM_PHEVShare_s,t
```

Two guards, both of which fired during development and are now permanent:

- **Bounded by source coverage.** The chart runs to FY2055; the VFM202405 table
  stops at FY2050. Later years get no composition rather than an extrapolated
  share — this surfaced as a `KeyError` for FY2051 on the first run.
- **Bounded to governed scenarios.** The derived lookup is restricted to the
  scenarios the drift table already governs (the Current finalist paths).
  Without that, rates were derived for `mbu26_official` and `befu26_official`
  and the published comparator kilometres were being recomposed. Caught by
  `test_ev_uptake_levers.py`.

---

## 3. Source contract

`data/vfm_202405/vfm_vkt_shares.csv`, sha256
`81da2535b316245182abc416d1e43a418888eb9ff986b8f663b636a6e375abe8`.
No runtime Excel access.

| uptake basis | VFM scenario | FY range | rows |
|---|---|---|---|
| MoT VFM base | `Base_EV` | 2025–2050 | 26 |
| MoT VFM fast | `Fast_EV` | 2025–2050 | 26 |
| MoT VFM slow | `Slow_EV` | 2025–2050 | 26 |

Shares finite, non-negative, summing to one within 1.0e-06. Conventional share:

| FY | Base | Fast | Slow |
|---|---|---|---|
| 2030 | 0.732447 | 0.690103 | 0.783782 |
| 2040 | 0.322306 | 0.255155 | 0.420874 |
| 2050 | 0.119794 | 0.082622 | 0.172955 |

---

## 4. Results

### Pool invariance

| FY | Base | Fast | Slow | max difference |
|---|---|---|---|---|
| 2031 | 20738.422218 | 20738.422218 | 20738.422218 | **0.000e+00** |
| 2040 | 32991.652142 | 32991.652142 | 32991.652142 | **0.000e+00** |
| 2050 | 51820.865772 | 51820.865772 | 51820.865772 | **0.000e+00** |

### Class allocation, FY2050 (million km)

| basis | conventional | Light BEV | PHEV |
|---|---|---|---|
| Base | 6207.8288 | 42570.7376 | 3042.2994 |
| Fast | 4281.5436 | 44461.8883 | 3077.4339 |
| Slow | 8962.6689 | 39860.0519 | 2998.1450 |

Every value equals `common pool × canonical source share`, computed
independently from the CSV — matched on all 72 audit rows, both engines.

### Fast–Slow spread, now carrying to FY2050

| series | FY2031 | FY2040 | FY2050 |
|---|---|---|---|
| conventional Light RUC km | 15.65% | 51.42% | **75.41%** |
| Light BEV km | 35.30% | 26.82% | 10.81% |
| PHEV km | 35.88% | 14.24% | 2.61% |
| conventional Light RUC revenue | 15.65% | 51.42% | **75.41%** |
| Total RUC | 1.08% | 0.62% | **0.06%** |
| Total NLTF | 0.55% | 0.41% | **0.05%** |

### Where the aggregate width genuinely collapses — and why

Conventional Light RUC and Light BEV are charged the **same per-km rate**
(0.166510 at FY2050), so moving kilometres between them is revenue-neutral.
Only PHEV, at roughly half rate (0.082110), moves total revenue — and PHEV's
share barely differs between Fast and Slow by FY2050 (0.0594 vs 0.0579).

So the composition question is enormous at class level and almost invisible at
Total NLTF level. Both are reported. **No width was fabricated** to make the
aggregate look more interesting than it is.

---

## 5. Preservation

| check | result |
|---|---|
| Current Base, FY2001–FY2055 | **416 rows compared, 0 moved** |
| Actuals, comparison, conflict paths at the default basis | **0 moved** |
| BEFU26 / MBU26 published rows | **0 moved**, any basis |
| PED, Heavy RUC, Heavy BEV, MVR, TUC | **0.000e+00** across all three bases |
| Heavy-BEV default | still Off under the typed key |
| formula identities | 312 checks close through `FORMULA_DEFINITIONS` |

Movement occurs **only** under Fast/Slow, **only** FY2031–FY2050, **only** in
the Light class series and their governed rollups — 1 800 rows across
`current_basecase`, `current_comparison_1` and the three conflict scenarios,
all of which are Current finalist paths that already inherited the composition
FY2025–FY2030 before this amendment.

### Uncertainty pack

Numerically identical: maximum absolute difference **7.3e-12** across
`central`, `lower80`, `lower50`, `draw_median`, `upper50`, `upper80` on all
1 000 rows — about 1e-15 relative, i.e. floating-point reassociation from the
extra (mathematically no-op) allocation pass at the Base basis, not a value
change. The parquet byte hash therefore moved; the numbers did not.

---

## 6. Browser acceptance

Read from rendered Plotly arrays. Light RUC revenue, all layers:

| FY | envelope lower (Fast) | envelope upper (Slow) |
|---|---|---|
| 2031 | 1.253640 | 1.464904 |
| 2040 | 1.079480 | 1.780585 |
| 2050 | **0.712920** | **1.492374** |

Matching the model exactly (Fast FY2050 712.92, Slow 1492.37 $m). Chart caption
reports "widest gap 70.69% of level".

Ten legend entries; chart 1836 px of 1920 and 1366 px of 1440; no horizontal
overflow; **zero console errors**. Screenshots in `screenshots/`.

---

## 7. Performance

| stage | mean ms |
|---|---|
| pack load (cold, once per process) | 36.0 |
| band lookup per series | 0.172 |
| layer catalogue build | 0.013 |
| figure assembly, default | 85.3 |
| figure assembly, all layers | 93.4 |
| **whole render path** | **91.6** |

Still inside the 100 ms target, and marginally faster than the 93.1 ms
pre-amendment benchmark. No runtime Excel access, no model fitting, no
simulation.

**Cold first render is slower.** The composition loop now covers ~31 June years
across the Current scenarios instead of 6, so the one-off view construction
grew; the per-interaction render path is unaffected because it reads cached
frames. Reported rather than optimised — reducing it belongs to the compiled-
scenario performance workstream, not this bounded amendment.
