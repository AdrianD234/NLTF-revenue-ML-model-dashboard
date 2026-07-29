# P1.1 - unit, completeness and allocation contracts

## Permissive behaviours removed

1. **Magnitude-based unit inference.** Five production sites divided by 1e6
   whenever `abs(value) > 10_000_000`. Correct only while a series stays
   inside its expected range; a re-based or genuinely large series silently
   lost six orders of magnitude with no error.
2. **Substring-driven display scaling.** Three copies of `_display_unit_scale`
   matched the word million in the label and returned 1.0 for anything
   unrecognised, so a typo was indistinguishable from an already-unscaled unit.
3. **Undeclared internal frames.** The Treasury macro replay's shadow and
   display rows carried no units at all and only worked because the magnitude
   hack guessed for them.

## Production locations changed

- `model_dashboard/unit_contract.py` (new): registry, conversions, errors
- `model_dashboard/completeness_contract.py` (new): availability engine
- `model_dashboard/mbu26_source_spine.py`: annualisation, anchor, migration pool
- `model_dashboard/revenue_source_pack.py`: annualisation, anchor
- `model_dashboard/forecast_runner.py`: native unit declarations
- `model_dashboard/ev_uptake_levers.py`, `fuel_price_scenario.py`, `app.py`:
  registry-backed scaling

## Coverage

- Unit registry: 41 series, 40 aliases, 12 conversions.
- Unit coverage: 100% - every declared unit in both committed packs resolves.
- Completeness: 1575 cells, 1550 available (98.4%), 0 fail-closed findings.
- Mutation tests: 14 scenarios; 13 fail closed, the H21+ case stays withheld.

## PED cross-row identity

The governed identity is quarterly VKT-per-capita x quarterly population,
summed over the four fiscal quarters - not annual VKTpc x a mean population.

- Pre-macro (S0): closes at 2.21e-14%.
- Post-macro (S1-S4): diverges up to 1.706% (FY2030).

The Treasury macro replay applies stream-specific factors to
`light_petrol_vkt` and `ped_vkt_per_capita` independently, so their ratio
stops reproducing the governed population path. This is recorded as
`known_macro_cross_row_inconsistency_pending_p1_2` and is NOT repaired here:
P1.2 direct scenario replay determines the authoritative construction. It is
a named, enumerated exception, not a generally acceptable tolerance - the
ceiling is pinned and the first divergent stage is asserted to be S1, so it
cannot grow or migrate earlier unnoticed.

## FY2026 population lineage

FY2026 is NOT unavailable. Its four quarters resolve with mixed lineage:
2025Q3-Q4 from the governed MBU26 population proxy (the same fallback
production itself uses, recorded per row), 2026Q1-Q2 from scenario inputs.
Using a different historical source (Treasury's interpolated path) opened a
spurious 0.21% FY2026 gap, which is why the identity tests what production
actually did rather than a reconstruction.

## Residuals

- Allocation: worst 1.82e-12; nothing assigned to conventional activity.
- Current formulas close within 1e-6; official published-source residuals stay
  separately named and are never allocated to a current class.

## Production value stability

- 75 governed pack CSVs compared against the branch point: max absolute delta 0.0. P1.1 is value-neutral.

## Routed to P1.2

- The post-macro PED cross-row inconsistency described above.
