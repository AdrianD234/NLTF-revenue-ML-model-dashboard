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
| **1. Light RUC production treatment** | **conventional-anchor share expansion** |
| **2. PED baseline** | **P0 — raw AR(1), no retention overlay in the Base path** |
| **3. PHEV petrol treatment** | **unresolved — sensitivity only** |

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

This is worth resolving at implementation time, most likely by blending the two
over a short seam window rather than by switching methods. I am not deciding
that here; it is a production design detail, not a Checkpoint 3 question.

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
