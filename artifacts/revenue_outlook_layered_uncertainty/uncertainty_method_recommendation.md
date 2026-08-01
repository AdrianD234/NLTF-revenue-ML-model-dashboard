# Gate B (revised) — uncertainty method recommendation

**Supersedes the first Gate B pass.** That pass read only
`annual_predictions.parquet` (58 finalist rows, H1–H3) and concluded the
repository had no long-horizon evidence and that a saturating fit was
unfittable. **Both conclusions were wrong.** The committed rolling-origin pack
in `artifacts/long_horizon_validation/` carries 1 990 raw quarterly
forecast/actual rows to H20 with per-cell samples an order of magnitude larger,
and the curve *is* fittable — for PED it saturates cleanly.

The earlier report is retained as `annual_predictions_audit.md`: its analysis of
`annual_predictions.parquet` stands as an audit of **that file**, and only its
repository-wide conclusion is withdrawn.

Builders: `scripts/build_uncertainty_method_evidence.py`,
`scripts/build_uncertainty_method_candidates.py`

---

## 1. Evidence inventory — what each source actually measures

| source | rows | horizon | model error | macro-driver error | rate error | bridge error | composition error |
|---|---|---|---|---|---|---|---|
| `annual_predictions.parquet` | 58 finalist | H1–H3 annual | ✅ | ❌ realised drivers | ❌ | ❌ | ❌ |
| `long_horizon_predictions.csv` | 1 990 | H1–H20 quarters | ✅ | ❌ **actual-driver** | ❌ | ❌ | ❌ |
| `long_horizon_june_year_errors.csv` | 1 148 | JY H1–H5 | ✅ | ❌ actual-driver | ❌ | ❌ | ❌ |
| MBU26 archived forecast error | per governed map | published horizon | ✅ | ✅ | ✅ | partial | partial |

Two things follow, and they are the assumptions this design rests on:

1. **The rolling-origin pack is actual-driver.** Exogenous inputs at each target
   quarter are the *observed* values, so it isolates model degradation with
   horizon and **understates** true forward error, which also carries
   Treasury-driver error. It is used here for the horizon **shape** and for the
   level, with that conservative bias stated. It must never be described as
   including driver uncertainty.
2. **The MBU26 archived source is the only one that includes driver error**, but
   it is the official model's error, not the current finalists'. It is a
   cross-check on the level, not a substitute.

**Do not mix quarterly and annual error concepts.** Quarterly errors are wider
than June-year-aggregated errors because within-year noise partly cancels. The
Revenue Outlook chart is a June-year chart, so **the band basis must be the
June-year aggregation**. The first pass's comparison of a 4.45% annual number
against a 12.79% quarterly number was not a like-for-like comparison.

---

## 2. The horizon shape, on the correct (June-year) basis

`long_horizon_june_year_quantiles.csv`, cohort `all_available`, all targets.

**80% relative width (%)**

| stream | JY H1 (FY2026) | H2 (FY2027) | H3 (FY2028) | H4 (FY2029) | H5 (FY2030) |
|---|---|---|---|---|---|
| PED | 3.17 | 9.78 | 12.72 | 12.46 | **12.68** |
| HEAVY_RUC | 6.66 | 10.03 | 8.22 | 7.75 | **9.72** |
| LIGHT_RUC | 22.30 | 23.99 | 21.42 | 20.61 | **23.11** |

**50% relative width (%)**

| stream | H1 | H2 | H3 | H4 | H5 |
|---|---|---|---|---|---|
| PED | 1.65 | 2.10 | 9.24 | 9.24 | **9.78** |
| HEAVY_RUC | 4.51 | 3.33 | 3.66 | 1.90 | **3.17** |
| LIGHT_RUC | 4.28 | 5.71 | 11.14 | 11.78 | **16.78** |

Sample sizes per cell: PED 26/61/33/51/18, HEAVY_RUC 19/43/23/33/12,
LIGHT_RUC 13/28/14/18/6.

**Reading:** PED grows sharply to JY H3 and then flattens. HEAVY_RUC is flat and
noisy with no trend. LIGHT_RUC is flat at a high level on the 80% band while its
50% band is still climbing. So on the annual basis **the curve has largely
levelled off by FY2028–FY2030**, which is the single most important input to the
H21+ decision.

