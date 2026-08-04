# The overlay identity wedge — root cause and resolution (CASE 1)

Resolves the stop condition recorded in `stop_condition_identity_wedge.md`,
which is retained as historical evidence. Evidence here:
`overlay_wedge_stage_decomposition.csv`, `overlay_identity_wedge_audit.csv`,
`quarterly_annual_reconciliation.csv`.

## The first identity-breaking stage, named exactly

    model_dashboard/fuel_price_scenario.py
    apply_treasury_macro_to_chart_rows

Factors come from `DirectTreasuryScenarioReplayResult.baseline_macro_annual_factors`,
which publishes a **separate factor per series**:

| FY2030 factor | value |
|---|---|
| `light_petrol_vkt` | 1.014896 |
| `ped_vkt_per_capita` | 1.000916 |
| ratio | **1.013967** |
| measured Treasury ÷ legacy population | **1.013970** |
| residual | −3e-6 |

The ratio of the two published factors **is** the Treasury-versus-legacy
population ratio. Confirmed for both engines and both governed scenarios, with
a systematic residual of −3e-6 (a quarterly-sum versus VKT-weighted-mean
population difference, not a methodological gap).

## Why this is not a defect

The replay is internally consistent. For a total and its per-capita rate,

    factor(total) = factor(per_capita) × factor(population)

and that is exactly what the two published factors satisfy. The macro replay
restates the population path — its docstring says it makes the replayed path
"authoritative for every current model population path" — so **the
`scenario_inputs/scenario_input_wide` population is the LEGACY, pre-replay
path.** Testing the PED identity against it fails by precisely the restatement
ratio. The identity was never broken; it was being evaluated against the wrong
population.

Nothing here is an "effective population" fiction. The quantity is named,
governed, committed replay output.

## Why the wedge is flat after FY2030

`baseline_macro_annual_factors` covers **FY2025–FY2030 only**, and the overlay
carries the terminal FY2030 factor forward unchanged. Measured multipliers are
identical at FY2030, FY2031, FY2032 and FY2050 (petrol ×1.014896, VKT per
capita ×1.000916). That is why the ratio ramps to 1.013967 across the
econometric window and then holds for twenty years. The true Treasury ÷ legacy
population ratio continues rising to 1.015423 by FY2050, so the published
long-run rows embed the FY2030 restatement rather than a year-specific one.

That frozen-factor behaviour is pre-existing and applies to the whole Revenue
Outlook, not to this branch. It is recorded here as a separate observation for
the overlay owner; correcting it would move `light_petrol_vkt` and is therefore
outside the authority granted for this work.

## Resolution implemented

The governed population is recovered from the governed annual pair:

    population_factor_fy = target_petrol_fy
                         / sum_q(vktpc_q × legacy_pop_q / 1e6)
    governed_pop_q       = legacy_pop_q × population_factor_fy

Recovering it from the annual pair rather than re-reading the replay keeps it
correct under **every** policy, conflict, lever and vintage combination — the
factor is whatever the published annuals imply — while the audit reconciles it
back to the replay's own factors. A factor drifting more than 10% from the
legacy population is refused as no longer a population restatement.

Consequences:

- VKT per capita absorbs its own annual benchmark on the raw shape; native
  quarters are held and the free quarters take the residual in raw proportion.
- The ill-conditioned 2×2 seam solve is **gone**. Population no longer
  over-constrains the system, so the seam year needs no matrix solve at all.
- The per-quarter identity holds exactly against the governed population.
- Provenance on every derived row names the factor and its source.

## Verified outcome

End to end through the real pipeline, both engines:

| series | annual | quarterly |
|---|---|---|
| `ped_vkt_per_capita` | FY2025–FY2050 | **2026Q1–2050Q2** (98) |
| `light_petrol_vkt` | FY2026–FY2050 | **2025Q3–2050Q2** (100) |

- Quarterly→annual reconciliation: 98 year/series/engine combinations, worst
  relative residual **3.5e-16**.
- Publication helper is strictly additive: 2673 pre-existing rows compared,
  **0 changed**, max absolute change **0.0**; 40 rows added, all
  `light_petrol_vkt` june_year.
- `ped_vkt_per_capita` annual, `ped_volume`, PED revenues, Actual history and
  official comparators are provably unchanged.
- No annual value moved, so the owner's authorised exception permitting
  decision-facing `ped_vkt_per_capita` to move was **not needed and not used**.

## Case classification

**CASE 1.** The wedge matches a real, named, governed source. No overlay
semantics defect, no series renaming, and no recalculation of any
decision-facing annual value was required.
