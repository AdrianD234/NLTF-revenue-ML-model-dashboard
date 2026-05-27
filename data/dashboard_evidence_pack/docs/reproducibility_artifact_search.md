# Reproducibility Artifact Search

This search documents why the coefficient, feature-importance, SHAP and scenario-sensitivity tables remain explicit incomplete states rather than fabricated explainability outputs.

## Searched Roots

- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\data\dashboard_evidence_pack`
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs`
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\heavy_ruc_fullgrid_rescue_closure_outputs\run_20260521_171358`
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Repos\NLTF-revenue-ML-model-dashboard\scripts`

## Search Tokens

`coef`, `coefficient`, `feature_import`, `importance`, `shap`, `sensitivity`, `sensitivities`, `scenario_sensitivity`, `scenario_sensitivities`

## Heavy RUC Traceability Files

- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\heavy_ruc_fullgrid_rescue_closure_outputs\run_20260521_171358\all_quarterly_predictions.csv`: found
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\heavy_ruc_fullgrid_rescue_closure_outputs\run_20260521_171358\ensemble_weights.csv`: found
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\heavy_ruc_fullgrid_rescue_closure_outputs\run_20260521_171358\candidate_config_inventory.csv`: found
- `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\heavy_ruc_fullgrid_rescue_closure_outputs\run_20260521_171358\feature_inventory.csv`: found

## Explainability Artifact Matches

- No coefficient, feature-importance, SHAP or scenario-sensitivity artifact files were found in the searched roots.

## Conclusion

Heavy RUC component forecasts, weights, candidate configuration and feature inventory are available and used for component traceability. Fitted model objects, origin-level coefficients, GBM feature importances, SHAP outputs and executable scenario sensitivity outputs were not found in the current evidence pack inputs, so the corresponding tables are marked `reproducibility_status = incomplete` with `artifact_search_status = not_found`.