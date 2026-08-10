# RESOLVED — committed governed artifacts that did not reproduce

**Status: closed by `hardening/governed-artifact-reproducibility`.**
Evidence: `artifacts/governed_artifact_reproducibility/`.

Two instances of one class were found separately during the CI-optimisation
work and investigated together here:

| # | artifact | symptom | resolution |
| --- | --- | --- | --- |
| 1 | `artifacts/chart_sources/r2_ladder_summary.csv` | a parallel test run moved PED calibration R² 0.559 → 0.580 | the two value sets are the two ENGINE identities; write isolation (already merged) plus engine-identity regression tests |
| 2 | `data/revenue_outlook_uncertainty/uncertainty_band_rows.parquet` | rebuilding moved `light_petrol_vkt` FY2031–FY2050 by up to 1.34% | the committed pack predated the published long-run Current line; rebuilt onto it, exception retired, content pinned |

The common shape — **a committed governed artifact that its own builder does
not reproduce** — is now guarded in both directions: the uncertainty manifest
pins its output hashes (a divergent pack reads `stale` in
`scripts/plan_governed_pack_rebuilds.py`), and the chart-source values are
pinned to their engine identity by `tests/test_r2_engine_identity.py`.

---

## A. The PED R² parallel-execution finding

### Original evidence

A `pytest -n 4 --dist=loadscope` run rewrote the tracked
`artifacts/chart_sources/r2_ladder_summary.csv` and moved the published PED
VKT-per-capita `calibration_r2` values, with every test green:

| basis | committed | after the parallel run |
| --- | --- | --- |
| operational pooled | `0.5591936636031876` | `0.5803595524485978` |
| paper horizon mean | `0.9230110422702978` | `0.9448430187011027` |

The earlier diagnosis established (and this branch re-verified) that all
seven `load_evidence_pack` library callers produce byte-identical output on
the committed default root, sequentially, in both Python 3.11 and 3.13; that
the only byte difference between environments is line endings; and that only
xdist ever moved a value. What it could not explain was why concurrency
produced a *different but internally consistent* pair of numbers.

### Final root cause

**The two value sets are the two engine identities. There was never any
numerical nondeterminism.**

The "moved" paper-basis value `0.9448430187011027` exists verbatim in
`data/engine_ar1/dashboard_evidence_pack/data/diagnostic_tests.parquet`; the
committed `0.9230110422702978` is the same stored diagnostic in the ensemble
pack `data/dashboard_evidence_pack/data/diagnostic_tests.parquet`. The
operational value is recomputed at load time from whichever pack's
`scorecard_predictions.parquet` was loaded, and moves with it.

Two writer populations exist:

* the seven library callers resolve `DEFAULT_EVIDENCE_PACK_ROOT`
  (`data/dashboard_evidence_pack`, the **ensemble** pack) — the population the
  earlier writer matrix tested;
* app-booting modules (AppTest smoke, UI, engine-switcher, scenario-key,
  Excel-extract tests) resolve the active engine through
  `model_dashboard.engine.engine_default()`, which is **`ar1`** when
  `DASHBOARD_ENGINE_DEFAULT` is unset — so they write the AR(1) identity.
  Two further modules set that variable to `ar1` process-wide at import time.

Before write isolation, both identities shared the single tracked
destination, so the file's final content was decided by whichever writer ran
last. Sequential runs were protected by an accident of collation order: the
alphabetically last writer module (`test_stress_horizon_aliases`, a library
caller on the ensemble root) always restored the committed content after any
AppTest module had overwritten it. `--dist=loadscope` distributed modules
across workers and broke that accidental ordering; an AR(1)-identity writer
finished last and its values were published. Every test passed because both
identities are internally consistent.

Proven by the Phase B matrix (`ci/phase_b_r2_matrix.sh`,
`ci/r2_writer_audit.py`; evidence in
`artifacts/governed_artifact_reproducibility/r2_worker_matrix.csv` and
`r2_parallel_diagnosis.md`): the ensemble root reproduces the committed
values exactly under sequential and isolated 2-/4-worker execution in every
distribution mode, the AR(1) root reproduces the incident values, and a
deliberately shared destination (the pre-fix world, recreated in scratch)
republishes whichever identity wrote last.

