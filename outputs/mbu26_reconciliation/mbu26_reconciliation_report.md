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

