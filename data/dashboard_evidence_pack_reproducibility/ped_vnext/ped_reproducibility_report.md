# PED VKT per capita vNext reproducibility report

Status: COMPLETE (production forward-scoreable)

- Finalist: `PED__VNEXT_SOLVED_CONVEX_TOP2`
- Parity: state replay 0.0e+00, recipe replay 0.0e+00 (tolerance 1e-6)
- Max evidence-pack prediction delta: 0.0e+00
- Canonical input basis: `data/model_input_history/ped_inputs.parquet`
- Lag recursion: recursive_predicted; transform: ln(target) -> exp
- Seeds fixed (random_state=42); scikit-learn 1.7.2

## Components

- `PED__VNEXT__dynamic_no_leads__resid_gbr_learning_rate0p05_max_depth1_n_estimators150__noylag__wexp` (weight 0.5844, resid_gbr, window expanding)
- `PED__VNEXT__diff__gbr_learning_rate0p05_max_depth1_n_estimators400__ylag__w56` (weight 0.4156, gbr, window 56)

## Lineage

The archived legacy finalist remains historically reproducible (stored replay)
but is not forward-scoreable; it is documented in
`reproducibility_gap_register.parquet` and preserved in the v6 pack backup.
