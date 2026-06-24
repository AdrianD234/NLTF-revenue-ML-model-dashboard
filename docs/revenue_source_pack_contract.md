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

## Derived Audit Artifacts

`scripts/export_revenue_source_pack_tables.py` exports:

- `canonical_revenue_long.csv`
- `source_pack_intake_status.csv`
- `path_trace_status.csv`
- `reconciliation_report.csv`
- `source_gap_register.csv`
- `remaining_decisions_handoff.csv`
- `validation_issues.csv`
- `loader_exports_manifest.json`

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
values.

The source gap register is a machine-readable list of runtime limitations such
as missing release-value tables, missing Crown top-up rows, annual-only source
pack scope, and unavailable PED total-VKT bridge rows. It backs the Revenue
Outlook warnings and is hash-recorded in `loader_exports_manifest.json`.

The remaining-decisions handoff links each unresolved workbook decision to the
runtime gap IDs, repo-local artifacts, and dashboard treatment that currently
govern it. It is a decision register, not a model refit, and it does not change
forecast values.
