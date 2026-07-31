# Official vintage reconciliation: BEFU26 (bridge: BEFU26)

Comparator vintage for cross-vintage deltas: MBU26.
All artifact paths are repo-relative; published source values are surfaced,
never corrected.

## Checks

| Check | Status | Detail |
|---|---|---|
| pack_frames_loaded | PASS | BEFU26 and MBU26 packs loaded and hash-validated by the governed loader |
| runtime_pack_bridge_vintage_ensemble | PASS | manifest bridge_assumption_vintage_id=BEFU26, requested=BEFU26 |
| runtime_pack_bridge_vintage_ar1 | PASS | manifest bridge_assumption_vintage_id=BEFU26, requested=BEFU26 |
| workbook_formula_count | PASS | 0 Excel formulas found (static published values expected) |
| annual_percentage_change_block | PASS | unit=fraction; 495 rows over FY2001-FY2055; 0 published rows differ from level-implied change beyond 1e-6 relative (published rounding; reported, not corrected) |
| official_annual_verbatim_copy | PASS | byte-identical to data/revenue_model_source_pack/official_vintages/befu26/official_annual.csv |
| row_reconciliation_no_unexpected_residuals | PASS | 770 rows classified |
| formula_reconciliation_no_unexpected_residuals | PASS | 770 rows classified |
| effective_rate_audit_finite | PASS | all rates finite or NA (div-by-zero guarded) |
| class_share_sums_to_one | PASS | shares sum to 1 within 1e-9 where all classes present |
| composition_refresh_candidate_flagged | PASS | candidate deltas > 0.01 vs VFM Base exist (opt-in only; Current composition unchanged) |
| vintage_series_fy_key_parity | PASS | 2200 shared series/FY keys |
| published_actual_revisions_surfaced | PASS | light_petrol_vkt FY2025 -0.492090; ped_vkt_per_capita FY2025 -0.092884 |
| pinned_baseline_manifest_present | PASS | baseline bridge vintage MBU26 at 8d1a4304c1df1c983036971aa053e29f5c153cf0 |
| pinned_baseline_ensemble | PASS | sha256 matches pinned manifest (impact computed against the pinned file, never a live regeneration) |
| pinned_baseline_ar1 | PASS | sha256 matches pinned manifest (impact computed against the pinned file, never a live regeneration) |
| bridge_impact_non_empty_both_engines | PASS | 1768 matched impact rows across ['ar1', 'ensemble'] |
| current_vs_official_gap_coverage | PASS | 400 rows: 8 streams x FY2026-2050 x 2 engines |
| decomposition_residual_closure | PASS | max \|residual\|: NLTF 9.05e-11, RUC 1.82e-12, FED 8.64e-12 (tolerance 1e-6) |
| decomposition_current_side_closes | PASS | max \|current RUC closure\| 3.64e-12 |
| decomposition_fixed_rows_zero | PASS | max \|fixed/carried row gap\| 8.53e-13 (zero by construction: bridge vintage == official vintage == BEFU26) |
| policy_basis_app_default_state | PASS | app default UI Current policy state is 'delayed_6m' |
| policy_basis_both_bases_present | PASS | bases: ['actual_default_ui', 'policy_normalised'] |
| front_end_selector_official_vintage_available | PASS | BEFU26 present in official_vintages.available for engines ['ar1', 'ensemble'] |
| artifacts_repo_relative_paths_only | PASS | no absolute user paths in any artifact |

## Published-source residuals (named, quantified, retained)

BEFU26 `gross_ruc_revenue` fails to close to its class leaves plus refunds (same defect family as the MBU26 FY2027 +0.627 residual). The published values are retained; nothing is force-balanced:

- FY2027: residual +0.627012 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2028: residual +0.466274 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2029: residual +0.362901 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)
- FY2030: residual +0.383247 $m (gross_ruc_revenue, status residual_reported, classified published_source_residual)

## Published ACTUAL revisions vs the prior vintage

- light_petrol_vkt FY2025: BEFU26 - MBU26 = -0.492090 (note `published_actual_revision`)
- ped_vkt_per_capita FY2025: BEFU26 - MBU26 = -0.092884 (note `published_actual_revision`)

## Bridge-refresh impact headline (Current finalist Base case, Total NLTF)

- ar1: FY2026-2030 sum -35.447 $m; FY2031-2050 sum -1.968 $m (refreshed BEFU26 bridge minus pinned MBU26-bridge baseline)
- ensemble: FY2026-2030 sum -35.413 $m; FY2031-2050 sum -1.969 $m (refreshed BEFU26 bridge minus pinned MBU26-bridge baseline)

### Impact coverage

- ar1: 884 matched rows; 0 only in pinned baseline; 0 only in refreshed pack; 510 baseline official-comparator rows excluded (comparator addition is not bridge impact)
- ensemble: 884 matched rows; 0 only in pinned baseline; 0 only in refreshed pack; 510 baseline official-comparator rows excluded (comparator addition is not bridge impact)

## Composition-refresh candidate verdict

MATERIAL vs VFM Base in 16 FYs (2025-2044): max |share delta| 0.025112 exceeds 0.01. OPT-IN CANDIDATE ONLY: the Current model composition is unchanged pending separate approval.

## Scope notes

- The financial decomposition is a financial closure, not causal driver
  attribution: official GDP/unemployment/price/judgment inputs are not
  supplied (driver_availability_matrix.csv) and receive no fabricated dollars.
- The policy-basis comparison keeps `policy_normalised` and `actual_default_ui`
  separate; the official side is always the published vintage and
  delayed-vs-delayed is never constructed as the standard comparison.

Overall: PASS (25/25 checks passed).
