# Checkpoint 2 — structural verdict (corrected)

Branch `investigation/p0-fleet-allocation-semantics`. Investigation only: no
production code, governed pack, checkpoint or dashboard value was changed.

Regenerate with:

    .venv\Scripts\python.exe scripts\checkpoint2_runtime_parity.py       # runtime path
    .venv\Scripts\python.exe scripts\checkpoint2_structural_variants.py  # stored-pack mechanics

Tests: `tests/test_fleet_allocation_runtime_semantics.py` (9 passing).

---

## CORRECTION — the first pass mis-specified the runtime path

My first Checkpoint 2 defined Reference A as "stored pack + VFM overlay" and
called `apply_uptake_levers_to_chart_rows()` directly on the committed chart
rows. **That omitted two runtime stages: the raw PED bridge and the Treasury
macro replay.** The result was that I reconstructed the λ-plus-VFM PED
combination the front end is specifically built to avoid, and then diagnosed
it as the live path.

The repository's actual sequence, implemented in `fleet_mix.load_dashboard_frame()`
and in `app.cached_scenario_overlay_rows()`:

    committed pack -> raw PED bridge -> Treasury macro replay -> VFM overlay
    -> FED policy overlay -> front end

`PED_BRIDGE_DEFAULT_MODE = "raw_model"` with **alpha = 0.0**, so the default
bridge restores the raw PED level and discards the λ PED deduction entirely.
`app.py:1194` then sets `adjust_ped = (bridge_mode == PED_BRIDGE_DEFAULT_MODE)`,
with the comment: the optimized bridge already displaces petrol activity, so
only the raw bridge needs the VFM lever. It is a deliberate either/or guard.

**Withdrawn from the first pass:**

| claim | status |
|---|---|
| "Reference A is the actual front end" | wrong — it omitted S2 and S3 |
| "FY2030 front-end total = 5721.97" | wrong — the true value is **6019.02** |
| "PED is displaced twice in the final front end" | **wrong** — see §5 |
| "Three quarters of the displayed gap is post-model" | recomputed against the true S5 value in §4 |
| "Interaction is exactly zero" | still zero, but it is structural, not a finding — see §4 |

**Retained:** everything in §1 about the stored pack. Those level mechanics
were correct and are unaffected.

---

## 0. Correction to the previous checkpoint

My last note downgraded Light RUC to `insufficient_evidence` on the grounds
that the decisive forecast-year test could not be run. That was wrong on the
method, not on the caution. The raw Light RUC forecast was already committed
and replay-verified in two places, and repairing `_light_ruc_feature_frame`
was never necessary:

- `scenario_input_replay_mismatch_report.csv`, `series_id =
  current_light_ruc_total_modelled_km`, `scenario_name = current_basecase` —
  all rows `replay_status = pass`, max `replay_abs_delta` 9.5e-07, and the
  quarterly replay values sum to the annual figure exactly (FY2027:
  3052.255 + 3075.891 + 3270.599 + 3298.763 = 12697.508).
- `ev_phev_split_assumptions.csv`, column `current_light_total_modelled_km`.

Raw annual Light RUC model forecast, asserted in the script:

| FY | million km |
|---|---:|
| 2026 | 12968.092014 |
| 2027 | 12697.507968 |
| 2028 | 13372.423680 |
| 2029 | 13833.483861 |
| 2030 | 14129.750868 |

The earlier `InvalidIndexError` is a real but separate technical defect in an
internal helper. It is logged in §7 and blocks nothing here.

The 27% claim I withdrew stays withdrawn. The class *shares* do match MBU26
closely — but as you note, that validates the share-fitting step and nothing
about the level, because the allocation machinery targets MBU26 proportions by
construction. A good share match is not evidence that the right quantity was
used as the anchor.

---

## 1. What λ actually is

`revenue_line_reconciliation.csv` states the runtime formulas verbatim:

| series | formula in the pack | row role |
|---|---|---|
| `current_light_ruc_total_modelled_km` | sum quarterly current finalist Light RUC total net km before EV/PHEV allocation | **`audit_only`** |
| `light_ruc_net_km` | current Light RUC total modelled km − **λ** × optimized EV/PHEV migration total | `bridge_input` |
| `light_petrol_vkt` | current PED-derived light-petrol VKT − **(1−λ)** × optimized EV/PHEV migration total | `bridge_input` |
| `light_bev_ruc_net_km` | optimized EV/PHEV migration total × MBU26 Light BEV share within EV/PHEV | `bridge_input` |
| `phev_ruc_net_km` | optimized EV/PHEV migration total × MBU26 PHEV share within EV/PHEV | `bridge_input` |

