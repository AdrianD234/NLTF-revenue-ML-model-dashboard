# DIAGNOSTIC_DATA_SPEC.lock.md

Diagnostic audit files are secondary evidence for the Stage 1 dashboard. They supplement, but do not replace, the Parquet candidate cone.

## Accepted Diagnostic Inputs

- `model_diagnostic_audit_tables.xlsx`
- `model_diagnostic_audit_report.md`
- `tables/model_summary_our_vs_schiff.csv`
- `tables/paired_common_forecast_pairs_our_vs_schiff.csv`
- `tables/h1_residual_diagnostics_our_vs_schiff.csv`
- `tables/diagnostic_pass_matrix.csv`
- selected quarterly or annual prediction files if present under the repo or diagnostic pack

## Required Behavior

- Missing diagnostic tables must produce explicit unavailable cards, not fake data.
- ACF should use audit tables first, then selected residuals if raw prediction rows exist.
- Residual vs fitted and error distribution charts must not invent points when raw predictions are absent.
- Pass matrix thresholds are locked:
  - Calibration or Mincer-Zarnowitz R2 pass: at least 0.70. This must not be labelled adjusted R2 unless an actual adjusted R2 source field is used.
  - Durbin-Watson pass: between 1.5 and 2.5.
  - ADF pass: p-value below 0.05.
  - KPSS pass: p-value above 0.05.
  - Breusch-Pagan and White pass: p-value above 0.05.
  - Jarque-Bera is caution, not fatal, when p-value is below 0.05.
  - Cointegration pass: p-value below 0.05 where relevant.
