# Layered Revenue Scenario and Uncertainty Framework

One full-width chart carrying three independently selectable concepts:
deterministic scenario paths, the non-probabilistic MoT VFM Fast–Slow
structural range, and 50%/80% conditional modelled-uncertainty bands running
to FY2050.

Branch: `feature/revenue-outlook-layered-scenarios-uncertainty`
Base: `28ee2e3` · Reuses the PR #14 checkpoint `d1f3535`

---

## 1. What was built, commit by commit

| commit | content |
|---|---|
| `80cc06e` | **P0** — typed `RevenueScenarioComputationKey` replacing the positional tuple, closing the slot-6 collision |
| `fc7575d` | **Gate A** — post-P0 central-path reconciliation, plus a correction to my own earlier reading |
| `a79ea1a` | Gate B, first pass (superseded; retained as an audit of `annual_predictions.parquet`) |
| `da4805d` | **Gate B revised** on the H1–H20 evidence, plus fail-closed key hardening |
| `17807e0` | June-year basis made authoritative, asymmetric and origin-bootstrapped |
| `a2c845c` | **Sections A–C** — the seeded 10 000-draw pack, closing on every draw |
| *(this)* | **Section D** — layer registry, unified selector, VFM paths, band rendering, audit surface |

---

## 2. The scenario key (P0)

`ev_uptake_key` slot 6 was read as the official comparator vintage id by one
helper and as a Heavy-BEV boolean by another. Production always wrote a
non-empty vintage there, so `bool("BEFU26")` switched Heavy-BEV
reclassification **on in every render**, against its documented default and the
settled `HEAVY_RUC: not_reclassified` contract.

`RevenueScenarioComputationKey` gives every control one named field, fails
closed on invalid values (a truthy string is not a bool; NaN and infinity are
rejected rather than silently becoming `()`), serialises canonically and
carries a stable digest. A repo-wide source scan asserts no production module
indexes by position, and an AppTest proves a normal render never touches the
legacy adapter.

**Value impact:** 100 rows, all `heavy_ruc_net_km` / `heavy_ruc_net_revenue`,
both engines. The overlay is a value-preserving reclassification
(−14.233264 out of `heavy_ruc_net_revenue`, +14.233264 into
`heavy_bev_ruc_net_revenue` at FY2030), so no aggregate moved — but the chart
carries `heavy_ruc_*` and not `heavy_bev_*`, so a reader saw Heavy RUC lower
with no visible destination.

**Gate A:** 2 250 rows across chart · line reconciliation · stack components ·
`FORMULA_DEFINITIONS` recomputed from leaves, both engines, both Current
scenarios, FY2026–FY2050. **Zero residuals above 1e-6.** Official BEFU26 and
MBU26 rows byte-equal to the committed CSVs.

---

## 3. The uncertainty basis

June-year aggregation of the committed rolling-origin evaluation. Plateau
continuation. Three evidence states. All owner-approved.

**Smoothed seam (FY2030), 80% span:** PED 16.84% · Heavy RUC 10.41% ·
Light RUC 32.19%.

Bands are **asymmetric**, because the evidence is:

| stream | lower distance | upper distance | median multiplier |
|---|---|---|---|
| PED | 14.32% | 2.52% | 0.9482 |
| LIGHT_RUC | **26.08%** | 6.11% | 0.9395 |
| HEAVY_RUC | 6.28% | 4.13% | 0.9738 |

Smoothing acts on the **dispersion around the median**, never on the raw
quantiles — running isotonic straight over q10/q90 drags a drifting bias into
the width, which inflated Light RUC by ~9pp of pure artefact in an earlier
pass.

---

## 4. The draw engine (A–C)

10 000 deterministic draws of three parent shocks. Marginals are the empirical
June-year log errors quantile-mapped onto the governed targets by a monotone
piecewise-linear transform pinned at the five knots — the governed quantiles
reproduce exactly, the asymmetry and bias survive, and no normal approximation
touches the values.

Dependence: Gaussian copula on a Spearman rank correlation from **79 aligned
(origin, june_year) observations** — full weight, no shrinkage.
ρ(LIGHT, HEAVY) = 0.472, ρ(PED, HEAVY) = 0.130, ρ(PED, LIGHT) = 0.115.

**Identity closure: 350 checks (14 formulas × 25 June years), each on all
10 000 draws. Zero failures, worst residual exactly 0.000e+00.**

Aggregates come from aggregate draws — a test proves the drawn Total RUC band
is strictly narrower than summed component endpoints, which is what a positive
LIGHT/HEAVY correlation implies.

**Tier-5 contribution to the Total NLTF 80% span:** heavy_bev_proxy 0.21%
(FY2030) → 1.63% (FY2050); mvr_proxy under 0.2%; tuc exactly 0. None dominates.

