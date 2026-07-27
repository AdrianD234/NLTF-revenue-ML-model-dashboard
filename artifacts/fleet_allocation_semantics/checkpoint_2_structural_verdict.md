# Checkpoint 2 — structural verdict

Branch `investigation/p0-fleet-allocation-semantics`. Investigation only: no
production code, governed pack, checkpoint or dashboard value was changed.

Regenerate with:

    .venv\Scripts\python.exe scripts\checkpoint2_structural_variants.py

All 16 hard gates pass. Every number below is reproduced by that script from
committed, replay-verified sources.

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

## 2. Hard gates

| gate | result |
|---|---|
| S5 reproduces the decision-facing front end exactly | pass — Variant B matches the stored pack on all 7 series, max delta 8.2e-12 |
| Identify which stage Workstream A decomposed | **S1** (the stored pack, post-λ). Workstream A read `light_ruc_net_km` and `light_petrol_vkt`, i.e. λ-adjusted levels, and attributed their MBU26 shortfall to population/migration/econometrics. It never saw S0. |
| Does λ change a decision-facing LEVEL? | **Yes.** λ sets `light_ruc_net_km` and `light_petrol_vkt`, both `bridge_input` rows that feed revenue. The raw model output is tagged `audit_only`. |
| Is λ lineage-only if VFM replaces its shares? | **No.** The VFM overlay preserves the λ-created pool *exactly* — gate `vfm_overlay_preserves_the_lambda_created_pool_level`, max delta 1.8e-12. S4 and S5 inherit a level λ created. |

Remaining gates (all pass, tolerance 1e-6): raw conventional preserved in C
and E (0.0); PED level matches each variant's definition (0.0); Variant C
removes exactly the λ PED transfer (1.8e-12); physical class sums close (0.0);
FY2025 actual classes unchanged across variants (0.0); revenue identity closes
(1.8e-12).

---

## 3. Variant matrix

Rates, litres intensity, refunds, admin, Heavy RUC, MVR, TUC, LPG and CNG are
identical in every variant and taken from the official spine. Only the four
light activity levels differ. FY2030:

| variant | light petrol VKT | conventional | pool | gross PED | total RUC | total NLTF | gap vs MBU26 |
|---|---:|---:|---:|---:|---:|---:|---:|
| B stored pack | 29787.438 | 12519.462 | 16782.212 | 2452.388 | 2983.813 | 5874.475 | −8.70% |
| C semantic clean anchor | 32439.900 | 14129.751 | 19291.158 | 2670.764 | 3195.253 | 6304.290 | **−2.02%** |
| D isolate PED | 32439.900 | 12519.462 | 16782.212 | 2670.764 | 2983.813 | 6092.851 | −5.31% |
| E isolate Light RUC | 29787.438 | 14129.751 | 19291.158 | 2452.388 | 3195.253 | 6085.914 | −5.42% |

Reference A (the actual front end, stored pack plus the default `MoT VFM base`
overlay) is *below* B, because the overlay adds a further PED reduction:
FY2030 total NLTF 5721.97, −11.07% vs MBU26.

---

## 4. Gap attribution

PED and Light RUC feed separate revenue lines at fixed rates, so the
decomposition is exactly additive — the measured interaction term is 0.00 in
every year. Total NLTF, $m vs MBU26:

| FY | total gap | PED post-model | Light RUC post-model | underlying econometrics + other |
|---|---:|---:|---:|---:|
| 2026 | −61.68 | 77.81 | 47.01 | +63.14 |
| 2027 | −229.43 | 102.88 | 61.36 | −65.19 |
| 2028 | −322.29 | 140.79 | 101.53 | −79.97 |
| 2029 | −430.41 | 179.24 | 151.23 | −99.95 |
| 2030 | **−559.89** | **218.38** | **211.44** | **−130.08** |

At FY2030: 39.0% of the gap is the PED post-model reduction, 37.8% the Light
RUC post-model allocation, and 23.2% everything else including the underlying
econometrics. **Roughly three quarters of the FY2030 shortfall is created
after the model stage.**

---

## 5. PED: petrol activity is displaced twice

Gross PED revenue, $m, and distance from MBU26:

| FY | L0 raw model | L1 after λ | L2 after VFM overlay | MBU26 | L0 % | L1 % | L2 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 2134.60 | 2056.78 | 2038.36 | 2062.78 | +3.48 | −0.29 | −1.18 |
| 2027 | 2206.07 | 2103.19 | 2062.35 | 2200.88 | +0.24 | −4.44 | −6.29 |
| 2028 | 2441.12 | 2300.33 | 2227.69 | 2456.03 | −0.61 | −6.34 | −9.30 |
| 2029 | 2570.62 | 2391.38 | 2282.19 | 2596.02 | −0.98 | −7.88 | −12.09 |
| 2030 | 2670.76 | 2452.39 | 2300.60 | 2706.16 | −1.31 | −9.38 | −14.99 |

L1 → L2 is `ped_retention_curve`, a prospective logistic displacement of
petrol activity to electric vehicles, normalised to 1.0 at FY2025. L0 → L1 is
`(1−λ)·M`, also a prospective displacement of petrol activity to electric
vehicles. They are applied sequentially to the same base.

