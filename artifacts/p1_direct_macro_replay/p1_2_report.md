# P1.2 - direct Treasury macro replay for every governed scenario

## The defect

`apply_treasury_macro_to_chart_rows` historically applied a BASE-derived
Treasury factor to Base and comparison traces alike, to preserve their
differential. That is exact only for models linear in the changed inputs.
The current comparison carries its own population AND GDP paths, and the
PED model is recursive while Heavy RUC is a GBM ensemble, so the
transferred factor misstates the comparison.

Measured transfer error on current_comparison_1: quarterly PED VKTpc up to 0.287%, annual series up to 0.074%.

## The construction

The adjustment moved to INPUT space, where it is exact by construction:
per-period ratios derived from the vetted Base transform
(`gdp_ratio = treasury_base / legacy_base`, likewise population) are
applied to each scenario's own macro columns, preserving every scenario
differential bit-for-bit; the fixed promoted models are then replayed per
scenario against that scenario's own legacy shadow. Factors are keyed
(scenario, series, period) and the overlay fails closed on: a legacy
Base-pair result over non-Base rows, a missing factor for a targeted row,
and a non-numeric targeted value. `Base bit-for-bit` and
`differential preserved` are asserted by test, not assumed.

## Parity: where factor transfer was right and where it was not

- 324 audited cells across 2 scenarios; Base parity exact by construction; current_comparison_1: 119 of 162 cells outside the 1e-09 tolerance - those are the corrected cells.

The audit compares, for every scenario/series/period the old path
touched: the value produced by transferring the Base factor onto the
committed skeleton, against the value produced by the scenario's own
direct replay. Cells within the governed tolerance prove the old cache
was harmless THERE; cells outside it are exactly the correction this
change ships. Direct replay is authoritative everywhere either way.

| series | cells | transfer wrong | worst rel dev | worst value delta |
|---|---|---|---|---|
| ped_vkt_per_capita | 26 | 25 | 2.87e-03 | 4.4737 |
| net_fed_revenue | 6 | 5 | 7.35e-04 | 1.6548 |
| ped_volume | 6 | 5 | 7.22e-04 | 2.1770 |
| gross_ped_revenue | 6 | 5 | 7.22e-04 | 1.6542 |
| gross_fed_revenue | 6 | 5 | 7.09e-04 | 1.6535 |
| total_fed_ruc_net_revenue | 6 | 5 | 3.63e-04 | 1.6435 |
| total_nltf_net_revenue | 6 | 5 | 3.25e-04 | 1.6394 |
| total_ruc_net_revenue | 6 | 5 | 1.22e-04 | 0.4025 |
| heavy_ruc_net_km | 26 | 24 | 3.85e-05 | 41404.0929 |
| heavy_ruc_net_revenue | 6 | 5 | 3.27e-05 | 0.0485 |
| phev_ruc_net_km | 6 | 5 | 5.27e-06 | 0.0061 |
| light_ruc_net_km | 26 | 5 | 5.27e-06 | 0.0674 |
| light_bev_ruc_net_km | 6 | 5 | 5.27e-06 | 0.0112 |
| phev_ruc_net_revenue | 6 | 5 | 5.27e-06 | 0.0003 |
| light_bev_ruc_net_revenue | 6 | 5 | 5.27e-06 | 0.0010 |
| light_ruc_net_revenue | 6 | 5 | 5.27e-06 | 0.0049 |
| net_mvr_revenue | 6 | 0 | 0.00e+00 | 0.0000 |

## Revenue impact

- current_comparison_1 total NLTF net revenue correction: worst 1.639m (0.0325%) across FY2026-FY2030.

The committed pack skeleton is pre-macro, so no committed value changes;
the correction lands in the runtime display layer for non-Base scenarios.

## PED cross-row identity - resolved at the macro layer

Under the authoritative construction (each stage's own VKTpc against that
stage's governed population; Treasury-adjusted per scenario after the
macro overlay) the identity closes at machine precision at S0-S3 for both
governed scenarios and at S4 for Base - see
`p1_unit_completeness/ped_cross_row_identity.csv`. The 1.706% pinned by
P1.1 was the expected side being held at the pre-macro population: a
measurement-construction artifact, not a production defect. A deliberate
power check keeps the measurement honest: S1 against the LEGACY
population must show >= 0.5% residual.

One enumerated exception remains, one layer up from the macro overlay:
the FED policy pair factors are Base-derived and transferred onto the
comparison at S4 - the same defect class, 570x smaller (0.000502% on
comparison petrol VKT at FY2027 under the delayed policy). Pinned as
`policy_pair_transfer_on_comparison_pending_followup` with a 1e-3%
ceiling, confined to S4/comparison by gate, and routed to the
policy-layer follow-up (per-scenario policy variant replay).

## Determinism

- Two full replays produced bit-identical factor frames.

## Fail-closed inventory

- legacy Base-pair result over a frame containing non-Base current rows;
- any targeted row with no factor for ITS scenario (the silent `continue`
  that retained the legacy value is gone);
- non-numeric value on a targeted row;
- a scenario missing streams, input rows, or factor-grid cells vs Base;
- replay rows failing the complete-numeric validation.

## Scope

MBU26 official rows, historical actuals and the runtime conflict/policy
layers are untouched. Conflict and policy scenarios were already direct
replays of Treasury-adjusted Base inputs and keep their own pair-factor
mechanism.
