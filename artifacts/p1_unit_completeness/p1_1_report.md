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
- Completeness: 5247 cells, 5229 available (99.7%), 0 fail-closed findings.
- Fault injection: 20 mutations of the real promoted frame; 20 failed closed with the expected status.

Coverage is reported per class rather than as one aggregate, because a
single headline percentage hides which class is thin. See
`completeness_coverage_by_class.csv`.

| class | cells | available | not applicable | withheld | fail-closed | coverage |
|---|---|---|---|---|---|---|
| hidden_source_leaf | 225 | 225 | 0 | 0 | 0 | 100.00% |
| official_comparator | 3060 | 3060 | 0 | 0 | 0 | 100.00% |
| official_quarterly_not_supplied | 18 | 0 | 18 | 0 | 0 | 0.00% |
| required_annual_current | 1224 | 1224 | 0 | 0 | 0 | 100.00% |
| required_quarterly_current | 720 | 720 | 0 | 0 | 0 | 100.00% |

## The expected inventory is governed, not observed

The first revision built its role/series inventory from the rows present in
the frame being checked. That is self-masking: a series that disappears
entirely also disappears from the expected set, so the engine stops
expecting it and reports `not_applicable` - the most serious failure
presenting as the most benign status. Removing one row was tested; removing
the whole family was not detectable.

`model_dashboard/series_inventory_contract.py` now defines the expected set
as a static literal, resolved to `governed_series_inventory.csv` and pinned
to the code by test. It reads no pack.

The quarterly km declaration is stage-dependent and legitimately so: the
composition overlay between S1 and S2 divides quarterly km by 1e6 and
relabels in the same step (3_791_499_897 net km -> 3_791.4999 million km).
That is the unit contract working, not a defect. The annual-only matrix
could not see it; the contract now names the conversion boundary.

## Enforced at a production boundary

The validator is called as a blocking gate in two places, not only by this
generator: before the pack is written in
`build_current_revenue_outlook_runtime_pack`, and at
`load_revenue_outlook_pack`. Callers reach the load through
`cached_load_revenue_outlook_pack`, which is keyed on the pack signature,
so validation costs once per pack rather than once per Streamlit rerun.

`test_production_completeness_boundary.py` re-stamps the manifest hashes
after damaging a pack, so the pack passes every integrity check and is
still missing a required row. The completeness gate is what stops it.

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

- 67 governed pack CSVs compared against the branch point: max absolute delta 0.0. P1.1 is value-neutral.

## Routed to P1.2

- The post-macro PED cross-row inconsistency described above.