This is now direct evidence for the double-count hypothesis rather than
suspicion. I flagged previously that the VFM retention curve being normalised
to FY2025 and prospective might make it a legitimate standalone overlay — that
remains true *in isolation*, but it is not applied in isolation. It is applied
on top of a base from which the same displacement has already been subtracted.

Falsification note: this is not proved by MBU26 proximity. The evidence is
that the two deductions have the same economic content (petrol VKT lost to
EVs), the same sign, the same prospective phasing, and no offsetting term
anywhere in the chain. The MBU26 comparison is corroborating, not the test.

---

## 6. Structural diagnostic (corroborating, not a selection criterion)

Per your instruction this is descriptive only. No variant is chosen because it
is closer to MBU26.

| FY | raw model vs MBU26 conventional | pack conventional vs MBU26 | conventional-anchor pool vs MBU26 pool | pack pool vs MBU26 pool |
|---|---:|---:|---:|---:|
| 2026 | +0.53% | −4.24% | +0.93% | −3.89% |
| 2027 | −1.87% | −8.08% | −2.16% | −7.67% |
| 2028 | −0.41% | −8.13% | −0.07% | −7.89% |
| 2029 | −0.67% | −10.09% | +0.64% | −9.75% |
| 2030 | −1.89% | −13.07% | +0.66% | −12.44% |

The raw Light RUC econometric forecast is within about 2% of MBU26's
conventional Light RUC line throughout. Expanding it by the VFM Base
conventional share gives a total pool within about 2.2% of the official pool
across FY2026–FY2030 and within 1% at both endpoints. Raw light-petrol VKT is
likewise within 1.31% of MBU26 by FY2030.

The econometric forecasts are close to the official activity paths. The
divergence is introduced downstream.

---

## 7. Provisional verdict

**1. Does λ change the level supplied to the final VFM overlay?**
Yes, decisively. λ sets both decision-facing activity levels, and the VFM
overlay preserves the λ-created pool to 1.8e-12 while re-splitting it. λ must
not be described as lineage-only.

**2. Should the raw Light RUC model be treated as the conventional anchor?**
On the evidence, yes — and this is a semantic argument, not a fit argument.
The Light RUC model's target is conventional-only (established decisively in
Phase 2: residual exactly 0.0 million km in every year, with the FY2024
definition break confirming it). A conventional-only forecast is a
conventional anchor. The present pipeline instead treats it as one of two
inputs to a universe and then reduces it. Variant C's method — preserve the
raw forecast as conventional, infer BEV and PHEV by expanding through
independently sourced VFM Base shares — is the interpretation consistent with
what the model estimates. It is also the method you correctly defended as
legitimate when you rejected my broader claim.

**3. FY2030 gap attribution.** PED post-model reduction 218.38 (39.0%), Light
RUC post-model allocation 211.44 (37.8%), underlying econometrics and all
other lines −130.08 (23.2%). Additive, interaction exactly zero.

**Layering verdict.** The PED stream carries two sequential prospective
displacements of petrol activity to EVs with no offset. This is a
double-count on the evidence available. The Light RUC stream carries one
allocation, but it is an allocation that lowers the conventional line below
the model output and inflates the pool by the PED-side deduction.

### What is not yet settled

- Whether the correct fix is to drop the λ transfer, drop the VFM PED
  retention, or reconcile them into a single displacement term. That is a
  design decision for Checkpoint 3, not a finding.
- Whether MBU26 itself applies any equivalent deduction. I have not
  re-opened the search for unpublished MBU26 drivers, per your instruction.
- `_light_ruc_feature_frame` raises `InvalidIndexError: Reindexing only valid
  with uniquely valued Index objects` when passed scenario-input future rows.
  Logged as a separate technical defect. It did not block this checkpoint and
  the public replay path was not needed either, since the committed replay
  artifacts already carry the raw forecast.

No production change has been made and no PR has been opened.

---

## 8. Artifacts

| file | contents |
|---|---|
| `runtime_stage_waterfall.csv` | S0→S1 levels, λ, migration total, both transfers, universe construction |
| `structural_variant_definitions.csv` | PED and Light RUC treatment per variant |
| `structural_variant_results_fy.csv` | FY2025–FY2030 activity and revenue lines, all variants, MBU26 gap |
| `reference_a_vs_stored_pack.csv` | S4 overlay vs S1 pack; pool preservation |
| `ped_displacement_layering.csv` | L0 raw → L1 λ → L2 VFM, per FY |
| `fy_gap_attribution.csv` | additive decomposition with interaction term |
| `conservation_audit.csv` | class sums and pool-minus-raw per variant per FY |
| `revenue_identity_audit.csv` | total NLTF recomputed from components |
| `checkpoint_2_hard_gates.csv` | all 16 gates with deltas and tolerances |
| `compact_falsification_metrics.csv` | structural diagnostic percentages |
| `actual_anchor_and_continuity.csv` | FY2025 anchor and FY2025→FY2026 step |
