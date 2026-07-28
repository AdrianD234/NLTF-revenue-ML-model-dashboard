# Checkpoint 3 — final design verdict

Branch `investigation/p0-fleet-allocation-semantics`. Investigation only: no
production code, governed pack, checkpoint or dashboard value was changed.

Regenerate with:

    .venv\Scripts\python.exe scripts\checkpoint3a_ped_retention_falsification.py
    .venv\Scripts\python.exe scripts\checkpoint3bc_light_fleet_and_phev.py

All seven Checkpoint 3 hard gates pass. Runtime lineage and the λ/PED
double-count question are treated as settled and were not reopened.

---

## Summary of the three verdicts

| question | verdict |
|---|---|
| **1. Light RUC production treatment** | **conventional-anchor share expansion, immediate VFM shares from FY2026** (seam resolved in Checkpoint 3.1B) |
| **2. PED baseline** | **P0 — raw AR(1), no retention overlay in the Base path** |
| **3. PHEV petrol treatment** | **unresolved — sensitivity only** |
| **4. H21+ policy** | **current-model numeric Light RUC path ends at FY2030** (Checkpoint 3.1C) |

---

## 1. Light RUC — conventional-anchor share expansion

Both candidate methods were built on identical inputs and judged on the four
stated criteria. Neither was selected on MBU26 proximity.

| criterion | share anchor | actual-anchored add-on |
|---|---|---|
| FY2025 classes are the actuals | yes | yes |
| FY2026 pool step | +9.98% | +7.82% |
| FY2026 BEV step | **+52.85%** | **+26.41%** |
| FY2026 PHEV step | +50.96% | +33.71% |
| FY2035 conventional share vs VFM | 0.00 pp (exact by construction) | **+8.05 pp drift** |
| conservation | exact | exact |
| scenario scalability | pool fixed by Base share; presets reallocate it | **pool moves with the preset** |
| explainability | one rule | two rules |

**Score: share anchor better on scalability and explainability, tied on
conservation, worse on continuity.** The add-on is better on one criterion of
four, so it is not materially better and the stated decision rule selects the
share anchor.

Gate `presets_preserve_base_pool` confirms the scalability property directly:
under Base, Fast and Slow the allocated pool equals the Base-derived pool to
3.6e-12, so an uptake preset is a pure composition lever.

### The one genuine weakness, stated plainly

The share anchor has a **level discontinuity at the actual/forecast seam**. The
FY2025 BEV actual is 820.6 million km against VFM's own FY2025 BEV of 1054.8 —
22% lower. The share anchor jumps to the VFM-implied level in a single year, so
BEV steps +52.8% into FY2026. The add-on avoids this by construction because it
starts from the actual and applies VFM *changes*.

> **SUPERSEDED by Checkpoint 3.1B.** I suggested here that this be resolved by
> blending over a short seam window. That was a judgement offered without
> checking it, and the evidence overturns it: the FY2025 actual conventional
> share sits *above* the whole VFM cone, so blending pushes the share vector
> outside it, and a multi-year blend defers the adjustment into a larger later
> jump. The observed FY2024→FY2025 BEV outturn was +98.5%, against which a
> +52.8% step is a deceleration. **Immediate VFM shares from FY2026 is the
> recommendation.** See §3.1B.

### Long-horizon caution

The share anchor is well supported in the decision window and degrades beyond
it, because the raw Light RUC model grows faster than VFM's conventional path:

| FY | raw model vs VFM conventional | share-anchor pool vs MBU26 pool |
|---|---:|---:|
| 2026 | −1.2% | +0.9% |
| 2030 | +9.3% | +0.7% |
| 2033 | +22.8% | +14.4% |
| 2035 | +35.1% | +26.8% |

Dividing a strongly growing conventional anchor by a falling conventional share
compounds. FY2030 is H15–H18; FY2035 is roughly H40, inside the zone the repo
already classifies as `unvalidated_extrapolation_h21_plus`. So this is a known
horizon-governance problem rather than a new defect, and it applies to the
current architecture too. It should not block the FY2026–FY2030 correction, but
it should be flagged wherever the pool is read beyond FY2030.

> **STRENGTHENED by Checkpoint 3.1C.** "Flagged" is not sufficient. Run to
> FY2050 the construction implies a pool of 185,828 million km, 3.87× VFM's own
> pool, because dividing by a conventional share falling to 0.120 amplifies
> without bound. The recommendation is now to **end the current-model numeric
> Light RUC path at FY2030**, not to label it. See §3.1C.

