# Revenue Outlook Requirement Audit

Status: DELIVERED TO REMOTE AT `22d6d31`; FY2026 JUNCTION UPDATE IN PROGRESS

This audit maps the active Revenue Outlook hybrid NLTF forecast objective to
current repository evidence. The source-pack delivery covered by this audit was
committed and pushed to `origin/main` at `22d6d31`. The current FY2026 junction
update is tracked separately until its scoped changes are validated and pushed.

## Objective Invariants

| Invariant | Current evidence | Status |
| --- | --- | --- |
| Existing Revenue Outlook page, hierarchy, promoted volume pack, and canonical join-key scaffolding are preserved | No `data/current_revenue_outlook` files are modified in `git status`; changes are in source-pack/materializer/exporter/UI/test layers | Proven in current worktree |
| Raw workbook is build-time lineage only and not loaded by Streamlit runtime | `manifest.json` stores raw workbook basename and SHA256 only; app runtime loads repo-local source pack via `cached_load_revenue_source_pack`; source policy says runtime uses normalized files only | Proven in current worktree |
| Volume forecasts, finalist evidence, MAPE/KPI/chart-source evidence are not changed | `git status` shows no `data/dashboard_evidence_pack` or `artifacts/chart_sources` changes; split full verifier passed | Proven in current worktree |

## Requirement Audit

| # | Requirement | Current evidence | Status |
| ---: | --- | --- | --- |
| 1 | Deterministically extract and vendor `release_values.csv`, `forecast_archive.csv`, `quarterly_actuals.csv`, plus FED-path/Crown-top-up rows if present, preserving metadata and hashes without `ws.cell` scans | `manifest.json` row counts and SHA256s: `release_values.csv` 33,772, `forecast_archive.csv` 1,973, `quarterly_actuals.csv` 2,007, `fed_rate_paths.csv` 222; `quarterly_actuals.csv` includes Crown top-up rows; materializer uses `load_workbook(..., read_only=True)` and `iter_rows(values_only=True)` with no `.cell(...)` calls | Proven in current worktree |
| 2 | Replace only PED, Light RUC, Heavy RUC with governed formulas and prevent double counting | `test_hybrid_annual_revenue_replaces_only_three_lines_and_preserves_mot_fixed_rows` asserts only three replacement series, exactly one replacement row per FY/FED-path/series, no non-replacement duplicate of those series, and PED formula `total VKT * litres/100km / 100 * FED rate` | Proven in current worktree |
| 3 | Recalculate Gross FED, Net FED, Total RUC, Net MVR, Total NLTF and report residuals/gaps without forcing balance | `hybrid_annual_revenue.csv` has 1,296 rows; `reconciliation_report.csv` has 192 rows; tests assert roll-up formulas and residual-vs-official arithmetic. Residual summary is recorded in `artifacts/revenue_outlook_hybrid_evidence.md` | Proven in current worktree |
| 4 | Make Release round, revenue path/basis, FED path, and Crown top-up value-backed; path/top-up selections update outputs | `source_gap_register.csv` marks release, FED path, Crown top-up, quarterly rows, and PED bridge `available`; app-view tests assert Crown top-up Include/Exclude changes totals and No-2027-uplift changes PED revenue | Proven in current worktree |
| 5 | Plot selected MOT/BEFU and true rolling BEFU 1Y archive rows, not synthetic shifts | `path_trace_status.csv` marks `selected_mot_befu_release` and `rolling_befu_1y` plotted/available; tests assert rolling BEFU rows are true `release_values.csv` horizon-one rows and chart traces are present | Proven in current worktree |
| 6 | Use uncertainty by source: MOT 50/80 bands from horizon-specific archived errors where available; model spread/gap otherwise | `mot_error_bands.csv` has 89 rows; app-view tests assert MOT archived 50% and 80% bands render when available and no fan is fabricated when not available | Proven in current worktree |
| 7 | Enforce June-year semantics and separate forecast start from selected FY; status from metadata/coverage, not magnitude | `test_quarterly_actuals_use_june_year_mapping_without_partial_year_inference` asserts FY2025 is 2024Q3/2024Q4/2025Q1/2025Q2 and partial FY2026 is not inferred as complete; horizon tests assert selected FY audit remains separate from horizon control | Proven in current worktree |
| 8 | Add horizon control and stop Total NLTF where common fixed-MOT/replacement horizon ends | `REVENUE_SOURCE_HORIZON_OPTIONS` is `Next 5 FY`, `To FY2031`, `Full common horizon`; horizon tests assert Next 5 FY limits traces and Full common horizon is FY2014-FY2031, not carried to 2050 | Proven in current worktree |
| 9 | Make component/deduction rows selectable and downloadable in long form with signs, units, provenance, replacement flag, status, while preserving first viewport layout | App-view tests assert long-form fields, negative deduction signs, component filtering, source provenance, replacement flags, and no local paths; browser geometry evidence shows Revenue Outlook controls/charts above first fold at 1680x940 and 820x940 | Proven in current worktree |
| 10 | Run compileall, full pytest, validators, host Playwright, screenshots/reconciliation outputs, no local paths | `verify-dashboard-skip-browser-requirement-audit` passed; `host-playwright-requirement-audit` passed with 38 browser tests; source-pack/evidence path scans have no user-profile/cloud-drive path strings; screenshots and reconciliation/evidence artifacts exist | Proven in current worktree |

## Generated Source-Pack Coverage

| Artifact | Rows |
| --- | ---: |
| `release_values.csv` | 33,772 |
| `forecast_archive.csv` | 1,973 |
| `quarterly_actuals.csv` | 2,007 |
| `fed_rate_paths.csv` | 222 |
| `mot_error_bands.csv` | 89 |
| `official_befu25_annual.csv` | 1,940 |
| `ped_bridge_inputs.csv` | 94 |
| `canonical_revenue_long.csv` | 39,967 |
| `hybrid_annual_revenue.csv` | 1,296 |

## Current Runtime Gap State

All five runtime source-gap rows are currently `available`:

- `release_value_table_missing`: `release_values_available`
- `fed_path_scenario_values_missing`: `fed_path_values_available`
- `crown_top_up_values_missing`: `excluded_by_selection`
- `quarterly_source_pack_missing`: `quarterly_available`
- `ped_total_vkt_bridge_missing`: `bridge_rows_available`

Decision handoff statuses:

- Critical decisions are `source_backed`.
- H13+ treatment is `label_applied` with no value changes.
- `validation_issues.csv` contains only `revenue_basis_alias` and
  `series_registry_gap` warnings.

## Latest Verification

- `verify-dashboard-skip-browser-requirement-audit`: PASS.
- `host-playwright-requirement-audit`: PASS, `38 passed`.
- Focused source-pack tests after replacement invariants:
  `pytest-revenue-source-replacement-invariants`: PASS, `39 passed`.
- `git diff --check`: clean apart from CRLF warnings.

## Remaining Delivery Caveat

Resolved for the original Revenue Outlook hybrid source-pack delivery: the
source-pack CSV additions and script/test changes were committed and pushed at
`22d6d31`. New FY2026 junction edits must still complete their own validation,
commit, push and clean-status check before they are treated as delivered.
