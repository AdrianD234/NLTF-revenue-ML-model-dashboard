# MBU26 reconciliation census (Workstream A, Phase A1)

Engine: AR(1), the authoritative production engine. Base case,
FY2026-FY2030. Read-only: no model, pack or checkpoint was altered.

## The headline difference

Total NLTF net revenue, current model minus MBU26 official:

| june_year | value_current | value_mbu26 | absolute_difference | percent_difference |
|---|---|---|---|---|
| 2026 | 4,501.47 | 4,563.15 | -61.68 | -1.35 |
| 2027 | 4,778.85 | 5,008.28 | -229.43 | -4.58 |
| 2028 | 5,316.85 | 5,639.13 | -322.29 | -5.72 |
| 2029 | 5,629.42 | 6,059.83 | -430.41 | -7.10 |
| 2030 | 5,874.47 | 6,434.37 | -559.89 | -8.70 |

## Where the difference sits

| series_id | fy2026_diff | max_abs_diff | max_abs_pct |
|---|---|---|---|
| net_fed_revenue | -6.00 | 253.78 | 9.59 |
| net_mvr_revenue | -0.00 | 0.00 | 0.00 |
| total_nltf_net_revenue | -61.68 | 559.89 | 8.70 |
| total_ruc_net_revenue | -55.68 | 306.12 | 9.30 |

## Driver availability - the finding that governs everything else

Of 14 driver families, **6 are reproducible** for a
common-input counterfactual and the rest are not.

| driver | streams_affected | current_model_source | mbu26_source | mbu26_vintage_reproducible |
|---|---|---|---|---|
| real GDP | PED / Light RUC / Heavy RUC | Treasury BEFU26 overlay (committed CSV) | not published in the MBU26 source pack | no |
| population | PED (per-capita denominator) | Treasury BEFU26 June anchors, log-linear interpolation | not published in the MBU26 source pack | no |
| unemployment rate | PED | scenario input workbook | not published in the MBU26 source pack | no |
| real petrol price | PED | scenario input workbook | not published in the MBU26 source pack | no |
| real diesel price | Light RUC | scenario input workbook | not published in the MBU26 source pack | no |
| real Light RUC price | Light RUC | scenario input workbook | not published in the MBU26 source pack | no |
| real Heavy RUC price | Heavy RUC | scenario input workbook | not published in the MBU26 source pack | no |
| PED effective rate | PED revenue bridge | inherited from MBU26 | MBU26 official annual (revenue / volume) | yes |
| class RUC effective rates | Light/Heavy RUC revenue bridge | inherited from MBU26 | MBU26 official annual (revenue / km) | yes |
| fuel intensity (litres per km) | PED volume bridge | inherited from MBU26 | MBU26 official annual (litres / VKT) | yes |
| EV/PHEV class allocation | Light RUC class mix | MoT VFM 202405 uptake levers | MBU26 official class km rows | yes |
| refunds and admin | net revenue formulas | inherited from MBU26 | MBU26 official annual | yes |
| MVR / TUC / LPG / CNG | fixed revenue rows | inherited from MBU26 | MBU26 official annual | yes |
| judgemental adjustment | any | none applied | unknown; not disclosed in the workbook | no |

The reproducible ones are exactly those the current model already
**inherits** from MBU26: effective rates, fuel intensity, class allocation,
refunds, admin and the fixed revenue rows. They cannot explain any of the
difference, because both sides already use identical values for them.

Every driver that could actually move the two paths apart - GDP,
population, unemployment, petrol, diesel and RUC prices - is **not
published in the MBU26 source pack**. The workbook reports MBU26's
*outputs*, not the assumptions that produced them.

## What this means for the decomposition

65 of 85 series/FY cells cannot support a like-for-like
common-input counterfactual from committed content. The requested
counterfactual C - *current finalist under the fullest reproducible MBU26
driver vintage* - **cannot be constructed** for the drivers that matter.