Pack: `data/revenue_outlook_uncertainty/` — 1 000 band rows, 40 series,
FY2026–FY2050 with no gaps, **byte-identical across rebuilds**.

---

## 5. The layered chart (D)

`model_dashboard/revenue_chart_layers.py` is the single registry. One
`st.multiselect("Show on chart")` drives everything; the per-trace checkbox
popover is gone.

Selectable: Actual · Current Base · High population/comparison · **MoT VFM Fast
uptake** · **MoT VFM Slow uptake** · official comparators · conflict paths ·
50% band · 80% band · VFM Fast–Slow range.

**Default:** Actual, Current Base, High population, official comparator,
conflict Medium, behavioural comparison, plus the 50% and 80% bands. The VFM
layers are one click away.

**Z-order** (asserted in the registry and on the figure): 80% band → VFM
structural range → 50% band → deterministic paths.

**Colours:** the two modelled bands share one slate hue at different opacities
so they read as inner/outer of one object; the VFM envelope keeps a distinct
teal. VFM Fast is purple, Slow is teal.

**VFM Fast/Slow run to FY2050.** They separate FY2025–FY2030 (FY2030: Fast
6.391135, Slow 6.422642, Base 6.408493 between them) and are identical from
FY2031, because the post-model layer is composition-invariant. That is a
property of the model, stated in the layer's interpretation text.

The separate right-hand fan chart stays removed. Three lazy audit toggles —
fan detail, modelled-uncertainty audit, VFM range audit — each build nothing
until asked.

---

## 6. Browser acceptance

Screenshots in `screenshots/`. Numbers read from rendered Plotly arrays.

**Total NLTF revenue, FY2030, all layers, 1920×1080:**

| quantity | value |
|---|---|
| Current Base | 6.408493 |
| VFM Fast / Slow | 6.391135 / 6.422642 (Base between them) |
| 80% band | 5.767471 → 6.593651 |
| 50% band | 5.973106 → 6.431544 (nested) |

**Light RUC revenue, FY2030 — the governed contract, rendered:**

| quantity | rendered | governed |
|---|---|---|
| 80% span | **32.1877%** | 32.19% |
| lower distance | **26.0798%** | 26.08% |
| upper distance | **6.1079%** | 6.11% |

Chart width 1836 px of 1920, 1366 px of 1440. No horizontal overflow. **Zero
console errors.** The all-layers view (10 legend entries, 3 band layers)
remains legible at both widths.

---

## 7. Performance

`performance_timings.csv`:

| stage | mean ms |
|---|---|
| uncertainty pack load (cold, once per process) | 26.7 |
| band lookup per series | **0.144** |
| layer catalogue build | 0.014 |
| figure assembly, default (2 bands, 4 paths) | 89.6 |
| figure assembly, all layers (3 bands, all paths) | 89.4 |
| **whole render path (lookup + assembly)** | **93.1** |

Target ≤ 100 ms met. Adding the third band costs nothing measurable. The
runtime performs no simulation, loads no workbook and fits no model — a test
asserts the draw-engine symbols are absent from `app.py`.

---

## 8. Idempotency

Every builder rerun back to back: **22 of 23 governed files byte-identical**.
The only file that changes is `performance_timings.csv`, which records
wall-clock measurements.

---

## 9. Known limitations, stated plainly

- **The bands are conditional.** The rolling-origin evaluation uses observed
  future economic drivers, so it isolates model degradation and **excludes
  Treasury-driver forecast error**. Every label, hover and audit says so.
- **The Current line may sit outside the inner 50% band** where historical
  errors are biased. That is the evidence, not a defect; the 50% band is always
  nested inside the 80%, and the median multiplier is disclosed.
- **Light RUC's seam rests on 6 origins** with a q10 bootstrap spanning a
  factor of 4.7. Retained uncapped per the owner decision, with the thinness in
  the audit.
- **FY2031–FY2050 is `inferred_long_run`** — no evaluation evidence exists
  there; the plateau holds the last measured distribution flat.
- **TUC carries zero modelled uncertainty** as a fixed governed component, so
  the Total NLTF band does not cover it.
- **Heavy-BEV kilometres are not conserved by the reclassification**
  (`heavy_ruc_net_km` −38.55 with `heavy_bev_ruc_net_km` +0). Reported in Gate
  A, unfixed: it would change the composition architecture, and it only
  manifests when Heavy-BEV is explicitly switched on, which after P0 is never
  the default.
- **Total NLTF's 80% span grows 12.68% → 22.51%** from FY2030 to FY2050 under a
  flat per-stream plateau. The growth is compositional: Light RUC, the widest
  stream, becomes a larger share of the total.