---

## 2. PED — P0 is the production baseline

### The test

Rolling-origin, origin-correct, no target leakage. P0 is the raw recursive
forecast; P1 multiplies it by the same VFM retention curve the runtime applies,
re-normalised to 1 at each origin. Identical origins, drivers and actuals.

**P1 is a structural hindcast, not a real-time forecast test.** `data/vfm_202405`
is a single May-2024 vintage; no historical vintages exist. At every origin
before 2024Q2 the retention curve embeds information unavailable at the time, so
P1 holds an information advantage a real forecaster would not have had.

### Result — P1 is worse in every cohort, at every horizon

AR(1) production model, H1–H12, 56 origins:

| cohort | n | P0 WAPE | P1 WAPE | WAPE improvement |
|---|---:|---:|---:|---:|
| all available | 606 | 2.492 | 2.674 | **−7.28%** |
| balanced | 540 | 2.535 | 2.653 | **−4.65%** |
| all available ex-COVID | 510 | 1.627 | 1.932 | **−18.75%** |
| balanced ex-COVID | 312 | 1.146 | 1.520 | **−32.61%** |

June-year annual aggregation: −3.62% (balanced) to −35.54% (balanced ex-COVID).
Every individual horizon H1–H12 is worse, monotonically widening from −2.9% at
H1 to −6.7% at H12.

### Why the full-sample bias looks better but the accuracy is worse

P1 does reduce mean signed error (+1.11% → +0.60% balanced). That improvement is
entirely a COVID artefact:

| target years | n | P0 signed error | P1 signed error |
|---|---:|---:|---:|
| excluding FY2020–21 | 510 | **−0.365%** | **−0.915%** |
| FY2020–21 only | 96 | +6.907% | +6.337% |

Outside COVID the AR(1) already slightly *under*predicts, so pulling forecasts
down makes both bias and accuracy worse. The apparent gain comes from the
retention curve happening to push in the right direction during a pandemic
collapse — for entirely the wrong reason.

### Decision gate

Neither gate is met. `gate_a_five_pct_wape_or_mape` = False (improvement is
negative). `gate_b_consistent_smaller_improvement` = False (not consistent, and
not positive). **Adopt P1: False.**

Per the stated rule the burden of proof sits on the post-model adjustment, and
it is not discharged. **P0 becomes the production baseline; P1 becomes an
explicit VFM fleet-transition sensitivity.**

### The honest limit of this test

The retention ratio spans only **0.977 to 1.000** across the entire backtest
window, because the logistic midpoint is 2042 and the test ends 2025Q4. The
overlay's substantive claim is about FY2030–FY2050, where it reaches 0.938 by
FY2030 and far lower later, and where no observations exist.

So this test shows the overlay is **not supported by out-of-sample evidence and
mildly harmful where it can be measured**. It cannot show the overlay is wrong
about the 2040s. That is precisely why the decision rule places the burden on
the adjustment: absent evidence, the verified econometric output stands.

There is a second reason to prefer P0 that the test also surfaces. Under P0 the
petrol share of total light VKT still falls from 0.701 to 0.520 by FY2035
(`combined_light_fleet_paths.csv`), because the other classes grow around a
roughly flat petrol path. Electrification is already represented in the
composition without a second explicit displacement.

---

## 3. PHEV petrol — unresolved, sensitivity only

### What the sourcing evidence shows

In the VFM source, light petrol VKT and the Light RUC pool are **disjoint**.
Their sum reconciles to VFM's own implied total light VKT to within 6.5 million
km out of ~46,000 (0.014%), and the residual shrinks as PHEV kilometres grow —
the opposite of what partial inclusion would produce.

| FY | VFM light petrol | VFM Light RUC pool | sum | VFM implied total | residual |
|---|---:|---:|---:|---:|---:|
| 2025 | 31464.6 | 14607.1 | 46071.7 | 46078.2 | 6.49 |
| 2030 | 30999.6 | 17651.6 | 48651.2 | 48653.1 | 1.89 |
| 2035 | 28677.5 | 22281.3 | 50958.8 | 50957.3 | −1.53 |

So PHEV kilometres sit in the Light RUC pool and are **excluded from the petrol
VKT series**. A plug-in hybrid nevertheless burns petrol on some fraction of its
kilometres, and that petrol attracts excise.

