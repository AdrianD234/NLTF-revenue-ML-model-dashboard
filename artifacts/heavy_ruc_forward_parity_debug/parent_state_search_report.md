# Heavy RUC Final Parent-State Search

- Audit: `heavy_ruc_final_parent_state_recovery`
- Created: `2026-06-10T09:45:06+00:00`
- Candidate artifacts inspected: `218`
- Recoverable parent fitted state found: `false`
- Recoverable exact parent feature matrix found: `false`
- Capability decision: `keep_parity_failed`
- Parity rerun status: `not_run_no_parent_state_or_exact_matrix_recovered`

## Final Conclusion

Original parent C3/C4 fitted estimator or feature matrix not retained. Heavy RUC cannot safely score new assumption rows from repo-local artifacts.

Exact stored prediction replay remains available from stored parent component predictions. Training-fit R2/provenance remains available from the source-refit state export. New-row Heavy RUC forward scoring remains unavailable until original parent state or exact parent feature matrices are recovered and pass component plus final weighted replay parity.

## Candidate Role Counts

- `parity_debug_evidence`: `3`
- `raw_parent_component_forecast_source`: `30`
- `source_code_reference`: `12`
- `source_refit_feature_matrix_not_parent`: `4`
- `source_refit_state_not_parent`: `168`
- `state_lineage_reference`: `1`

## Candidate Status Counts

- `diagnostic_evidence_not_parent_state`: `3`
- `not_exact_parent_feature_matrix`: `4`
- `not_original_parent_state`: `169`
- `source_code_only`: `12`
- `stored_predictions_not_forward_state`: `30`

## Search Sources

- `repo_source_artifacts` / `heavy_ruc_source_artifacts`: `searched`, files scanned `2`
- `repo_source_refit_state` / `heavy_ruc_forward_state`: `searched`, files scanned `168`
- `repo_source_refit_feature_matrices` / `heavy_ruc_forward_feature_matrices`: `searched`, files scanned `4`
- `repo_parity_debug` / `heavy_ruc_forward_parity_debug`: `searched`, files scanned `19`
- `repo_model_input_history` / `model_input_history`: `searched`, files scanned `5`
- `repo_scripts` / `repo_scripts_heavy_ruc`: `searched`, files scanned `6`
- `external_user_candidate_drop` / `local_heavy_ruc_named_candidates`: `searched`, files scanned `41`
- `external_model_input_candidate_drop` / `local_model_inputs_named_candidates`: `searched`, files scanned `109`

## Notable Lineage

- `heavy_parent_search_0001` `source_code_reference` `source_code_only`: `heavy_ruc_fullgrid_rescue_closure.py`
- `heavy_parent_search_0002` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2015q2.joblib`
- `heavy_parent_search_0003` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2015q3.joblib`
- `heavy_parent_search_0004` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2015q4.joblib`
- `heavy_parent_search_0005` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2016q1.joblib`
- `heavy_parent_search_0006` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2016q2.joblib`
- `heavy_parent_search_0007` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2016q3.joblib`
- `heavy_parent_search_0008` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2016q4.joblib`
- `heavy_parent_search_0009` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2017q1.joblib`
- `heavy_parent_search_0010` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2017q2.joblib`
- `heavy_parent_search_0011` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2017q3.joblib`
- `heavy_parent_search_0012` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2017q4.joblib`
- `heavy_parent_search_0013` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2018q1.joblib`
- `heavy_parent_search_0014` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2018q2.joblib`
- `heavy_parent_search_0015` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2018q3.joblib`
- `heavy_parent_search_0016` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2018q4.joblib`
- `heavy_parent_search_0017` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2019q1.joblib`
- `heavy_parent_search_0018` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2019q2.joblib`
- `heavy_parent_search_0019` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2019q3.joblib`
- `heavy_parent_search_0020` `source_refit_state_not_parent` `not_original_parent_state`: `C1_2019q4.joblib`