So λ is not a lineage artefact and not a share. **λ is the parameter that
decides how much of a single migration total M is subtracted from the Light
RUC stream and how much from the PED stream.** It sets levels directly.

FY2030, exact:

```
M = BEV + PHEV                    = 2751.234 + 1511.517 = 4262.750
λ = 0.377758
λ·M      = 1610.289   14129.751 − 1610.289 = 12519.462  = light_ruc_net_km
(1−λ)·M  = 2652.462   32439.900 − 2652.462 = 29787.438  = light_petrol_vkt
```

Both reductions are reproduced to 1e-6 in `runtime_stage_waterfall.csv`.

### The decisive forecast-year comparison

Neither the pack's conventional line nor its class sum preserves the raw model
output. FY2026–FY2030, million km:

| FY | raw model | pack conventional | pack class sum | conv − raw | sum − raw |
|---|---:|---:|---:|---:|---:|
| 2026 | 12968.092 | 12352.558 | 14169.000 | −615.534 | +1200.908 |
| 2027 | 12697.508 | 11893.795 | 14198.682 | −803.713 | +1501.174 |
| 2028 | 13372.424 | 12336.184 | 15226.666 | −1036.239 | +1854.243 |
| 2029 | 13833.484 | 12521.359 | 16084.857 | −1312.125 | +2251.373 |
| 2030 | 14129.751 | 12519.462 | 16782.212 | −1610.289 | +2652.462 |

`class sum − raw` equals `(1−λ)·M` in every year — the pool is inflated by
exactly the amount taken off the PED side. `conv − raw` equals `−λ·M`.

The FY2025 equality I reported last time was indeed only the actual anchor.
It does not continue: FY2025 uses the actual and is untouched by λ in the pack
(hard gate `fy2025_actual_classes_unchanged_across_variants`, delta 0.0).

### Why the levels move: the universe is built without EVs

The optimiser conserves a "light mobility universe"
`U_t = raw light-petrol VKT + raw Light RUC modelled km`, then re-splits it
into four classes at MBU26 *proportions*. But both inputs to `U_t` are
conventional-only, while the MBU26 proportions are shares of a universe that
**contains** BEV and PHEV kilometres:

| FY | our `U_t` | MBU26 universe | MBU26 EV+PHEV km | universe gap |
|---|---:|---:|---:|---:|
| 2026 | 45911.116 | 46576.629 | 1842.773 | 665.513 |
| 2028 | 45522.586 | 48877.686 | 3103.516 | 3355.100 |
| 2030 | 46569.651 | 52035.365 | 4763.054 | 5465.715 |

Applying shares-of-a-universe-with-EVs to a universe-without-EVs leaves the
optimiser nothing to build BEV and PHEV kilometres from except the two
conventional streams. That is the mechanism, and it is arithmetically exact:
FY2030, 2652.462 (from PED) + 1610.289 (from Light RUC) = 4262.750 = BEV+PHEV.

This is the narrow, defensible version of a claim I earlier over-stated and
withdrew. It is not "manufactures kilometres from a series that never
contained them" as a general charge against inferring classes from a
conventional anchor — that method is legitimate and is exactly what Variant C
does. It is specific: the *conservation constraint* is imposed on a universe
whose definition does not match the shares applied to it.

---

## 2. The corrected runtime waterfall

Nine parity gates pass (`corrected_runtime_parity_gates.csv`), including:

| gate | max abs delta |
|---|---|
| S2 raw bridge restores the raw PED level | 0.0 |
| S2 − S1 on PED equals exactly (1−λ)·M | 1.8e-12 |
| S2 leaves the Light RUC classes unchanged | 0.0 |
| S4 matches `load_dashboard_frame` on 5 series | 0.0 |
| Matrix cell P1/L0 reproduces the S5 front end | 0.0 |
| Signed gap decomposition closes | 0.0 |