I could not establish from the repository whether the MBU26 litres-per-100km
intensity is grossed up to cover PHEV petrol. The `ped_litres_per_100km` series
is documented only as "MBU26 litres intensity" with no statement of scope.
**This is therefore unresolved and must not be silently assumed to be zero.**

Note the direction: if PHEV petrol is genuinely missing, the model *understates*
PED — the opposite sign to the λ Light RUC defect.

### Sensitivity

Extra gross PED revenue if PHEV kilometres consume the given fraction of
conventional petrol intensity, on the P0/L1 path:

| fraction | FY2030 extra litres (m) | FY2030 extra $m | % of gross PED | FY2035 extra $m | % of gross PED |
|---:|---:|---:|---:|---:|---:|
| 0% | 0.0 | 0.0 | 0.00% | 0.0 | 0.00% |
| 25% | 39.9 | 37.5 | 1.41% | 101.7 | 3.29% |
| 50% | 79.9 | 75.1 | 2.81% | 203.4 | 6.58% |
| 75% | 119.8 | 112.6 | 4.22% | 305.1 | 9.87% |
| 100% | 159.8 | 150.2 | 5.62% | 406.8 | 13.16% |

For scale, a 50% assumption at FY2030 is +$75.1m against a total FY2030 gap of
−$415.3m. Material, but well short of the Light RUC λ effect (−$222.5m).

**Recommendation:** carry this as a labelled sensitivity and put the sourcing
question to whoever owns the MBU26 intensity series. Do not adopt a production
figure on the strength of this analysis.

---

## 4. Hard gates

| gate | max abs delta | status |
|---|---:|---|
| class sums close | 0.0 | pass |
| total light VKT conserved (petrol + pool) | 0.0 | pass |
| pool shares sum to one | 2.2e-16 | pass |
| raw conventional preserved under Base | 0.0 | pass |
| presets preserve the Base pool | 3.6e-12 | pass |
| no λ transfer in L1 | 0.0 | pass |
| FY2025 classes are the actuals | 0.0 | pass |

Each kilometre belongs to exactly one propulsion class by construction: the
pool is partitioned by three shares summing to one, and petrol VKT is disjoint
from the pool.

---

## 5. Recommended production design

    PED:
        light petrol VKT = raw AR(1) VKT per capita x population
        no retention overlay in the Base path
        VFM retention retained as an explicit fleet-transition sensitivity

    Light RUC:
        conventional = raw Light RUC model forecast
        pool         = conventional / VFM_Base_conventional_share
        BEV          = pool x VFM_Base_BEV_share
        PHEV         = pool x VFM_Base_PHEV_share
        alternative presets reallocate the Base-derived pool, never resize it
        seam blending at FY2025/FY2026 to be resolved at implementation

    lambda:
        removed from every decision-facing level
        artefacts retained as legacy audit evidence only

    PHEV petrol:
        labelled sensitivity, no production assumption adopted

---

## 6. Artifacts

| file | contents |
|---|---|
| `ped_retention_rolling_predictions.csv` | every origin/target pair, P0 and P1, with retention ratio |
| `ped_retention_horizon_metrics.csv` | MAPE/WAPE/RMSE/signed by horizon and cohort |
| `ped_retention_annual_metrics.csv` | June-year aggregated metrics |
| `ped_retention_band_summary.csv` | pooled H1–H12 and H13–H20 bands |
| `ped_retention_decision_gate.csv` | the gate evaluation and its inputs |
| `light_ruc_anchor_method_comparison.csv` | both methods, FY2025–FY2035 |
| `light_ruc_anchor_method_scorecard.csv` | the four-criterion judgement |
| `light_ruc_preset_pool_invariance.csv` | Base/Fast/Slow pool invariance |
| `combined_light_fleet_paths.csv` | P0/L1 and P1/L1 fleet paths with YoY and shares |
| `phev_petrol_sourcing_evidence.csv` | the disjointness test |
| `phev_petrol_sensitivity.csv` | 0/25/50/75/100% sensitivity |
| `checkpoint_3_hard_gates.csv` | the seven gates |

No production change has been made and no PR has been opened. Workstream A has
not been rerun.

---

# Checkpoint 3.1 — design closure

Three matters were reopened. Two changed my recommendation.

Regenerate with:

    .venv\Scripts\python.exe scripts\checkpoint3a_ped_retention_falsification.py
    .venv\Scripts\python.exe scripts\checkpoint31_seam_and_long_horizon.py

