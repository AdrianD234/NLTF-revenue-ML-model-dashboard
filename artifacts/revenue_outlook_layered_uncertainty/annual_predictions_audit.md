> **SUPERSEDED as a repository-wide conclusion.** This document analysed
> `annual_predictions.parquet` only, and missed the committed rolling-origin
> pack in `artifacts/long_horizon_validation/` (1 990 rows, H1-H20). Its
> findings about *that file* stand and are retained as an audit of it. Its
> conclusions that the repository has only H1-H3 evidence, that a saturating
> curve is unfittable, and its Option 1/2/3 recommendation are **withdrawn**.
> See `uncertainty_method_recommendation.md`.

# Gate B — uncertainty method: findings and recommendation

**Stopping for owner review, as instructed — but not with the deliverable that
was asked for, because the empirical base does not support it.**

The brief's §7 assumes committed out-of-sample forecasts rich enough for
horizon-specific quantiles with pooling and isotonic smoothing across H1–H20,
and §8 assumes an *"observed H1-H20 width curve"* to fit a saturating
continuation to. **Neither exists in this repository.** That finding has to be
settled before three continuation rules are built on top of it.

---

## 1. What the committed out-of-sample evidence actually is

`data/dashboard_evidence_pack/data/annual_predictions.parquet` — the source the
current `Current finalist backtest error` fan already uses.

| | |
|---|---|
| total rows | 130 |
| finalist rows (excluding the Schiff benchmark) | **58** |
| streams | **3** — PED, LIGHT_RUC, HEAVY_RUC (volume streams) |
| origins | 2016Q4 – 2020Q2 |
| horizons present | **1, 2, 3** |

Per-cell sample sizes, finalist rows only:

| stream | H1 | H2 | H3 |
|---|---|---|---|
| HEAVY_RUC | 13 | 9 | **2** |
| LIGHT_RUC | 4 | 5 | **1** |
| PED | 13 | 9 | **2** |

Empirical log-error widths by horizon:

| stream | H | n | 50% width | 80% width |
|---|---|---|---|---|
| HEAVY_RUC | 1 | 13 | 3.16% | 4.86% |
| HEAVY_RUC | 2 | 9 | 1.26% | 3.25% |
| HEAVY_RUC | 3 | 2 | 2.22% | 3.55% |
| LIGHT_RUC | 1 | 4 | 0.83% | 1.39% |
| LIGHT_RUC | 2 | 5 | 0.79% | 2.92% |
| LIGHT_RUC | 3 | **1** | **0.00%** | **0.00%** |
| PED | 1 | 13 | 4.08% | 4.66% |
| PED | 2 | 9 | 2.71% | 3.64% |
| PED | 3 | 2 | 0.40% | 0.64% |

### Why this blocks the design as specified

1. **The supported horizon is 3 years, not 20.** FY2050 is horizon 25. That is
   an 8× extrapolation beyond the last observed error, not the 1.25× the brief
   envisages.
2. **The observed width curve is decreasing and non-monotonic.** PED goes
   4.66% → 3.64% → 0.64%; HEAVY_RUC goes 4.86% → 3.25% → 3.55%. Uncertainty
   does not shrink with horizon — this is sampling noise at n ≤ 13, and at H3
   it is n = 2 and n = 1.
3. **LIGHT_RUC at H3 has n = 1**, so its quantiles collapse to a point and its
   measured width is exactly zero. Any rule anchored on the widest *supported*
   horizon would anchor Light RUC on a single observation.
4. **Candidate C is unfittable.** A constrained saturating growth curve fitted
   to the observed short-run width curve cannot be fitted to three
   noise-dominated, downward-sloping points. Fitting it anyway would be
   inventing the shape and calling it evidence.
5. **Only 3 of the ~25 chartable series have any direct evidence at all**, and
   all three are *volume* streams. There is no direct out-of-sample error for
   any revenue series, any BEV/PHEV class, MVR, TUC, or any aggregate.

The existing production fan sidesteps all of this: it computes **one** quantile
set per stream pooled over all origins and applies that same relative width at
every FY (`_current_finalist_backtest_fan_band_rows` takes `stream_q.iloc[0]`).
It is already effectively candidate A, and it is honest only because it stops
at FY2030.

---

## 2. How much the choice matters

