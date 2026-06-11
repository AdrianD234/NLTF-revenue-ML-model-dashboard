# FORECAST_FORWARD_SCORER_VNEXT_AMENDMENT.lock.md

## Purpose

Governed amendment to `FORECAST_FORWARD_SCORER_SPEC.lock.md`. It records the
closure decision for the PED and Heavy RUC forward-scoring gaps and the
fixed-finalist succession rules for the vNext production scorers.

## Closure decision

Exhaustive recovery work (parent-state triage of 413 staged files, canonical
source-script history recovery, five lag-recursion policies, source-refit
state export) established that:

- Heavy RUC `HEAVY_RUC__RECON_STATIC_REBUILT` C3/C4 parent fitted estimators
  and exact parent feature matrices were never retained. Best replay deltas:
  C3 `4.11e6`, C4 `1.29e7` against tolerance `1e-6`. Recovery is infeasible.
- PED `PED__HPOREFINE_solver_static_convex_top18` inner members were never
  retained as fitted state (inner weighted replay delta `10.36`;
  `feature_level_refit_not_attempted`). Recovery is infeasible.

Both legacy finalists are therefore **archived**: historically reproducible
(stored replay) but permanently non-forward-scoreable. They remain the
governed basis of the historical evidence pack at
`data/dashboard_evidence_pack`, which is unchanged.

## vNext succession rules

1. New forward forecasts for PED and Heavy RUC are produced only by the vNext
   fixed finalists recorded in
   `data/dashboard_evidence_pack_reproducibility/<stream>_vnext/fitted_model_manifest.json`.
2. vNext finalists were selected by `pipeline/vnext_run.py` from a governed
   candidate grid (locked-spec refits plus disciplined challengers; no lead
   features; fixed seeds) scored on the exact stored evidence keysets for
   both score bases. Selection basis: paper-style horizon-mean MAPE,
   tie-break operational pooled MAPE.
3. A stream may be numeric in the Forecast Builder only while ALL of the
   following hold, enforced at every score call:
   - `forward_scorer_parity_audit.json` records `parity_status = "passed"`
     (state replay AND deterministic recipe replay within `1e-6`);
   - the runtime production-state gate replays archived training-fit
     predictions from saved state within `1e-6`;
   - the fitted-state files match the manifest SHA256 hashes.
   Otherwise the stream emits governed missing-value gaps.
4. After any environment change (Python/scikit-learn/numpy upgrade, new
   host), rerun `python -m pipeline.vnext_run finalize scorecards` and the
   governance suite `pytest tests/test_vnext_parity.py` before relying on
   numeric outputs.
5. No model search may run at score time (`broad_search_run: false` is
   asserted by tests).

## Relationship to the legacy spec

The legacy capability rows for PED (`parity_failed`) and Heavy RUC
(`parity_failed` / `insufficient_artifacts`) in
`FORECAST_FORWARD_SCORER_SPEC.lock.md` continue to describe the **legacy**
finalists. `model_dashboard/vnext_forward_integration.py` resolves stream
capability to the vNext scorer when its governed pack is present and gates
pass; otherwise the legacy governance applies unchanged.

## Promotion record

- The governed dashboard evidence pack was rebuilt to
  `dashboard_evidence_pack_v7_vnext_finalists` by
  `scripts/promote_vnext_to_evidence_pack.py` on 2026-06-11.
- All finalist-dependent tables (scorecards, predictions, components,
  registry, coefficients, importances, sensitivities, diagnostics, frontier
  anchors, Schiff comparisons) now carry the vNext finalists. Schiff
  benchmark rows, Light RUC rows and the frontier visual samples are
  unchanged.
- Every rebuild formula was first verified to reproduce the stored legacy
  finalist values exactly (`--check` mode), including the statsmodels
  diagnostics battery and the Pass/Watch/Fail matrix derivation.
- The previous pack is preserved at `data/dashboard_evidence_pack_v6_backup`.
- The archived legacy finalists remain documented in the
  `*_vnext/reproducibility_gap_register.parquet` tables and the v6 backup.