That is a finding, not a failure to execute. It means the question
'would the current model still sit below MBU26 on identical drivers?'
cannot be answered from this repository as it stands. Answering it
requires MoT to supply the MBU26 driver assumptions, which are not in
the published workbook.

## Recommended next step

The decomposition should therefore be built in two explicitly separated
levels, as follows.

**Financial decomposition** - which activity and revenue lines account
for the dollar difference. This closes exactly and is fully computable
from committed content. It is the honest deliverable.

**Causal decomposition** - why MBU26 produced those quantities. This
must carry an explicit `unknown_official_model_inputs_or_judgment`
term. Attempting to attribute the gap to GDP or price assumptions we
cannot observe would be inventing the inputs.

Do not proceed to a Shapley driver decomposition over unavailable
drivers. Request the MBU26 driver vintage from MoT, or scope the
decomposition to the financial level and label the residual honestly.

## Series not available at June-year grain

`light_petrol_vkt` and `current_light_ruc_total_modelled_km` exist in
the MBU26 annual spine and the quarterly bridge but not in the
June-year chart rows for both scenarios, so they are absent from this
census. They are recoverable from the bridge if the financial
decomposition needs them.


---

# Phase A2 closeout: the financial decomposition

## Correction to the first pass

The first decomposition attributed 44% of the FY2030 gap to population. **That
was wrong.** It derived current population by inverting light-petrol VKT, which
folds the EV/PHEV migration allocation into the population term.

Taking current population from the scenario inputs and treating migration as
its own bridge term, with an order-neutral three-factor Shapley over
VKT per capita x population x migration:

| FY | VKT per capita | Population scaling | EV/PHEV migration |
|---|---:|---:|---:|
| 2026 | +71.11 | −1.20 | **−75.91** |
| 2027 | +15.28 | −10.17 | **−102.79** |
| 2028 | +1.15 | −15.60 | **−141.24** |
| 2029 | −3.36 | −21.14 | **−180.14** |
| 2030 | −7.32 | −26.61 | **−219.85** |

The FED-side gap is driven by **EV/PHEV migration allocation**, not population
and not driving behaviour. The current migration factor falls from 0.964 in
FY2026 to 0.918 in FY2030 against an official baseline of exactly 1: the
current path moves roughly 8% more light travel out of petrol and into
BEV/PHEV by FY2030 than MBU26's implied allocation.

VKT per capita is *positive* early (+71.1m in FY2026) and only turns negative
from FY2029. Population contributes at most −26.6m.

Caveat: official population is not published, so the official side is an
output-implied population with a migration factor of 1 by construction. The
migration term therefore carries whatever MBU26 folded into its own implied
population. It is an upper bound on the true allocation difference.

## RUC, sourced rather than differenced

| Component | FY2030 $m | Status |
|---|---:|---|
| conventional Light RUC | −169.38 | observable |
| Heavy RUC | −99.43 | observable |
| Light BEV RUC | −29.05 | observable |
| PHEV RUC | −7.87 | observable |
| Heavy BEV revenue | 0.00 | inherited from MBU26 |
| RUC administration | 0.00 | inherited from MBU26 |
| RUC refunds | 0.00 | cancels in the Total RUC identity |
| official formula/rounding residual | −0.38 | official workbook residual |

Refunds cancel algebraically: gross RUC includes them and
`ruc_revenue_net_admin − ruc_refunds` removes them. No gap is attributed to
them. The remaining −0.38m is named as an official workbook residual rather
than bundled into a difference-derived balancing term.

## Conclusion

**Financial.** The FY2026–FY2030 gap closes exactly through named observable
lines. Maximum closure residual 5.7e-13, inside the 1e-6 tolerance.

**Causal.** Partial. The EV/PHEV migration allocation, VKT per capita and
population scaling are observable and measured. MBU26's GDP, unemployment,
petrol, diesel and RUC-price assumptions remain unavailable and are recorded
as NA, never zero. Why MBU26 chose its fleet-electrification path is not
recoverable from the published workbook.

No model has been calibrated toward MBU26 at any point.
