# Official vintage reconciliation: PREBU26 (bridge: BEFU26)

Comparator vintage for cross-vintage deltas: BEFU26.
All artifact paths are repo-relative; published source values are surfaced,
never corrected.

## Checks

| Check | Status | Detail |
|---|---|---|
| pack_frames_loaded | PASS | PREBU26 and BEFU26 packs loaded and hash-validated by the governed loader |
| runtime_pack_bridge_vintage_ensemble | PASS | manifest bridge_assumption_vintage_id=BEFU26, requested=BEFU26 |
| runtime_pack_bridge_vintage_ar1 | PASS | manifest bridge_assumption_vintage_id=BEFU26, requested=BEFU26 |
| workbook_formula_count | PASS | 0 Excel formulas found (static published values expected) |
| annual_percentage_change_block | PASS | unit=fraction; 495 rows over FY2001-FY2055; 0 published rows differ from level-implied change beyond 1e-6 relative (published rounding; reported, not corrected) |
| official_annual_verbatim_copy | PASS | byte-identical to data/revenue_model_source_pack/official_vintages/prebu26/official_annual.csv |
| row_reconciliation_no_unexpected_residuals | PASS | 770 rows classified |
| formula_reconciliation_no_unexpected_residuals | PASS | 770 rows classified |
| effective_rate_audit_finite | PASS | all rates finite or NA (div-by-zero guarded) |
| class_share_sums_to_one | PASS | shares sum to 1 within 1e-9 where all classes present |
| composition_refresh_candidate_flagged | PASS | candidate deltas > 0.01 vs VFM Base exist (opt-in only; Current composition unchanged) |
| vintage_series_fy_key_parity | PASS | 2200 shared series/FY keys |
| published_actual_revisions_surfaced | PASS | light_petrol_vkt FY2003 +9.529231; light_petrol_vkt FY2004 +9.094052; light_petrol_vkt FY2005 +8.680932; light_petrol_vkt FY2006 +7.739596; light_petrol_vkt FY2007 +5.597786; light_petrol_vkt FY2008 +6.100505; light_petrol_vkt FY2009 +5.841869; light_petrol_vkt FY2010 +4.940246; light_petrol_vkt FY2011 +5.019666; light_petrol_vkt FY2012 +4.827431; light_petrol_vkt FY2013 +4.542638; light_petrol_vkt FY2014 +4.178790; light_petrol_vkt FY2015 +4.236206; light_petrol_vkt FY2016 +3.483143; light_petrol_vkt FY2017 +3.164339; light_petrol_vkt FY2018 +1.517933; light_petrol_vkt FY2019 -1.262440; light_petrol_vkt FY2020 -2.604217; light_petrol_vkt FY2021 -6.820052; light_petrol_vkt FY2022 -29.268854; light_petrol_vkt FY2023 -61.561368; light_petrol_vkt FY2024 +44.736686; light_petrol_vkt FY2025 +914.961376; ped_vkt_per_capita FY2003 +2.388958; ped_vkt_per_capita FY2004 +2.239535; ped_vkt_per_capita FY2005 +2.110848; ped_vkt_per_capita FY2006 +1.860977; ped_vkt_per_capita FY2007 +1.330536; ped_vkt_per_capita FY2008 +1.437435; ped_vkt_per_capita FY2009 +1.364817; ped_vkt_per_capita FY2010 +1.140723; ped_vkt_per_capita FY2011 +1.148456; ped_vkt_per_capita FY2012 +1.097429; ped_vkt_per_capita FY2013 +1.026917; ped_vkt_per_capita FY2014 +0.932339; ped_vkt_per_capita FY2015 +0.928069; ped_vkt_per_capita FY2016 +0.747115; ped_vkt_per_capita FY2017 +0.663805; ped_vkt_per_capita FY2018 +0.312862; ped_vkt_per_capita FY2019 -0.255078; ped_vkt_per_capita FY2020 -0.516550; ped_vkt_per_capita FY2021 -1.342174; ped_vkt_per_capita FY2022 -5.757963; ped_vkt_per_capita FY2023 -11.997720; ped_vkt_per_capita FY2024 +8.434789; ped_vkt_per_capita FY2025 +172.273745 |
| pinned_baseline_manifest_present | PASS | baseline bridge vintage BEFU26 at bf61160d86499a5d39d9dbef47e85a4b9b563d3d |
| pinned_baseline_ensemble | PASS | sha256 matches pinned manifest (impact computed against the pinned file, never a live regeneration) |
| pinned_baseline_ar1 | PASS | sha256 matches pinned manifest (impact computed against the pinned file, never a live regeneration) |
| bridge_impact_non_empty_both_engines | PASS | 1768 matched impact rows across ['ar1', 'ensemble'] |
| current_vs_official_gap_coverage | PASS | 400 rows: 8 streams x FY2026-2050 x 2 engines |
| decomposition_residual_closure | PASS | max \|residual\|: NLTF 4.80e-11, RUC 1.42e-12, FED 7.11e-12 (tolerance 1e-6) |
| decomposition_current_side_closes | PASS | max \|current RUC closure\| 3.64e-12 |
| decomposition_fixed_rows_reported | PASS | bridge vintage BEFU26 != official vintage PREBU26; fixed-row gaps reported (max 80.887542), not asserted zero |
| policy_basis_app_default_state | PASS | app default UI Current policy state is 'delayed_6m' |
| policy_basis_both_bases_present | PASS | bases: ['actual_default_ui', 'policy_normalised'] |
| front_end_selector_official_vintage_available | PASS | PREBU26 present in official_vintages.available for engines ['ar1', 'ensemble'] |
| artifacts_repo_relative_paths_only | PASS | no absolute user paths in any artifact |

