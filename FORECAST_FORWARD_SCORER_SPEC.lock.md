# FORECAST_FORWARD_SCORER_SPEC.lock.md

## Purpose

This lock file defines the fixed-finalist forward-scorer governance contract for Forecast Builder.

The runner may score future assumption rows only when a stream has a repo-local, fixed-finalist scorer that passes parity against archived finalist outputs. Stored validation predictions, training-fit rows, component weights, registry rows, MAPE/R2 values or paper-style fit metrics are not sufficient on their own.

## Capability States

| State | Meaning | Forecast rows |
|---|---|---|
| `numeric_forecast_available` | A repo-local fixed-finalist scorer is available and accepted for new assumption rows. | Numeric forecast values are permitted. |
| `governed_gap` | The stream has no enabled forward scorer but does not have a more specific parity/artifact status. | Forecast values must be missing, never zero-filled. |
| `parity_failed` | Repo-local artifacts exist but the replay chain does not meet parity tolerance. | Forecast values must be missing until parity is resolved. |
| `insufficient_artifacts` | Repo-local artifacts prove some replay/governance facts but do not include enough fitted state or executable scorer code. | Forecast values must be missing until artifacts are vendored and parity-tested. |

## Fixed-Finalist Streams

| Stream | Fixed finalist | Current capability | Required proof before numeric |
|---|---|---|---|
| PED | `PED__RESCUE_static_annual_weighted_top12_capnone` -> `PED__HPOREFINE_solver_static_convex_top18` | `parity_failed` | Inner HPO chain must reproduce stored replay within tolerance and close the feature-level refit gap. |
| Light RUC | `dynamic_RESID_GBR_n150_d1_lr0.05_w36` | `numeric_forecast_available` | Repo-local model-input history, Light RUC registry and scikit-learn runtime. |
| Heavy RUC | `HEAVY_RUC__RECON_STATIC_REBUILT` | `insufficient_artifacts` | C1-C4 executable component scorers or fitted states, plus parity for new-row scoring. |

## Heavy RUC Contract

The only Heavy RUC components that may be reconstructed are:

- C1 `HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64`, weight `0.469332`;
- C2 `HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64`, weight `0.281844`;
- C3 `HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52`, weight `0.144373`;
- C4 `HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40`, weight `0.104451`.

Current repo-local evidence proves stored weighted replay from `component_predictions.parquet` within tolerance, but `model_coefficients.parquet` records that fitted component coefficients or serialized estimators are unavailable and `data/dashboard_evidence_pack_reproducibility/heavy_ruc/source_artifacts/` is absent. Heavy RUC therefore remains non-numeric with `capability_status=insufficient_artifacts`.

## PED Contract

The only PED chain that may be reconstructed is:

- outer finalist `PED__RESCUE_static_annual_weighted_top12_capnone`;
- outer component `PED__HPOREFINE_solver_static_convex_top18`;
- inner members `PED__solver_static_convex_top18`, `PED__solver_preq_convex_top18`, and `PED__diff__GBR_learning_rate0_05_max_depth1_n_estimators650__ylag__w40`.

Current repo-local evidence includes vendored source artifacts and HPO weights, but the inner replay chain has `max_inner_replay_delta=10.361948081296077` against tolerance `1e-6` and the gap register records `feature_level_refit_not_attempted`. PED therefore remains non-numeric with `capability_status=parity_failed`.

## Output Metadata

Every scenario output must carry scorer governance metadata in `future_forecasts`, `component_forecasts`, `forecast_capability_report`, `forecast_chart_rows`, and `forecast_run_manifest.json` model capability records:

- `scorer_version`;
- `source_artifact_hashes`;
- `parity_status`;
- `max_parity_delta`;
- `stored_replay_max_delta`;
- `capability_status`.

Unavailable forecast values must be missing values. They must not be zero, mean forecasts, validation predictions, training-fit predictions or weights-only calculations.

## Search And Mutation Rules

- Do not run broad recursive search for source artifacts during scoring.
- Do not read user-local Downloads or OneDrive model paths during dashboard rendering.
- Do not change historical evidence-pack values, finalists, MAPE/R2, diagnostics, scenario, stress, benchmark or chart-source calculations.
- Do not change Light RUC forecast outputs while adding PED/Heavy governance metadata.
