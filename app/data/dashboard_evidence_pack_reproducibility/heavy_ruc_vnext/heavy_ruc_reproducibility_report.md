# Heavy RUC volume vNext reproducibility report

Status: COMPLETE (production forward-scoreable)

- Finalist: `HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4`
- Parity: state replay 0.0e+00, recipe replay 0.0e+00 (tolerance 1e-6)
- Max evidence-pack prediction delta: 0.0e+00
- Canonical input basis: `data/model_input_history/heavy_ruc_inputs.parquet`
- Lag recursion: recursive_predicted; transform: ln(target) -> exp
- Seeds fixed (random_state=42); scikit-learn 1.7.2

## Components

- `HEAVY_RUC__VNEXT__dynamic_no_leads__ridge_alpha10p0__ylag__w64` (weight 0.7089, ridge, window 64)
- `HEAVY_RUC__VNEXT__schiff__gbr_learning_rate0p08_max_depth1_n_estimators150__noylag__w52` (weight 0.2122, gbr, window 52)
- `HEAVY_RUC__VNEXT__dynamic_no_leads__gbr_learning_rate0p05_max_depth1_n_estimators650__ylag__w52` (weight 0.0789, gbr, window 52)

## Lineage

The archived legacy finalist remains historically reproducible (stored replay)
but is not forward-scoreable; it is documented in
`reproducibility_gap_register.parquet` and preserved in the v6 pack backup.