Tests: `tests/test_light_ruc_anchor_design.py` (13) and
`tests/test_fleet_allocation_runtime_semantics.py` (9). All 22 pass.

---

## 3.1A — COVID window corrected. The claim survives.

You were right that the exclusion was coded on the wrong definition. The
specification window is calendar quarters 2020Q1–2021Q4; I had excluded June
years FY2020–FY2021, which is 2019Q3–2021Q2. All three are now reported and
kept distinct, with the origin grid rebalanced inside each so P0 and P1 always
share an identical grid.

AR(1) production, H1–H12, balanced:

| exclusion | n | P0 WAPE | P1 WAPE | improvement | P0 signed | P1 signed |
|---|---:|---:|---:|---:|---:|---:|
| none | 540 | 2.535 | 2.653 | −4.65% | +1.114 | +0.597 |
| **2020Q1–2021Q4 (primary)** | 312 | **1.065** | **1.381** | **−29.59%** | **−0.818** | **−1.227** |
| calendar 2020–2021 | 312 | 1.065 | 1.381 | −29.59% | −0.818 | −1.227 |
| June years FY2020–21 (old) | 312 | 1.146 | 1.520 | −32.61% | −0.953 | −1.401 |

June-year annual WAPE on the primary window: −34.95% (balanced), −33.25% (all
available).

The two calendar definitions are the same set of quarters given the period
labels, and they return byte-identical metrics — a test pins that so they are
never conflated again.

**The COVID-artefact statement stands, on the correct window.** Excluding
2020Q1–2021Q4, P0's signed bias is −0.818% and P1 moves it to −1.227%: the
overlay makes bias *worse*, not better, once the pandemic quarters are removed.
The apparent full-sample bias gain is confined to those quarters. The P0 verdict
is unchanged and slightly stronger.

---

## 3.1B — seam resolved, and it reverses my earlier lean

I previously called the FY2026 BEV step "implausible" and suggested blending.
Two pieces of evidence say otherwise, and I should not have offered that
judgement without checking them.

**First, the observed actuals.** FY2024 → FY2025 outturn was BEV **+98.5%**,
PHEV **+123.2%**, pool **+23.4%**. Against that, the immediate method's FY2026
BEV step of **+52.8%** is a deceleration, not a discontinuity. (Caveat: FY2024
is the first year in which BEV and PHEV were separately recorded, so its base
may be incomplete — the direction is clear but the exact multiple is not.)

**Second, the VFM cone.** The FY2025 *actual* conventional share is 0.9072,
which sits above the entire VFM Base/Fast/Slow cone. Blending toward it
therefore pushes the share vector **outside** the cone:

| method | FY2026 conventional share | inside cone [0.8607, 0.8877] | FY2026 BEV step |
|---|---:|---|---:|
| **A immediate** | **0.8716** | **yes** | +52.8% |
| B two-year | 0.8894 | no | +28.8% |
| C three-year | 0.8953 | no | +21.0% |
| D actual-anchored add-on | 0.8890 | no | +26.4% |

**Third, blending does not smooth — it defers and concentrates.** When the blend
weight reaches 1 the pool catches up in a single step. For the three-year
transition that step lands at **FY2028, inside the backtest-supported zone**,
with pool growth of 12.5% against 1.3% the year before. That is worse than the
seam it was meant to fix. The two-year method also produces a non-monotonic BEV
path (+28.8% then +43.6%).

**Recommendation: A, immediate VFM shares from FY2026.** It is the shortest
transition, the only one inside the VFM cone at FY2026, its seam step is below
recent outturn, and it is the only one that does not manufacture a later
catch-up jump. Blending is rejected on evidence, not on simplicity.

Every method preserves the raw conventional anchor exactly (gate: 0.0).

---

## 3.1C — long-horizon guard: unrestricted share expansion fails

This is the most serious result in the checkpoint. Two-year method shown; A and
B are near-identical, and all three share-anchor methods behave the same way.

