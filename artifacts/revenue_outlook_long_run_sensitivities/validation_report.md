# Validation report — Fleet efficiency and PT mode shift continuous through FY2050

Branch `fix/revenue-outlook-fleet-pt-through-2050`, base
`10f4e36edb9c769eaf33b81fc6388af059f261db` (origin/main at start).

## Root cause (see layer_diagnosis.md)

`ped_revenue_bridge_audit` is governed only over FY2026–FY2030. The
sensitivity audit frame multiplied its `base_litres_per_100km` /
`ped_rate_nzd_per_litre`, so for every post-model year the adjusted
`ped_volume` / `gross_ped_revenue` were NaN and silently skipped; `_delta()`
turned the missing PED effect into a zero rollup delta, and PED volume, PED
revenue and all FED/NLTF rollups snapped back to the unsensitised path at
FY2031. PT activity series already compounded to FY2050; PT's defects were
the FY2030 start year and the same PED-side truncation.

## Fix (single canonical boundary)

In `revenue_sensitivity_impact_audit_frame` (model_dashboard/revenue_outlook.py):

1. Post-model years derive the scenario-specific pre-sensitivity baseline
   from that FY's own line rows (intensity = 100·PED volume ÷ light petrol
   VKT; effective PED rate = gross PED revenue ÷ PED volume) and apply the
   proportional factors directly to the FY's own baseline — never recursively
   from the previous adjusted year, and bit-exact pass-through when every
   factor is 1.0. FY2026–FY2030 keep the governed bridge formula unchanged.
2. Factors use `exp(n · log1p(−r))` with `n(FY) = max(FY − 2025, 0)`
   (`_cumulative_sensitivity_factor`).
3. `SENSITIVITY_PT_START_FY` = `REVENUE_FIRST_FORECAST_FY` (2026) — owner
   decision; labels and seed notes updated.
4. Post-model audit rows stamp segment, exponents, factors, litres, rate and
   a computation key.
5. Annual 50/80% bands are withheld with a governed note while Fleet or PT is
   non-Off (`_uncertainty_bands_withheld_for_sensitivity`); quarterly bands
   remain withheld as before.

Every consumer (chart rows, line reconciliation, formula residuals, stack,
bridge, future forecasts, native quarters via annual ratio, derived quarters
via the final annual rows, downloads, policy runtime bypass, A/B through
`cached_revenue_outlook_view`) inherits the same audit — no chart-only patch
and no second implementation.

## Evidence

* `lever_factor_audit.csv` — Low/Med/High/Custom-10% fleet + Low/Med/High PT,
  both engines, FY2026/2030/2031/2040/2050: max |ratio − (1−r)^n| = 1.44e−15.
* `seam_audit.csv` — factor(2031) = factor(2030)·(1−r) with max residual
  2.22e−16; `resets_to_baseline` false everywhere.
* `nonmovement_audit.csv` — guarded series (heavy/heavy-BEV/MVR, plus all
  activity under fleet-only) exact non-movement, zero violations.
* `formula_closure_audit.csv` — Current-path formula residuals all
  `reconciled` under every lever/level/engine.
* `quarterly_reconciliation.csv` — under Fleet Med + PT Med the four native
  quarters reconcile to the adjusted annual (additive series max gap 9.1e−13);
  no quarter beyond 2050Q2.
* `browser_acceptance.md` — rendered-chart verification on :8537.

## Test results (this branch, local venv)

* New `tests/test_revenue_outlook_long_run_sensitivities.py`: 60 passed
  (33-item contract, both engines at frame level).
* Existing sensitivity/formula tests (`test_revenue_outlook.py -k
  "sensitivity or formula or residual"`): 8 passed (PT exponent test updated
  to the FY2026 contract, as the handoff sanctions).
* `test_revenue_outlook_series_coverage.py` + `test_quarterly_disaggregation.py`:
  64 passed.
* `test_revenue_outlook_replay_cache.py` + `test_revenue_outlook_policy_runtime.py`:
  77 passed after the governed digest repins.
* `test_scenario_comparison.py` + `test_streamlit_smoke.py` +
  `test_revenue_outlook_ui_slim_2050.py`: 111 passed (A/B parity: side equals
  single, zero deltas, A isolation, shared FY2050 horizon).
* Conflict scenario extract validation: 21/21 PASS.
* `check_streamlit_deploy_readiness.py`: PASS.

## Pack rebuilds actually required

* `data/revenue_outlook_replay_cache/{ar1,ensemble}` — manifest digest repin
  only; all 35 frames round-tripped byte-identically.
* `data/revenue_outlook_policy_runtime/{ar1,ensemble}` — manifest digest repin
  only; all 99 frames per engine round-tripped byte-identically.
* Quarterly display pack — NOT rebuilt: its source digest covers data files
  only, none changed.
* Main revenue outlook packs — NOT rebuilt: runtime start-years come from
  code constants and lever values from the unchanged pack config; the stored
  `sensitivity_config`/`sensitivity_seed_inputs` metadata (PT start_fy 2030,
  old note text) is stale until the next scheduled pack rebuild, which will
  regenerate them from the updated frames. Recorded as a limitation.

## Final CI and the authorised cross-environment gate change

The first clean-clone CI cycle on `b65fff3` failed on exactly two tests of
1877: `test_replay_cache_matches_reference_exactly[ar1|ensemble]` — the
cross-environment compiled-cache-vs-live-replay comparison (cache built on
Windows/py3.13, CI recomputing on Linux/py3.11). Measured drift: max_abs
6.104e-05 (fuel `future_forecasts.demand_calibrated_delta` and calibration
closure-ratio columns), exceeding the old `abs_tol=1e-6` gate by 2.1e-06.
Both replay-parity jobs passed; the same-environment path is byte-exact; the
repinned caches were byte-identical to the pre-branch build, so the drift is
runner noise, not a branch change. All four conditions of the handoff's
section-7 authorisation held, so the CROSS-ENVIRONMENT gate only was moved
to the presentation tolerance (`_CROSS_ENVIRONMENT_ATOL = 1e-4`, rel 1e-9
retained); the same-environment serialisation gate, formula closure and all
accounting tolerances are untouched. The bound's own sanity test now pins
the observed drift as accepted and larger real changes as still caught.

## Remaining limitations

1. RESOLVED on this branch (owner decision, 2026-08-04): Scenario B's PT and
   freight levers now render unconditionally, and the page freight toggle is
   no longer method-detail-gated — both are first-class governed levers
   continuous through FY2050. "Reset B to current page (A)" now mirrors an
   A-side PT selection (pinned by
   `test_revenue_outlook_compare_mode_renders_pt_and_freight_for_scenario_b`).
   The e-RUC lever remains method-detail workshop copy.
2. Pack `sensitivity_config`/`sensitivity_seed_inputs` metadata carries the
   old PT start-year text until the next full pack rebuild (values and
   runtime behaviour are unaffected).
3. Annual bands are withheld (not transformed) under non-Off Fleet/PT: rollup
   series cannot be re-quantiled without component-level draws, so the honest
   option 2 of the uncertainty contract was taken.