### Fix

* Write isolation (merged previously): explicit `output_dir` /
  `NLTF_CHART_SOURCE_OUTPUT_DIR` / per-worker scratch destinations, plus the
  governed-tree gate in every lane.
* This branch adds the identity layer: `tests/test_r2_engine_identity.py`
  pins the committed CSV to the ensemble pack's own stored diagnostics, pins
  the AR(1) identity as *different and internally consistent*, and proves
  sequential, two-worker and four-worker isolated generation all reproduce
  the committed values while the tracked files stay byte-identical.

### Authoritative values

**Unchanged.** The committed values are the ensemble engine's, they
reproduce exactly from the current promoted ensemble pack (so they are not
stale), and no calibration row, R² definition, model fit or coefficient was
touched. The AR(1) values are correct *for the AR(1) engine* and are neither
published nor promoted. No owner decision is required.

---

## B. The uncertainty builder mismatch

### Original discrepancy

On an unmodified tree, `scripts/build_revenue_outlook_uncertainty_pack.py`
moved exactly 20 of 1,000 rows — `light_petrol_vkt` FY2031–FY2050 — by one
rigid factor ≈ 1.4896% (max ≈ 509 units), all six band columns together;
every other row reproduced to ≤ 7.3e-12 (cross-environment float noise; the
same-platform rebuild is byte-identical).

### What the historical re-centring actually was

The committed offline pack was built on 2026-08-02 (`273148a`), **before**
the Light petrol VKT series had any published Current line past FY2030. Its
long-run centre was therefore the pre-overlay level — a value that never
appeared on any chart. On 2026-08-04 the PED-activity work published the
FY2031–FY2050 line carrying the Treasury macro population restatement
(`fuel_price_scenario.apply_treasury_macro_to_chart_rows`; Light petrol VKT
factor 1.014895961; commits `159e68e`, `316b39a`, `05c722e`), and `0481372`
rebuilt the downstream packs through the reference pipeline — which is where
the "re-centring onto the now-published Current line" lived. It was never a
helper or a manual edit, and the offline pack was simply not rebuilt.

So the direction is the opposite of what the original write-up assumed: the
**builder already sources its centre from the final governed Current path**
(the aligned line reconciliation under the production key — the same values
the dashboard draws), and the **committed pack was the stale side**.

### Builder correction and exact reconstruction

* The offline pack was rebuilt from the unmodified source checkout. The 20
  affected rows moved onto the published Current line by construction — no
  factor was computed, hardcoded or applied anywhere; the centre is read from
  the same governed frames as before. Widths, asymmetry, nesting, draws,
  seed, copula, quantile map, June-year basis and the FY2030/FY2031 seam are
  unchanged (see `uncertainty_width_invariance.csv`, `uncertainty_nesting_audit.csv`,
  `uncertainty_seam_audit.csv`).
* `test_delayed_state_reproduces_the_committed_offline_uncertainty_pack` now
  holds **every** row to exact reproduction; the rigid-rescale exception is
  retired.
* `test_the_offline_pack_centre_is_the_published_current_line` is the new
  permanent guard for the founding condition: the offline centre must equal
  the published Current base path, so a pack drifting off the chart again is
  a test failure, not an invisible centre.
* The builder now writes `output_hashes`, `source_main_sha` and
  `builder_version` into the manifest, and `plan_governed_pack_rebuilds.py`
  verifies them: committed pack bytes that its manifest cannot vouch for read
  as `stale` instead of `ok`.
* The planner's temporary rebuild warning (`REBUILD_CAVEATS`) is removed —
  the builder command reproduces the committed pack again.

---

## C. Other governed pack reproducibility

Every governed pack was probed in a fresh disposable clone under the Docker
Python 3.11 clean room: committed vs build 1, build 1 vs build 2, and the
planner status before and after
(`ci/probe_governed_pack_reproducibility.sh` +
`ci/pack_reproducibility_harness.py`; evidence in
`artifacts/governed_artifact_reproducibility/pack_reproducibility_matrix.csv`
and `pack_reproducibility_report.md`).