Default state recorded in `front_end_default_state.csv`: bridge `raw_model`,
uptake `MoT VFM base`, sensitivities Off/Off/Off, FED policy `delayed_6m`
(the app's own default), FED path "Current planned path".

**Which stage Workstream A decomposed: S1.** It read the stored pack's post-λ
annual spine, so it explained the stored pack's −8.70% FY2030 gap, not the
−6.46% actually displayed. That finding is reconfirmed.

---

## 3. PED — one displacement, not two

| FY | S0 raw | S1 pack (λ) | S2 raw bridge | S3 macro | S4 VFM | surviving λ effect | VFM factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 32943.024 | 31742.115 | 32943.024 | 32947.572 | 32652.383 | **0.0** | 0.991 |
| 2028 | 32150.163 | 30295.920 | 32150.163 | 32372.423 | 31350.174 | **0.0** | 0.968 |
| 2030 | 32439.900 | 29787.438 | 32439.900 | 32982.422 | 30940.960 | **0.0** | 0.938 |

The raw bridge restores the raw level exactly, and the surviving λ PED effect
is exactly zero in every year. **PED is not double-counted in the
decision-facing view.** My previous claim is withdrawn.

The λ PED deduction exists in the stored pack and nowhere downstream of it.
That is the architecture working as designed.

What remains open is a single-overlay question: whether the VFM retention
curve adds prospective information or duplicates electrification already
implicit in the AR(1) path. That needs its own falsification test and is not a
λ question.

---

## 4. Light RUC — λ still controls the decision-facing pool

| FY | S0 raw model | S1 | S2 | S3 | S4 | S5 | S5 − raw | S5 pool |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 12968.092 | 12352.558 | 12352.558 | 12338.415 | 12208.402 | 12208.402 | −759.690 | 14154.458 |
| 2028 | 13372.424 | 12336.184 | 12336.184 | 12497.243 | 12416.408 | 12416.408 | −956.016 | 15412.818 |
| 2030 | 14129.751 | 12519.462 | 12519.462 | 12909.794 | 12738.719 | 12738.719 | **−1391.032** | 17261.942 |

**No supported runtime step restores the raw conventional Light RUC forecast.**
The raw bridge explicitly leaves the Light RUC classes untouched (delta 0.0),
and the VFM overlay preserves the incoming pool level and only re-splits it.
So the decision-facing conventional line stays λ-reduced and the pool stays
λ-inflated all the way to the front end.

This is the finding that survives the correction intact, and it is now the
whole of the structural case.

---

## 5. Corrected 2×2 matrix and signed attribution

Factor P: P0 = raw bridge, no VFM retention; P1 = raw bridge + one retention.
Factor L: L0 = current λ-created pool; L1 = raw model preserved as
conventional, pool = conventional / VFM Base conventional share.

All four cells run inside the same macro, policy, rate and fixed-line
environment; effective rates are derived from S5 so P1/L0 reproduces the front
end by construction. FY2030:

| cell | light petrol VKT | conventional | pool | gross PED | total NLTF | gap vs MBU26 |
|---|---:|---:|---:|---:|---:|---:|
| P0/L0 | 32982.422 | 12738.719 | 17261.942 | 2715.430 | 6187.096 | −3.84% |
| P0/L1 | 32982.422 | 14570.289 | 19892.619 | 2715.430 | 6409.596 | **−0.39%** |
| **P1/L0** (front end) | 30940.960 | 12738.719 | 17261.942 | 2547.357 | **6019.023** | **−6.46%** |
| P1/L1 | 30940.960 | 14570.289 | 19892.619 | 2547.357 | 6241.523 | −3.00% |

Signed contributions to the **true** displayed gap. Each is the amount by which
that treatment moves the final value, so a term that widens a negative gap
reads negative. Closure residual is 0.0 in every year.

| FY | final gap | PED VFM retention | Light pool λ effect | interaction | residual clean-architecture gap |
|---|---:|---:|---:|---:|---:|
| 2026 | −5.73 | −19.13 | −48.26 | 0.00 | +61.66 |
| 2027 | −498.56 | −39.66 | −53.93 | 0.00 | −404.97 |
| 2028 | −221.99 | −77.62 | −104.39 | 0.00 | −39.99 |
| 2029 | −304.89 | −118.79 | −157.26 | 0.00 | −28.85 |
| 2030 | **−415.35** | **−168.07** | **−222.50** | 0.00 | **−24.77** |

At FY2030 the Light RUC λ pool effect is the single largest term (−222.50,
53.6% of the gap), the VFM PED retention is −168.07 (40.5%), and everything
else — underlying econometrics, macro and fixed lines — accounts for only
−24.77 (6.0%).

Two caveats on reading this table:

- **FY2027 is dominated by policy, not modelling.** The −404.97 residual is the
  `delayed_6m` FED uplift, which is the app's default policy state and a
  deliberate choice, not a defect. FY2027 should not be read as a model gap.
- **The zero interaction is structural, not empirical.** PED and Light RUC
  enter separate linear revenue lines at fixed rates, so the cross term is zero
  by construction. It is not evidence about the model.

---

## 6. Structural diagnostic (corroborating, not a selection criterion)

No variant is chosen because it is closer to MBU26.

The raw Light RUC econometric forecast sits within about 2% of MBU26's
conventional line throughout FY2026–FY2030, and expanding it by the VFM Base
conventional share gives a pool within about 2.2% of the official pool. Raw
light-petrol VKT is within 1.31% of MBU26 by FY2030. The econometric forecasts
track the official activity paths closely; the divergence is introduced
downstream.

---

## 7. Provisional verdict

**1. Does λ change the level supplied to the final VFM overlay?**
Yes for Light RUC, no for PED. λ sets the conventional Light RUC line and the
pool level that the VFM overlay preserves and re-splits, and nothing restores
the raw forecast. On PED, the raw bridge discards λ's deduction entirely before
the overlay runs. λ must not be described as lineage-only, but its only
*decision-facing* effect is on Light RUC.

**2. Should the raw Light RUC model be treated as the conventional anchor?**
Yes, on semantic grounds. The target is conventional-only (Phase 2: residual
exactly 0.0 in every year, with the FY2024 definition break confirming it), so a
conventional-only forecast is a conventional anchor. The pipeline instead treats
it as one of two inputs to a universe whose shares come from a universe that
includes EV kilometres, and then reduces it.

**3. Is PED double-counted in S5?** No. Withdrawn.

**4. Does λ still control the Light RUC pool in S5?** Yes, entirely.

**5. Is P1/L1 still the preferred candidate?** Partly. **L1 is well supported** —
it preserves what the model estimates and gives the VFM machinery one job,
composition. **The choice between P0 and P1 is not settled** by this checkpoint:
it turns on whether the VFM petrol retention duplicates electrification already
in the AR(1) path, which is a separate falsification test. My provisional lean
is P1/L1, because one prospective retention overlay on a raw anchor is
coherent, but I would not commit to P1 without that test.

### What is not settled

- Whether the VFM PED retention duplicates the AR(1) trend. Needs its own test.
- Whether MBU26 applies an equivalent deduction. Not re-opened, per instruction.
- `_light_ruc_feature_frame` raises `InvalidIndexError` on scenario-input future
  rows. Separate technical defect; blocked nothing here.

No production change has been made and no PR has been opened.

---

## 8. Artifacts

Corrected runtime path:

| file | contents |
|---|---|
| `corrected_runtime_stage_waterfall.csv` | S0–S5 for every activity and revenue series |
| `corrected_ped_stage_layering.csv` | raw → λ → bridge → macro → VFM, with surviving λ effect |
| `corrected_light_ruc_stage_trace.csv` | conventional and pool at each stage vs the raw model |
| `corrected_structural_matrix_2x2.csv` | P0/P1 × L0/L1, FY2026–FY2030 |
| `corrected_signed_gap_attribution.csv` | signed contributions, closure residual 0.0 |
| `corrected_runtime_parity_gates.csv` | the nine parity gates |
| `front_end_default_state.csv` | the default selector and policy states used |
| `s5_front_end_rows.csv` | the decision-facing values |

Stored-pack mechanics (first pass, still valid for §1):

| file | contents |
|---|---|
| `runtime_stage_waterfall.csv` | S0→S1 λ transfer and universe construction |
| `structural_variant_results_fy.csv` | stored-pack variant matrix |
| `conservation_audit.csv`, `revenue_identity_audit.csv` | closure checks |
| `checkpoint_2_hard_gates.csv` | the sixteen stored-pack gates |
| `compact_falsification_metrics.csv` | structural diagnostic percentages |

Superseded, retained only as the correction record:
`ped_displacement_layering.csv`, `reference_a_vs_stored_pack.csv`,
`reference_a_front_end_with_vfm_overlay.csv`, `fy_gap_attribution.csv`.
