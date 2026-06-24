# NLTF Revenue Source Pack Contract

## Runtime Source Policy

The Revenue Outlook page must load only repo-local normalized files from
`data/revenue_model_source_pack/2026_05_19/` and explicitly promoted Forecast
Builder packs. The raw workbook `19 05 2026 Latest NLTF revenue forecast
model.xlsx` is lineage-only. Its governed SHA256 is
`00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b`.

The runtime must not scan a latest folder, load raw Excel workbooks, publish
test fixtures, or silently convert unavailable bridge rows to zero.

## Canonical Schema

`model_dashboard.revenue_source_pack.load_revenue_source_pack()` builds a
canonical long table with:

`period`, `FY`, `time_grain`, `series_id`, `parent_series_id`, `value`, `unit`,
`aggregation_sign`, `release_vintage`, `forecast_path`, `path_status`,
`scenario_name`, `scenario_role`, `model_basis`, `revenue_basis`,
`source_status`, `bridge_status`, `source_file`, `source_cell`,
`source_hash_sha256`, and `distilled_hash_sha256`.

Rows whose source labels are not registered in `series_master.csv` are retained
with `source_status=unregistered_source_series` and
`bridge_status=source_registry_gap`. They are not dropped or forced into a
nearby label.

## Roll-Up Rules

The governed hierarchy uses the normalized `aggregation_rules.csv` contract:

- Gross FED = PED + LPG + CNG.
- Net FED = Gross FED - FED refunds + explicit Crown top-up when selected.
- Net MVR = MR1/CVL + MR2 + COO + MVR admin - MVR refunds.
- Total RUC = conventional Light/Heavy plus EV/PHEV classes on the selected
  gross/net basis.
- Total NLTF = Net FED + Net RUC + Net MVR + TUC.

`Total RUC+PED revenue` is the legacy Net FED + Net RUC subtotal. It is never
treated as the root Total NLTF revenue series.

The source workbook current selection may still reference that legacy subtotal.
Revenue Outlook defaults and promoted-pack manifests use `Total NLTF revenue`
as the effective dashboard selection, while preserving the workbook current
selection separately as provenance.

## Model And Bridge Roles

PED VKT per capita, Light RUC net km, and Heavy RUC net km remain direct model
outputs. PED revenue, Light RUC revenue, and Heavy RUC revenue are revenue
bridges. LPG, CNG, refunds, MVR, TUC, EV/PHEV splits, and Crown top-up are
official pass-through lines or governed assumptions.

Future revenue remains unavailable until explicit nominal rates and PED bridge
history pass governance. The current distilled pack records these as unresolved
decisions rather than filled values.

Crown top-up is an explicit policy overlay. When the current selection excludes
it, Net FED reconciliation remains Gross FED less refunds. When a user selects
Include, the dashboard must show a visible gap unless governed top-up value rows
exist; it must not apply a fabricated zero.

## Forecast Builder Join Keys

Promoted Revenue Outlook packs expose deterministic canonical join keys on
`future_revenue_forecasts`, `revenue_bridge_components`, and
`revenue_chart_rows`:

`canonical_stream_key`, `canonical_period_key`, `canonical_scenario_key`, and
`canonical_join_key`.

The keys are derived from the reviewed Forecast Builder stream, target period
or period, and scenario name. Historical rows use `historical_actual` as the
scenario key, and non-scenario aggregate audit rows use `all_scenarios`. These
columns are join metadata only; they do not alter activity forecasts, revenue
forecasts, bridge statuses, chart values, or output provenance hashes except for
the expected file hash changes caused by adding the columns.

## Revenue Basis Control

The workbook does not expose `revenue_basis` as a separate native dashboard
control. Revenue Outlook therefore derives that control from normalized
`canonical_long.revenue_basis` values and uses the workbook `revenue_path`
selection to choose the default. The derived control is still source-backed:
it is limited to observed normalized bases such as Net, Gross, Admin,
Deductions, and Nominal ex GST. Activity rows are excluded from the revenue
basis selector.

## Derived Audit Artifacts

`scripts/export_revenue_source_pack_tables.py` exports:

- `canonical_revenue_long.csv`
- `source_pack_intake_status.csv`
- `path_trace_status.csv`
- `reconciliation_report.csv`
- `source_gap_register.csv`
- `remaining_decisions_handoff.csv`
- `series_role_audit.csv`
- `validation_issues.csv`
- `loader_exports_manifest.json`

The export manifest is deterministic for a fixed source pack: it records the
source-pack manifest `created_at` value and an explicit determinism policy
rather than the wall-clock time of the export command. Re-running the exporter
against unchanged normalized files must reproduce identical loader-export
hashes and manifest text.

The reconciliation report compares calculable hierarchy totals to official
rows within rounding and reports `partial_missing`, `official_row_missing`, or
`difference_reported` where the source pack does not support a forced balance.

The source-pack intake status table records repo-local contract files, size,
SHA256, row counts, and replay-only artifacts that are not currently vendored.
It uses relative repository paths only. Missing release-value, forecast archive,
formula-lineage, and quarterly actual files are carried as explicit
`not_vendored` replay gaps, not inferred from local user folders.

The path trace status table records whether each required Revenue Outlook
total-path trace is value-backed and plotted. Actual/benchmark, selected
workbook basis, Aaron Schiff, and in-house paths are plotted from source rows.
Selected MOT/BEFU release paths and rolling BEFU 1Y are marked missing when the
release-value table is unavailable; registry metadata alone is not plotted as
values. The dashboard view overlays the active release-round control in the
`current_selection` column so missing release traces are tied to the selection
being inspected. The total-path chart mirrors those unavailable traces as
legend-only governed gaps, with no numeric x/y values, so selected MOT/BEFU and
rolling BEFU 1Y remain visible without fabricating release-value paths.

The uncertainty source control is evidence-bound. When the user selects
`MOT release round`, the dashboard requires release-value rows from the
source pack. If those rows are not vendored, the uncertainty panel renders an
explicit `release_value_table_missing` gap instead of substituting the
in-house-vs-Schiff model spread. Model-spread uncertainty remains available
only when the uncertainty source control selects a model-based source.

Revenue charts normalize equivalent monetary source-unit labels (`$m ex GST`
and `$m nominal ex GST`) to a single displayed axis and hover unit:
`$m nominal ex GST`. This applies to path, fan, component, and selected-FY
split hovers. It is a display label harmonization only; it does not rescale
values or mix revenue units with activity units. Annual source-pack charts use
one tick per June year.

The source gap register is a machine-readable list of runtime limitations such
as missing release-value tables, missing Crown top-up rows, annual-only source
pack scope, and unavailable PED total-VKT bridge rows. It backs the Revenue
Outlook warnings and is hash-recorded in `loader_exports_manifest.json`.

The remaining-decisions handoff links each unresolved workbook decision to the
runtime gap IDs, repo-local artifacts, and dashboard treatment that currently
govern it. It is a decision register, not a model refit, and it does not change
forecast values.

The series role audit records the runtime treatment for every registered series
and every preserved unregistered source line. PED VKT per capita, Light RUC net
km, and Heavy RUC net km are classified as direct modeled activity streams;
their revenue lines are classified as revenue bridges that require governed
bridge inputs. LPG, CNG, refunds, MVR, TUC, EV/PHEV splits, and Crown top-up
remain pass-through, deduction, policy-overlay, or source-registry gap rows.