### Sensitivities

| variant | effect |
|---|---|
| exclude 2020–2021 targets | PED collapses at short horizon (3.17 → 2.31 at H1) and only reaches 10.63 by H5; HEAVY narrows to 5.27 at H5. COVID is doing real work here. |
| `balanced_h20` cohort | LIGHT_RUC starts far narrower (1.77 at H1) then jumps to 23.11 by H5, i.e. its apparent flatness in the headline is partly a composition effect. |

The quarterly view (`long_horizon_error_quantiles.csv`, H1–H20 with bootstrap
intervals) tells the same story with more resolution: PED's quarterly 80% width
goes 3.27 → 12.58 (H12) → 12.64 (H20), saturating around H9–H10.

---

## 3. Is a saturating curve fittable? Yes — but only where it has saturated

Fitted on the quarterly smoothed widths,
`w(H) = w∞ − (w∞ − w₁)·exp(−k(H−1))`:

| stream | level | k | half-life (quarters) | w∞ | RMSE |
|---|---|---|---|---|---|
| PED | 80 | 0.2101 | **3.3** | 13.50% | 0.63 |
| LIGHT_RUC | 80 | 0.0622 | 11.2 | 41.21% | 1.70 |
| HEAVY_RUC | 80 | **0.0030** | **229.7** | **69.57%** | 0.49 |

**PED's fit is genuine** — it saturates within ~3 quarters of half-life at 13.5%,
almost exactly the plateau value. **HEAVY_RUC's fit is degenerate**: k ≈ 0.003
means the model has fitted a near-straight ramp, so `w∞ = 69.57%` is pure
extrapolation from a curve that never turned over. Using it for FY2050 would be
inventing a number, not fitting one.

So my earlier "unfittable" claim was wrong, and the corrected position is more
useful: **the saturating candidate is trustworthy exactly where it agrees with
the plateau, and untrustworthy exactly where it diverges from it.**

---

## 4. H21+ candidates (FY2031–FY2050), 80% width

| stream | candidate | FY2030 | FY2031 | FY2040 | FY2050 |
|---|---|---|---|---|---|
| PED | plateau | 12.79 | 12.79 | 12.79 | **12.79** |
| PED | saturating | 12.79 | 13.41 | 13.50 | **13.50** |
| PED | √horizon *(stress)* | 12.79 | 14.02 | 22.16 | **28.61** |
| HEAVY_RUC | plateau | 11.59 | 11.59 | 11.59 | **11.59** |
| HEAVY_RUC | saturating | 11.59 | 11.54 | 17.51 | **23.43** |
| HEAVY_RUC | √horizon *(stress)* | 11.59 | 12.70 | 20.08 | **25.93** |
| LIGHT_RUC | plateau | 33.37 | 33.37 | 33.37 | **33.37** |
| LIGHT_RUC | saturating | 33.37 | 36.22 | 40.68 | **41.17** |
| LIGHT_RUC | √horizon *(stress)* | 33.37 | 36.56 | 57.80 | **74.62** |
| any | legacy constant *(current fan)* | 4.5–4.9 | 4.5–4.9 | 4.5–4.9 | **4.5–4.9** |

For PED, plateau and saturating differ by 0.7pp at FY2050 — the choice barely
matters where the curve genuinely saturated. For HEAVY_RUC they differ by
**11.8pp**, entirely on the strength of a degenerate fit.

Indicative Total NLTF 80% width (bracketed between independent and comonotonic
component aggregation — the real number needs draw-level propagation, which is
deliberately not built at this gate): plateau 13.1% at FY2030 rising to 21.6% at
FY2050; √horizon reaches 48.3%.

---

## 5. Recommendation

### Band basis
Use the **June-year aggregation** from `long_horizon_june_year_errors.csv` for
level *and* shape. It is the same time grain as the chart, has the larger and
more horizon-complete samples, and avoids the quarterly/annual concept mixing.
Cross-check the level against the MBU26 archived source and record the gap as
the estimated driver-error understatement.