| FY | horizon state | raw conventional | conv share | pool | pool YoY | pool ÷ VFM | flag |
|---|---|---:|---:|---:|---:|---:|---|
| 2026 | H1–H12 | 12,968 | 0.889 | 14,581 | +7.8% | 0.97 | WATCH |
| 2028 | H1–H12 | 13,372 | 0.809 | 16,520 | +9.8% | 1.02 | WATCH |
| 2030 | H13–H20 | 14,130 | 0.732 | 19,291 | +7.6% | 1.09 | WATCH |
| 2035 | H21+ | 15,945 | 0.530 | 30,070 | +10.8% | 1.35 | **FAIL** |
| 2040 | H21+ | 17,908 | 0.322 | 55,561 | +14.9% | 1.84 | **FAIL** |
| 2045 | H21+ | 19,978 | 0.189 | 105,844 | +12.4% | 2.65 | **FAIL** |
| 2050 | H21+ | 22,261 | **0.120** | **185,828** | +11.2% | **3.87** | **FAIL** |

By FY2050 the construction implies **185.8 billion light-vehicle kilometres**,
3.87× VFM's own pool, from a conventional anchor of 22,261. That is not a
forecast; it is a division by a share approaching zero. `pool = conventional /
conventional_share` amplifies without bound as the share falls, and the raw
conventional model keeps growing (+35.1% above VFM conventional by FY2035).

First FAIL: FY2035 for A and B; FY2028 for C. The add-on method D never FAILs to
FY2050 (WATCH throughout, FY2050 ratio 1.34) because it never divides by a
shrinking share — that is a genuine long-horizon advantage for D, and the only
criterion on which it wins.

**Recommendation: option 1 — end the current-model numeric path at FY2030.**
The decision-grade window is clean (no FAIL through FY2030 for the recommended
method), and beyond it the construction is not defensible. FY2031+ should not
publish a current-model numeric Light RUC path pending the deferred structural
bridge (P0 #2B). I have not invented that transition here, per instruction.

Note this is a stronger statement than the existing H21+ warning label. A label
is not sufficient when the underlying number is arithmetically divergent rather
than merely uncertain.

---

## 3.1D — production specification

### PED
- **Base:** `light_petrol_vkt = raw AR(1) VKT per capita × population`. No
  retention overlay.
- The VFM petrol-retention curve becomes a **named optional sensitivity**, off
  by default.
- λ has no PED effect: already true at runtime via the raw bridge (alpha 0).

### Light RUC
- **Conventional:** the raw Light RUC model forecast, preserved exactly.
- **Seam:** none. VFM Base shares apply immediately from FY2026 (method A).
- **Pool:** `pool = conventional / VFM_Base_conventional_share`
- **Classes:** `BEV = pool × VFM_Base_BEV_share`, `PHEV = pool × VFM_Base_PHEV_share`
- **FY2025:** the actual class values, untouched.

### Fast / Slow / custom uptake
Preserve the Base-derived pool and reallocate composition only. Verified to
3.6e-12. An uptake preset is a composition lever, never a level lever.

### H21+ policy
The current-model numeric Light RUC path ends at **FY2030**. FY2031+ is
unavailable pending the structural bridge. Do not publish the share-expansion
result beyond FY2030 on the strength of a warning label.

### PHEV petrol
Unresolved. Carry the 0/25/50/75/100% sensitivity; adopt no production figure
until the scope of the MBU26 litres-intensity series is sourced. Direction of
the error is *understatement* of PED.

### λ retirement
Remove from every decision-facing level. Retain `ev_phev_ped_light_drift_assumptions`
and `ev_phev_split_assumptions` as clearly labelled historical audit lineage.
Rename or deprecate `current_light_ruc_total_modelled_km`, which is the raw
conventional model output and is currently named as though it were a total.

---

## Checkpoint 3.1 gates

| gate | max abs delta | status |
|---|---:|---|
| raw conventional preserved under every seam method | 0.0 | pass |
| share vector closes to one | 2.2e-16 | pass |
| pool equals the class sum | 0.0 | pass |
| no λ level in any candidate path | 0.0 | pass |
| presets preserve the Base pool | 3.6e-12 | pass |

## Checkpoint 3.1 artifacts

| file | contents |
|---|---|
| `light_ruc_seam_method_paths.csv` | A/B/C/D, FY2025–FY2050, shares, classes, cone membership |
| `light_ruc_seam_scorecard.csv` | seam criteria plus observed FY2024→FY2025 growth |
| `light_ruc_long_horizon_guard.csv` | FY2050 paths with watch/fail flags and horizon state |
| `checkpoint_31_hard_gates.csv` | the five gates |
| `ped_retention_band_summary.csv` | now carries all three COVID definitions |

No production change has been made and no PR has been opened.
