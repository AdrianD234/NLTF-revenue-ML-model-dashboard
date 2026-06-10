# Heavy RUC forward-scorer parity diagnosis

## Verdict

Heavy RUC must remain `parity_failed`; numeric forward forecasts are not enabled.

The repo-local replay from `data/model_input_history/heavy_ruc_inputs.parquet` does not reproduce the archived C1-C4 component predictions within the `1e-6` parity tolerance.

## Current worst row

- Component: `HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64`
- Origin / target / horizon: `2020Q4` -> `2021Q3` / `3`
- Stored component prediction: `939536576.056`
- Replayed component prediction: `1035060738.02`
- Max absolute delta: `95524161.9688`

## Evidence summary

- C1: max abs delta `36062398.0139`, matched rows `564` of `564`, missing rows `0`.
- C2: max abs delta `95524161.9688`, matched rows `564` of `564`, missing rows `0`.
- C3: max abs delta `66229698.8474`, matched rows `564` of `564`, missing rows `0`.
- C4: max abs delta `58697769.1477`, matched rows `564` of `564`, missing rows `0`.

## Diagnosis

- Candidate configs, weights, windows, feature-set names, target-lag flags and hyperparameters match the locked Heavy RUC finalist registry.
- Stored origin/target/horizon keys are all matched by repo-local replay rows, so this is not a missing-key coverage failure.
- The parent-run feature matrix, parent workbook, and fitted C1-C4 estimators are not vendored in the repo. Only parent component predictions and derived training-fit rows are available.
- The committed training-fit rows record a prior source replay max delta of `2.38418579102e-07`, while the repo-local input-history replay max delta is `95524161.9688`.
- The likely root cause is repo-local input-history or engineered-feature-matrix mismatch against the parent run. A feature-engineering mismatch cannot be ruled out until the parent feature matrix or fitted estimators are vendored.

## Prior audit note

A prior audit reference recorded max abs delta `126618189.8` at `2022Q1` -> `2024Q4` for C2. This debug pack keeps that row in `feature_matrix_comparison.csv` as `known_prior_audit_reference`, but the headline verdict uses the current committed source script and current committed input-history parquet.

## Exported files

- `component_parity_summary.csv`
- `component_parity_rows.csv`
- `worst_rows.csv`
- `feature_matrix_comparison.csv`
- `training_window_comparison.csv`
- `origin_target_coverage_comparison.csv`
- `candidate_config_comparison.csv`
- `input_history_manifest.json`
- `heavy_ruc_parity_diagnosis.md`

## Canonical history recovery update

The canonical-history recovery audit found the source-script workbook path and `Stage 1 Inputs` sheet, but Heavy RUC remains `parity_failed`.

### Current vs source-script history

- Current repo history max component/final delta: `95524161.9688`.
- Source-script workbook history max component/final delta: `12911117.0473`.
- Source-script workbook sheet: `Stage 1 Inputs`.
- Current repo engineered feature count: `356`.
- Source-script engineered feature count: `473`.

### Post-canonical replay

- C1: `failed`, max abs delta `4.52995300293e-06`.
- C2: `passed`, max abs delta `2.38418579102e-07`.
- C3: `failed`, max abs delta `4113063.82227`.
- C4: `failed`, max abs delta `12911117.0473`.
- Final weighted C1-C4 replay: `failed`, max abs delta `1348579.08671`.

### Governance decision

- `data/model_input_history/heavy_ruc_inputs.parquet` was not overwritten because source-script replay still fails the fixed `1e-6` component/final parity tolerance.
- C2 Schiff replay passes from the recovered source-script history, but target-lagged GBM components C3/C4 remain outside tolerance.
- The remaining governed gap is missing parent fitted component estimators or parent feature matrices for the target-lagged GBM components.