### Horizon segmentation
| FY range | quarter horizon | label |
|---|---|---|
| FY2026–FY2028 | H1–H12 | `backtest_supported` |
| FY2029–FY2030 | H13–H20 | `extended_conditional` — actual-driver evidence, thinner samples |
| FY2031–FY2050 | H21+ | `inferred_long_run` — no evaluation evidence |

The band stays visually continuous across the seams; the hover and audit carry
the evidential state.

### H21+ rule — **plateau at the smoothed H20 relative width**

Grounds, in order:

1. **The annual curve has already levelled off** by FY2028–FY2030 for PED and
   HEAVY_RUC. A plateau continues what the evidence shows rather than asserting
   a trend it does not.
2. **The saturating fit is only identified where it agrees with the plateau.**
   Where it disagrees (HEAVY_RUC, +11.8pp at FY2050) it is extrapolating a
   near-linear ramp with k ≈ 0.003. Adopting it would be choosing the wider band
   for reasons the data does not supply.
3. **Least assumptive** and trivially explainable to a governance reader: *"we
   hold the last measured uncertainty flat beyond the evidence."*
4. The known conservative bias (actual-driver understates driver error) argues
   against *also* adopting the widest available continuation — two corrections
   in the same direction stacked on top of each other would be false precision
   of a different kind.

**√horizon is a stress case only**, reported in the audit, never the default:
it triples the Light RUC band by FY2050 on no evidential basis.

**Retain the saturating continuation as a governed alternative** for streams
where the fit is well identified (a k half-life below, say, 20 quarters and RMSE
under ~1pp — PED qualifies, HEAVY_RUC does not), so the choice is per-stream and
auditable rather than global.

### One thing the owner should see before agreeing
On the June-year basis the **Light RUC 80% band is 21–24% at every horizon**,
far wider than PED (3–13%) or Heavy (7–10%), on n = 6–28. Either Light RUC
genuinely carries that much model uncertainty, or the rolling-origin evaluation
is unusually harsh on the GBM residual-correction recipe. A 23%-wide band on the
Light RUC chart is a striking thing to publish, so it is worth a look before it
ships.

---

## 6. Revised series-tier contract

`uncertainty_series_contract_draft.csv`. The first pass over-assigned proxies;
most series derive properly from an uncertain parent.

| tier | count | series |
|---|---|---|
| **1 · direct rolling-origin evidence** | 3 | `ped_vkt_per_capita`, `light_ruc_net_km`, `heavy_ruc_net_km` |
| **3 · derived by draw-level propagation** | 13 | `ped_volume`, `gross_ped_revenue`, `gross_fed_revenue`, `net_fed_revenue`, `light_bev_ruc_net_km`, `phev_ruc_net_km`, `light_ruc_net_revenue`, `light_bev_ruc_net_revenue`, `phev_ruc_net_revenue`, `heavy_ruc_net_revenue`, `total_ruc_net_revenue`, `total_fed_ruc_net_revenue`, `total_nltf_net_revenue` |
| **5 · governed conservative proxy** | 4 | `heavy_bev_ruc_net_km`, `heavy_bev_ruc_net_revenue`, `net_mvr_revenue`, `tuc_net_revenue` |

Light BEV and PHEV activity now derive from the uncertain Light pool times the
selected exact VFM shares; their revenues from uncertain km times governed
rates; PED volume and revenue from uncertain PED activity through the governed
bridge; every aggregate from draw-level `FORMULA_DEFINITIONS` propagation, which
Gate A has already proved closes to 1e-6.

Only four genuinely unsupported leaves remain: MVR, TUC, and the fixed Heavy-BEV
component (whose km/revenue asymmetry is the open item from Gate A).

---

## 7. Stop point

Not built, per instruction: the 10 000-draw pack, final chart layers, full
browser acceptance, full pytest.

**Decisions needed:**
1. Confirm **plateau** as the H21+ default, with the per-stream saturating
   alternative where the fit is well identified.
2. Confirm the June-year basis and the three-state horizon labelling.
3. Look at the Light RUC 21–24% band before it ships.
4. Confirm the tier-5 proxy treatment for MVR, TUC and Heavy BEV.