## Published-source residuals (named, quantified, retained)

PREBU26 `gross_ruc_revenue` fails to close to its class leaves plus refunds (same defect family as the MBU26 FY2027 +0.627 residual). The published values are retained; nothing is force-balanced:

- FY2027: residual +0.619398 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2028: residual +0.472877 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2029: residual +0.368256 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2030: residual +0.389594 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2031: residual +0.431551 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)

## Published ACTUAL revisions vs the prior vintage

- light_petrol_vkt FY2003: PREBU26 - BEFU26 = +9.529231 (note `published_actual_revision`)
- light_petrol_vkt FY2004: PREBU26 - BEFU26 = +9.094052 (note `published_actual_revision`)
- light_petrol_vkt FY2005: PREBU26 - BEFU26 = +8.680932 (note `published_actual_revision`)
- light_petrol_vkt FY2006: PREBU26 - BEFU26 = +7.739596 (note `published_actual_revision`)
- light_petrol_vkt FY2007: PREBU26 - BEFU26 = +5.597786 (note `published_actual_revision`)
- light_petrol_vkt FY2008: PREBU26 - BEFU26 = +6.100505 (note `published_actual_revision`)
- light_petrol_vkt FY2009: PREBU26 - BEFU26 = +5.841869 (note `published_actual_revision`)
- light_petrol_vkt FY2010: PREBU26 - BEFU26 = +4.940246 (note `published_actual_revision`)
- light_petrol_vkt FY2011: PREBU26 - BEFU26 = +5.019666 (note `published_actual_revision`)
- light_petrol_vkt FY2012: PREBU26 - BEFU26 = +4.827431 (note `published_actual_revision`)
- light_petrol_vkt FY2013: PREBU26 - BEFU26 = +4.542638 (note `published_actual_revision`)
- light_petrol_vkt FY2014: PREBU26 - BEFU26 = +4.178790 (note `published_actual_revision`)
- light_petrol_vkt FY2015: PREBU26 - BEFU26 = +4.236206 (note `published_actual_revision`)
- light_petrol_vkt FY2016: PREBU26 - BEFU26 = +3.483143 (note `published_actual_revision`)
- light_petrol_vkt FY2017: PREBU26 - BEFU26 = +3.164339 (note `published_actual_revision`)
- light_petrol_vkt FY2018: PREBU26 - BEFU26 = +1.517933 (note `published_actual_revision`)
- light_petrol_vkt FY2019: PREBU26 - BEFU26 = -1.262440 (note `published_actual_revision`)
- light_petrol_vkt FY2020: PREBU26 - BEFU26 = -2.604217 (note `published_actual_revision`)
- light_petrol_vkt FY2021: PREBU26 - BEFU26 = -6.820052 (note `published_actual_revision`)
- light_petrol_vkt FY2022: PREBU26 - BEFU26 = -29.268854 (note `published_actual_revision`)
- light_petrol_vkt FY2023: PREBU26 - BEFU26 = -61.561368 (note `published_actual_revision`)
- light_petrol_vkt FY2024: PREBU26 - BEFU26 = +44.736686 (note `published_actual_revision`)
- light_petrol_vkt FY2025: PREBU26 - BEFU26 = +914.961376 (note `published_actual_revision`)
- ped_vkt_per_capita FY2003: PREBU26 - BEFU26 = +2.388958 (note `published_actual_revision`)
- ped_vkt_per_capita FY2004: PREBU26 - BEFU26 = +2.239535 (note `published_actual_revision`)
- ped_vkt_per_capita FY2005: PREBU26 - BEFU26 = +2.110848 (note `published_actual_revision`)
- ped_vkt_per_capita FY2006: PREBU26 - BEFU26 = +1.860977 (note `published_actual_revision`)
- ped_vkt_per_capita FY2007: PREBU26 - BEFU26 = +1.330536 (note `published_actual_revision`)
- ped_vkt_per_capita FY2008: PREBU26 - BEFU26 = +1.437435 (note `published_actual_revision`)
- ped_vkt_per_capita FY2009: PREBU26 - BEFU26 = +1.364817 (note `published_actual_revision`)
- ped_vkt_per_capita FY2010: PREBU26 - BEFU26 = +1.140723 (note `published_actual_revision`)
- ped_vkt_per_capita FY2011: PREBU26 - BEFU26 = +1.148456 (note `published_actual_revision`)
- ped_vkt_per_capita FY2012: PREBU26 - BEFU26 = +1.097429 (note `published_actual_revision`)
- ped_vkt_per_capita FY2013: PREBU26 - BEFU26 = +1.026917 (note `published_actual_revision`)
- ped_vkt_per_capita FY2014: PREBU26 - BEFU26 = +0.932339 (note `published_actual_revision`)
- ped_vkt_per_capita FY2015: PREBU26 - BEFU26 = +0.928069 (note `published_actual_revision`)
- ped_vkt_per_capita FY2016: PREBU26 - BEFU26 = +0.747115 (note `published_actual_revision`)
- ped_vkt_per_capita FY2017: PREBU26 - BEFU26 = +0.663805 (note `published_actual_revision`)
- ped_vkt_per_capita FY2018: PREBU26 - BEFU26 = +0.312862 (note `published_actual_revision`)
- ped_vkt_per_capita FY2019: PREBU26 - BEFU26 = -0.255078 (note `published_actual_revision`)
- ped_vkt_per_capita FY2020: PREBU26 - BEFU26 = -0.516550 (note `published_actual_revision`)
- ped_vkt_per_capita FY2021: PREBU26 - BEFU26 = -1.342174 (note `published_actual_revision`)
- ped_vkt_per_capita FY2022: PREBU26 - BEFU26 = -5.757963 (note `published_actual_revision`)
- ped_vkt_per_capita FY2023: PREBU26 - BEFU26 = -11.997720 (note `published_actual_revision`)
- ped_vkt_per_capita FY2024: PREBU26 - BEFU26 = +8.434789 (note `published_actual_revision`)
- ped_vkt_per_capita FY2025: PREBU26 - BEFU26 = +172.273745 (note `published_actual_revision`)

