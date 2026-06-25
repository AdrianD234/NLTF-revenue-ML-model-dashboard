# Revenue Outlook Hybrid Evidence

Generated during the active Revenue Outlook hybrid NLTF forecast goal.

## Source-Pack Row Coverage

| Artifact | Rows | Role |
| --- | ---: | --- |
| `release_values.csv` | 33,772 | Selected MOT/BEFU release path and rolling BEFU 1Y archive rows |
| `forecast_archive.csv` | 1,973 | Workbook forecast archive lineage |
| `quarterly_actuals.csv` | 2,007 | Quarterly actuals, Crown top-up rows, and June-year aggregation inputs |
| `fed_rate_paths.csv` | 222 | Current planned and no-2027-12c-uplift FED/PED rate paths |
| `mot_error_bands.csv` | 89 | MOT archived-error uncertainty bands |
| `official_befu25_annual.csv` | 1,940 | Official annual BEFU25 source rows |
| `ped_bridge_inputs.csv` | 94 | Population, total VKT, PED litres intensity, and forecast-input population bridge inputs |
| `canonical_revenue_long.csv` | 39,967 | Canonical source-pack rows with source file/cell and hashes |
| `hybrid_annual_revenue.csv` | 1,296 | Replacement-only annual revenue replay and bridge audit |

## Runtime Gaps And Decisions

All five runtime source-gap rows are currently `available`:

| Gap | Status | Runtime treatment |
| --- | --- | --- |
| `release_value_table_missing` | available | `release_values_available` |
| `fed_path_scenario_values_missing` | available | `fed_path_values_available` |
| `crown_top_up_values_missing` | available | `excluded_by_selection` |
| `quarterly_source_pack_missing` | available | `quarterly_available` |
| `ped_total_vkt_bridge_missing` | available | `bridge_rows_available` |

The three critical decision-handoff rows are `source_backed`:

| Decision | Runtime status |
| --- | --- |
| `future_nominal_ped_fed_rates_by_scenario` | `fed_rate_path_and_total_vkt_source_backed` |
| `future_nominal_effective_light_heavy_ruc_rates` | `source_derived_effective_rate_replay` |
| `ped_bridge_source_history_and_re_estimation` | `bridge_rows_available` |

The non-source `h13_treatment` decision is `label_applied`, with no value
changes.

## Reconciliation Residuals

Residuals are reported and not forced to balance.

| Scope | Component status | Rows | Max absolute residual |
| --- | --- | ---: | ---: |
| `official_actuals` | `reconciled` | 30 | 0.000000 |
| `official_actuals` | `difference_reported` | 5 | 1.067134 |
| `official_actuals` | `official_row_missing` | 14 | n/a |
| `official_actuals` | `partial_missing` | 35 | n/a |
| `selected_dashboard_basis` | `reconciled` | 5 | 0.000000 |
| `selected_dashboard_basis` | `difference_reported` | 49 | 3,137.550702 |
| `selected_dashboard_basis` | `partial_missing` | 54 | n/a |

## Current Validation Evidence

- Focused source-pack tests:
  `python -m pytest -q tests\test_revenue_source_pack.py tests\test_revenue_source_app_views.py`
  passed with `39 passed` under `pytest-revenue-source-replacement-invariants`.
- Non-browser full verifier:
  `scripts\verify_dashboard.ps1 -Python python -Port 8515 -ReuseExistingServer -CommandTimeoutSeconds 900 -SkipBrowser`
  passed through `scripts\invoke_bounded.ps1` under
  `verify-dashboard-skip-browser-requirement-audit`.
- Host browser verifier:
  `scripts\verify_browser_host.ps1 -Python python -Port 8515 -CommandTimeoutSeconds 900`
  passed outside the sandbox with `38 passed` under
  `host-playwright-requirement-audit`.
- `validation_issues.csv` contains only `revenue_basis_alias` and
  `series_registry_gap` warnings.
- Source-pack local path scan found no user-profile or cloud-drive absolute
  path strings.

## Screenshot Evidence

- `artifacts/screenshots/revenue-outlook-after-1680x940.png`
- `artifacts/screenshots/revenue-outlook-after-820x940.png`
- `artifacts/screenshots/revenue_outlook_geometry_after.json`
- `artifacts/revenue_outlook_requirement_audit.md`