Summary: **the uncertainty issue was isolated.** No other pack moves a
governed value. `replay_cache`, `quarterly_display` and `policy_runtime`
reproduce their committed content to cross-environment float-noise level
(within each pack's own documented numerical contract, and far inside the
1e-9 test tolerance), and every builder is byte-idempotent when run twice in
the same environment. Manifest-level differences are provenance only
(`source_main_sha`, `build_environment`, per-file hashes tracking the float
noise).

Remaining follow-up (not blocking, recorded for the roadmap):

* ~~`load_evidence_pack` still writes chart sources as a side effect on every
  call; the structural question of moving publication behind one explicit
  materialisation command (original open question 6) remains open.~~
  **RESOLVED by `hotfix/r2-app-boot-read-only` (issue #31).** See below.
* The quarterly display pack is byte-reproducible only on the platform that
  built it (documented in its own manifest); cross-platform comparison is by
  value at ~1e-13, which the tests already honour.

---

## Instance 3 — app-boot mutation of governed chart-source evidence (issue #31)

**Status: resolved by `hotfix/r2-app-boot-read-only`.**
Evidence: `artifacts/r2_app_boot_read_only/`.

The write isolation recorded above fixed the *test suite*. It did not fix the
*application*, and it is the reason nobody noticed: `tests/conftest.py`
redirects chart-source output, so no test process could observe what a real
`streamlit run app.py` does.

Reproduced on a clean clone of `origin/main` at `46d1f87` with a real Streamlit
server and a real browser session, in normal configuration (no
`NLTF_CHART_SOURCE_OUTPUT_DIR`, engine default `ar1`, cache warmer on). Initial
boot alone was enough:

```
 M artifacts/chart_sources/r2_ladder_summary.csv

0.5591936636031876 -> 0.5803595524485978    (current_grid_operational_pooled)
0.9230110422702978 -> 0.9448430187011027    (schiff_paper_horizon_mean)
```

Only `r2_ladder_summary.csv` changed; the gap register and training-fit detail
did not. The change survived `--ignore-all-space`, so it was a genuine value
substitution rather than a line-ending artefact.

Call chain: `main()` -> `load_active_run` -> `cached_load_evidence_pack` ->
`load_evidence_pack` -> `write_chart_source_tables`. The app boots on
`engine_default() == "ar1"` while the committed tables carry the ensemble
identity, so the boot republished a valid-but-different identity over the
governed one.

**Resolution.** Materialisation is opt-in at the loader boundary and guarded at
the writer boundary:

* `load_evidence_pack` / `load_parquet_dashboard` take
  `materialize_chart_sources` (default `False`). Their materialisation path is
  SCRATCH-only, so no load path can reach the governed directory.
* `write_chart_source_tables` takes an explicit `mode`
  (`READ_ONLY` / `SCRATCH` / `PROMOTE`). The canonical directory requires
  `PROMOTE` **and** the governed `ensemble` identity; AR(1) is refused and
  routed to `artifacts/diagnostics/chart_sources/<engine>/`.
* `scripts/promote_chart_sources.py` is the one sanctioned publisher.
* `scripts/check_app_boot_read_only.py` proves it with a real host process,
  outside pytest, because AppTest inherits the redirect that hid the path.

Promotion from the ensemble pack reproduces the committed bytes exactly (`git
status` clean afterwards) and is idempotent across runs.

**Keep the three facts distinct.** Engine identity collision (instance 1), test
writer isolation (instance 1's fix), and app-boot governed-file mutation
(instance 3) are separate problems with separate fixes. The authoritative
ensemble R-squared definition never changed and was not in question in any of
them:

| | operational pooled | paper horizon mean |
| --- | --- | --- |
| ensemble (governed) | `0.5591936636031876` | `0.9230110422702978` |
| AR(1) | `0.5803595524485978` | `0.9448430187011027` |

No model, forecast or revenue value moved: the policy-runtime repin proof
compared 200 governed frames cell by cell and found only provenance movement.
