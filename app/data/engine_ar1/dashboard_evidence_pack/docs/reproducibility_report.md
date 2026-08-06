# Reproducibility Report

Status: COMPLETE for the current finalists.

- PED `PED__VNEXT_SOLVED_CONVEX_TOP2` and Heavy RUC `HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4` are production
  forward-scoreable vNext models: fitted estimators (per-origin and production), exact
  training matrices, prediction feature rows, coefficients, importances and measured
  scenario sensitivities are stored in `data/dashboard_evidence_pack_reproducibility/<stream>_vnext/`.
- Light RUC `dynamic_RESID_GBR_n150_d1_lr0.05_w36` keeps its governed fixed-recipe pack
  (`light_ruc`) plus a production state export (`light_ruc_vnext`).
- The legacy finalists' incomplete-rebuild gaps that this report previously documented
  are now closed by replacement: the archived models remain historically reproducible
  (stored replay) and are documented in the `*_vnext/reproducibility_gap_register.parquet`
  tables and the v6 backup pack.
