# Governed-artifact reproducibility hardening — implementation report

Branch: `hardening/governed-artifact-reproducibility`, from
`origin/main` = `ac1895da9a517a0040c363b6077ae37e603ee9a0`.
Environment: Windows 11 / Python 3.13.5 / numpy 2.4.6 / pandas 3.0.3
(pack-building platform) and `nltf-ci:local` Docker Python 3.11 (clean-room
probes). Full starting state: `starting_state.json`.

## Commit sequence

1. `ab5f026` — source and tests: planner caveat retired, uncertainty
   manifest content-pinning (`output_hashes`/`source_main_sha`/
   `builder_version`), status verification, exact-reproduction and
   centre-source tests, engine-identity R² tests, conftest xdist-inheritance
   fix, reusable clean-room harness (Phase A) and R² matrix tooling (Phase B).
2. `173f1d9` — the uncertainty pack rebuilt onto the published Current line
   (built twice at `ab5f026`, byte-identical builds).
3. policy-runtime provenance repin (separate commit, proof attached).
4. evidence and documentation.

## Phase A — all governed pack builders probed first (mandatory)

`ci/probe_governed_pack_reproducibility.sh` + `ci/pack_reproducibility_harness.py`
ran every pack at `ac1895d` in fresh disposable clones under Docker
Python 3.11: snapshot committed → build 1 → value-level compare → build 2 →
idempotency → planner status. Results (`pack_reproducibility_matrix.csv`,
`pack_reproducibility_report.md`, `pack_value_differences.parquet`,
`builder_idempotency.csv`):

- **The uncertainty mismatch is isolated.** The only governed-value movement
  anywhere is `light_petrol_vkt` FY2031–FY2050 in the offline uncertainty
  pack: 20 of 1,000 rows, all six band columns, one rigid factor 1.014895961.
- Every other difference in every pack is cross-environment float noise
  inside the structural closure contract (atol 1e-9 + rtol 1e-12·|x|):
  policy runtime ≤ 7.3e-12 abs, quarterly display ≤ 1.13e-10 abs (its own
  manifest documents this cross-platform behaviour), replay cache ≤ 2.2e-16
  relative on every forecast column. The single outside-contract group is the
  replay cache's `stored_replay_max_delta` diagnostic (288 cells,
  ≤ 9.54e-07) — the builder's own recorded measurement of replay closure,
  environment-dependent by construction, not a governed value.
- All four builders are **byte-idempotent** (build 1 vs build 2 identical:
  72, 8, 3 and 202 files respectively).
- The planner reported every pack ok on the committed tree, and its cascade
  fired correctly after rebuilds (uncertainty/replay rebuild → policy runtime
  stale → bundle affected).

## Phase B — the PED R² parallel movement

Root cause proven, not conjectured: **the two value sets are the two engine
identities** (`r2_parallel_diagnosis.md`, `r2_first_divergence.md`,
`r2_worker_matrix.csv`, `r2_input_hash_matrix.csv`, `r2_writer_inventory.csv`).
The ensemble evidence root computes exactly the committed
0.5591936636031876 / 0.9230110422702978; the AR(1) root computes exactly the
values the pre-isolation xdist run published, 0.5803595524485978 /
0.9448430187011027, digit for digit, in both environments. The xdist incident
was the AR(1) identity (AppTest writers resolving `engine_default() == "ar1"`)
winning the last-write race on the then-shared tracked destination; sequential
runs were masked by collation order (the alphabetically last writer is an
ensemble-root library caller).

**Authoritative values: unchanged.** They are the ensemble identity's, they
reproduce from the current promoted pack (not stale), and no calibration row,
R² definition, fit or coefficient moved. The split condition for a separate
econometric branch was not triggered.

One residual isolation defect was found and fixed: under xdist the
controller's `setdefault` leaked its scratch directory into every worker's
environment, so workers shared one destination (measured: tmp-rename
`FileNotFoundError` collisions at `ac1895d`,
`raw_phase_b_prefix/xdist_n2_load_collision_tail.log`). `tests/conftest.py`
now re-derives the destination per process behind a sentinel; user-supplied
overrides are still honoured. Regression coverage:
`tests/test_r2_engine_identity.py` (committed-identity pin, per-engine
identity, sequential + 2-worker + 4-worker isolated generation with the
tracked tree byte-identical), plus the existing
`tests/test_chart_source_write_isolation.py` suite.

## Phase C — the uncertainty builder and the governed re-centring

The task's premise inverted the direction, and the evidence settles it:

- The published Current line for Light petrol VKT FY2031–FY2050 (34543.478…
  at FY2031) was published on 2026-08-04 (`159e68e`..`0481372`) carrying the
  Treasury macro population restatement
  (`fuel_price_scenario.apply_treasury_macro_to_chart_rows`, factor
  1.014895961 at FY2030).
- The committed offline pack was built on 2026-08-02 (`273148a`), before that
  line existed; its long-run centre (34036.472… at FY2031) never appeared on
  any chart. The "governed re-centring onto the now-published Current line"
  always lived in the policy-runtime materialisation, which re-propagates the
  same draws through the published central path — it was never a helper or a
  manual pack edit.
- The builder therefore **already sources its centre from the final governed
  Current path** — `app.cached_aligned_scenario_detail_frames`' line frame at
  the production key, the same values the dashboard draws and the same frame
  the committed policy runtime's `line_reconciliation` carries. The committed
  pack was the stale side.

Resolution: rebuild the pack from the unmodified source checkout (no builder
value-logic change; the builder gained only manifest content-pinning). No
factor is computed, hardcoded or applied anywhere; the affected rows land on
the published line because that is where the governed centre now is. The
former rigid-rescale exception is retired:
`test_delayed_state_reproduces_the_committed_offline_uncertainty_pack` holds
every row to exact reproduction, and the new
`test_the_offline_pack_centre_is_the_published_current_line` permanently
fails any future pack whose centre drifts off the published Current base
path (975 of 1,000 rows covered by the line frame, including all 20 rows this
incident is about).

Evidence: `uncertainty_recentring_source_audit.csv`,
`uncertainty_recentring_factors.csv`, `uncertainty_before_after.csv`,
`uncertainty_width_invariance.csv`, `uncertainty_nesting_audit.csv`,
`uncertainty_seam_audit.csv`. Widths (span80/span50), median multipliers,
nesting, asymmetry, draws, seed, correlation, quantile map, June-year basis
and the FY2030/FY2031 seam are all unchanged; FY2030 rows are byte-stable.

The planner's temporary warning is replaced by structure: the manifest pins
`output_hashes` and `source_main_sha`, `status_uncertainty` verifies them
(a committed pack the builder did not produce reads `stale`, never silently
`ok`), and the exact-reproduction tests are permanent.

## Non-movement

`governed_value_non_movement.csv` and `revenue_outlook_row_parity.csv`: no
central forecast, revenue value, official value or policy-runtime band value
moved anywhere on this branch. The policy-runtime rebuild is a provenance
repin (`ci/policy_runtime_repin_proof.py` snapshot/compare), byte-identical
on every value frame. The dashboard renders identical numbers before and
after; the only governed data that moved is the offline uncertainty pack's
20 stale rows, which now equal the published line the dashboard was already
drawing.