Anchored on the pooled H1–H3 distribution (the only anchor with a defensible
sample: n = 24, 10, 24):

| stream | 80% width at anchor | A · constant to FY2050 | B · √horizon to FY2050 | C · saturating |
|---|---|---|---|---|
| HEAVY_RUC | 4.94% | 4.94% | **14.26%** | unfittable |
| LIGHT_RUC | 4.55% | 4.55% | **13.14%** | unfittable |
| PED | 4.45% | 4.45% | **12.84%** | unfittable |

**B is 2.887× A at FY2050**, and there is no evidence in this repository that
discriminates between them. The choice would be made on judgement alone, then
rendered as a precise-looking band on a decision-facing chart out to 2050.

---

## 3. Series inventory and tier assignment

From `fan_availability` (85 rows, 17 series). Direct empirical evidence exists
for six series; everything else must be derived, proxied, or declared.

| tier | series | count |
|---|---|---|
| **1 · direct current backtest** | `ped_vkt_per_capita`, `light_ruc_net_km`, `heavy_ruc_net_km`, `gross_ped_revenue`, `light_ruc_net_revenue`, `heavy_ruc_net_revenue` | 6 |
| **2 · archived official error** | `light_ruc_net_km`, `heavy_ruc_net_km`, `gross_ped_revenue`, `light_ruc_net_revenue`, `heavy_ruc_net_revenue`, `total_fed_ruc_net_revenue` | 6 (overlapping) |
| **3 · derived from uncertain parents** | `ped_volume`, `gross_fed_revenue`, `net_fed_revenue`, `total_ruc_net_revenue`, `total_fed_ruc_net_revenue`, `total_nltf_net_revenue` — reachable through `FORMULA_DEFINITIONS` once their leaves have draws | 6 |
| **4/5 · proxy required** | `light_bev_ruc_net_km`, `light_bev_ruc_net_revenue`, `phev_ruc_net_km`, `phev_ruc_net_revenue`, `net_mvr_revenue`, `tuc_net_revenue`, `heavy_bev_ruc_net_km`, `heavy_bev_ruc_net_revenue` | 8 |

Tier 3 is the genuinely sound part of the design: propagating leaf draws
through the governed identities is well-founded, and Gate A has just proved
those identities close to 1e-6. The problem is entirely in what the leaves are
anchored on beyond H3.

Note that the tier-4/5 group is not a rounding error — it includes every BEV
and PHEV class, which is exactly where the fleet transition makes the forecast
interesting.

---

## 4. Recommendation

**Do not build the FY2050 band as specified.** Three options, in the order I'd
rank them.

### Option 1 — bands to FY2030, declared scenario range beyond (recommended)

Give every series 50%/80% empirical bands through FY2030 using tier 1–3, with
tier 4/5 proxies explicitly flagged. Beyond FY2030 show the **structural
scenario range** — the VFM Fast–Slow envelope plus High population, which are
real governed alternatives — and do not draw a probabilistic band at all.

This is defensible on the evidence, keeps the layered-chart product (§3, §4,
§5, §10, §12 all survive intact), and is honest about where empirical support
ends. It is close to the existing contract, but with far better series
coverage and proper draw-level propagation.

### Option 2 — FY2050 bands under an explicitly declared assumption

Build them, anchored on the pooled H1–H3 distribution, using **rule A
(constant relative width)** — the least-invented of the three, and the one the
current production fan already implies. Label every FY2031+ row
`inferred_long_run_model_uncertainty` and state in the hover and the audit that
it rests on a 3-year evidence base extrapolated 8×. Rule B is not
recommendable: it produces a 2.9× wider band from the same data with nothing to
justify the exponent.

### Option 3 — commission the evidence

Extend the backtest to more origins and longer horizons, and add revenue-level
and class-level folds, then build the full design. That is a modelling
workstream, not a dashboard one.

---

## 5. What I have not built, per the stop instruction

No 10,000-draw simulation, no uncertainty pack, no chart-layer UI, no
all-series browser acceptance, no full pytest run. Gate A is committed; the
layer registry (§3) and VFM scenario paths (§4) are untouched and remain
straightforward once the uncertainty question is settled — they do not depend
on it.

**Decision needed:** which of the three options, and if Option 2, confirmation
that a band resting on H1–H3 evidence extrapolated to H25 is one you want on a
decision-facing chart.