## Bridge-refresh impact headline (Current finalist Base case, Total NLTF)

- ar1: FY2026-2030 sum +0.000 $m; FY2031-2050 sum +0.000 $m (refreshed BEFU26 bridge minus pinned BEFU26-bridge baseline)
- ensemble: FY2026-2030 sum +0.000 $m; FY2031-2050 sum +0.000 $m (refreshed BEFU26 bridge minus pinned BEFU26-bridge baseline)

### Impact coverage

- ar1: 884 matched rows; 0 only in pinned baseline; 0 only in refreshed pack; 1020 baseline official-comparator rows excluded (comparator addition is not bridge impact)
- ensemble: 884 matched rows; 0 only in pinned baseline; 0 only in refreshed pack; 1020 baseline official-comparator rows excluded (comparator addition is not bridge impact)

## Composition-refresh candidate verdict

MATERIAL vs VFM Base in 19 FYs (2025-2046): max |share delta| 0.040992 exceeds 0.01. OPT-IN CANDIDATE ONLY: the Current model composition is unchanged pending separate approval.

## Scope notes

- The financial decomposition is a financial closure, not causal driver
  attribution: official GDP/unemployment/price/judgment inputs are not
  supplied (driver_availability_matrix.csv) and receive no fabricated dollars.
- The policy-basis comparison keeps `policy_normalised` and `actual_default_ui`
  separate; the official side is always the published vintage and
  delayed-vs-delayed is never constructed as the standard comparison.

Overall: PASS (25/25 checks passed).
