# Heavy RUC Parent-State Triage Findings

- Created: `2026-06-10T11:10:31+00:00`
- Source zip: `heavy_ruc_parent_state_triage_pack_20260610_225153.zip`
- Classified records: `413`
- Capability decision: `keep_parity_failed`
- Parity passed: `false`

## Finding

Triage pack inspected: no original C3/C4 parent fitted estimator or exact parent feature matrix was found. Heavy RUC remains a governed gap; stored historical weighted replay and training-fit R2 are available, but new-row Heavy forecasts require exact C3/C4 parent-state parity.

The staged C3/C4 `.joblib` files hash-match the repo `forward_state` source-refit artifacts. They are not original parent fitted estimators. The matrix-like staged file is the repo source-refit `training_feature_matrix.parquet`, not an exact parent-run feature matrix. Triage component-prediction files are useful lineage, but predictions alone cannot score new assumption rows.

## Classification Counts

- `irrelevant`: `37`
- `original_parent_estimator`: `0`
- `parent_component_predictions`: `22`
- `parent_feature_matrix`: `0`
- `repo_debug_artifact`: `182`
- `source_refit_state`: `169`
- `too_large/skipped`: `3`

## Parity Evidence

- `C1`: `failed`, max abs delta `4.5299530029296875e-06`
- `C2`: `passed`, max abs delta `2.384185791015625e-07`
- `C3`: `failed`, max abs delta `4113063.8222726583`
- `C4`: `failed`, max abs delta `12911117.047347665`
- `C1_C4_weighted`: `failed`, max abs delta `1348579.0867124796`
