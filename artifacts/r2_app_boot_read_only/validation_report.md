# Validation report: issue #31

Local validation, Windows, `.venv` Python 3.13.5, Streamlit 1.58.0.

## 1. Reproduction, before any change

Real Streamlit host process against a clean clone of `origin/main` at
`46d1f87`. `git status` went clean -> `M artifacts/chart_sources/r2_ladder_summary.csv`;
the ensemble pair was replaced by the AR(1) pair; the change survived
`--ignore-all-space`. Only one of the three tracked files changed. See
`reproduction.md`.

## 2. Real host-process checks, after the fix

`scripts/check_app_boot_read_only.py`, real server + real browser, outside
pytest. Each run boots, loads the Revenue Outlook page, performs a rerun, and
stops the server cleanly.

| Run | Files before | Files after | Modified | git status | Result |
| --- | --- | --- | --- | --- | --- |
| normal cache warmer (the essential case) | 3 | 3 | 0 | clean | PASS |
| cache warmer disabled | 3 | 3 | 0 | clean | PASS |
| `DASHBOARD_ENGINE_DEFAULT=ensemble` | 3 | 3 | 0 | clean | PASS |
| after a canonical promotion (full tree) | 22 | 22 | 0 | clean | PASS |
| inside the built Databricks App bundle | 3 | 3 | 0 | n/a | PASS |

The warmer-on case is the one that matters and is green; the warmer was never
implicated, and the path was not hidden by disabling it.

## 3. Focused test suites

| Suite | Result |
| --- | --- |
| `compileall` over every changed module | OK |
| `tests/test_app_boot_read_only.py` (new, 14 tests) | 14 passed |
| chart-source isolation, R2 engine identity, R2 ladder/metrics, chart-source tables, evidence pack, score-basis governance, governance page, arbitration values, chart data reconciliation, artifact freshness | 109 passed |

## 3b. Full local core suite, and failure triage

Run as `-m "not e2e and not requires_local_scratch"` in alphabetical chunks with
`-p no:randomly`, so failures could be **named** rather than inferred from a
progress bar. One pytest process at a time.

Result: **2013 passed, 28 failed**, across six modules.

Every one of the 28 was a missing environment prep step, not a defect. CI runs
`python scripts/regenerate_curated_data_from_pack.py` before the test suites
(`.github/workflows/ci.yml:291` and `:368`, `ci/entrypoint.sh:42-44`), which
materialises the gitignored `artifacts/curated_data/*.csv`. My first local run
skipped it, so those modules failed on `FileNotFoundError` before reaching any
assertion.

| Module | Failures | Reproduced at base `46d1f87`? | After the CI prep step |
| --- | --- | --- | --- |
| `test_cone_landscape_validation.py` | 7 | yes | pass |
| `test_curated_data.py` | 7 | yes | pass |
| `test_ensemble_composition_validation.py` | 5 | yes | pass |
| `test_no_stale_finalist_values.py` | 2 | yes | pass |
| `test_schiff_purity.py` | 4 | yes | pass |
| `test_stress_horizon_validation.py` | 3 | yes | pass |

Named failures: `test_candidate_landscape_has_finalists`,
`test_candidate_landscape_has_schiff_benchmarks`,
`test_candidate_landscape_has_distribution_sample`,
`test_candidate_landscape_has_frontier_and_top_cluster_by_stream`,
`test_candidate_landscape_is_capped`, `test_candidate_landscape_roles_are_populated`,
`test_candidate_landscape_default_mode_is_not_full_raw`,
`test_curated_data_latest_values`, `test_no_stale_autogluon_finalist_values`,
`test_candidate_landscape_sample_has_expected_roles`,
`test_candidate_landscape_sample_is_capped`,
`test_pure_schiff_filter_excludes_residuals_and_blends`,
`test_stress_horizon_has_expected_buckets` (x2, two modules),
`test_ensemble_composition_positive_weights`,
`test_ensemble_composition_has_all_streams`, `test_ensemble_weights_are_positive`,
`test_ensemble_component_labels_short`, `test_component_lookup_contains_full_names`,
`test_ensemble_hover_is_readable`,
`test_stale_autogluon_values_are_not_current_finalists`,
`test_current_finalist_models_are_static_convex_top18_arbitration_winners`,
`test_pure_schiff_excludes_residuals`, `test_pure_schiff_excludes_blends`,
`test_pure_schiff_excludes_solvers`,
`test_schiff_benchmark_page_uses_pure_schiff_only`,
`test_light_ruc_2022_23_watchpoint_visible`, `test_stress_chart_hover_is_readable`.

**Classification: bucket 1 and bucket 4 — every failure reproduces on the exact
`origin/main` base SHA (proved by running each module in a disposable clone at
`46d1f87`, not asserted), and every one is a missing-local-scratch case.** None
are branch-owned. None are caused by an incorrect new test.

After running the CI prep step, all 29 tests in those six modules pass. **The
local core suite is green.** Nothing was skipped, weakened or loosened; the
missing step was supplied instead.

## 4. Mutation testing

Five mutations, each reintroducing the defect a different way. **All five
detected, no survivors** (`mutation_results.csv`).

Two survived on the first attempt and exposed genuinely weak tests, which were
then fixed:

- Flipping `materialize_chart_sources` back to `True` survived because the
  conftest redirect sent the reintroduced write to scratch while the test
  inspected a different root. The test now removes the redirect.
- The AppTest cases survived because `app.py`'s `load_active_run` catches every
  exception and degrades to a warning panel, so a raising loader left the tree
  untouched and the byte comparison still passed on a dashboard that rendered
  nothing. `assert_pack_loaded` now requires the pack to have actually loaded.

That second finding is the more instructive one: without it, the AppTest would
have passed while the app was broken.

## 5. Explicit promotion

In a disposable clone of the fixed branch:

- `scripts/promote_chart_sources.py` (engine `ensemble`, canonical destination,
  `mode=promote`) exited 0 and validated 21 tables.
- Reported before -> after: `0.5591936636031876 -> 0.5591936636031876` and
  `0.9230110422702978 -> 0.9230110422702978`. Values unchanged.
- **`git status` clean afterwards** — the promotion reproduces the committed
  bytes exactly, line endings included. The governed evidence is demonstrably
  reproducible from the ensemble pack.
- Run twice: byte-identical, zero files changed between runs, no `.tmp` residue.
- App boot re-checked afterwards: 22 files byte-identical.
- `--engine ar1` routes to `artifacts/diagnostics/chart_sources/ar1/`, never the
  canonical filenames.

## 6. Governed packs and value non-movement

`scripts/plan_governed_pack_rebuilds.py` initially reported `policy_runtime`
**stale**, because `chart_sources.py`, `parquet_loader.py` and
`evidence_pack.py` are digest-bound. The emitted order was followed exactly:
`policy_runtime`, then `databricks_bundle`.

`ci/policy_runtime_repin_proof.py` snapshot -> rebuild -> compare:

> **200 frames compared, 2 manifests. No governed frame moved. Every value, row
> count, column and dtype is identical; only provenance identifying the new code
> changed.**

Only `source_digest`, `source_main_sha` and `provenance` moved, in the two
manifests. `source_main_sha` pins `fa4c96b`, the committed source. The planner
then reported **every governed pack ok**.

The **uncertainty pack was not rebuilt** — the planner enforces its freshness
transitively through `policy_runtime` and did not ask for it. The recent
re-centring correction is untouched.

`governed_value_non_movement.csv` records 312 representative values at FY2026,
FY2030, FY2031 and FY2050 across both engines, covering PED VKT per capita,
Light petrol VKT, PED volume, gross PED revenue, net FED revenue, Light RUC,
Heavy RUC, Total RUC and Total NLTF revenue, plus official comparators.
Expected movement: exactly zero. Observed: zero.

A second idempotency build was not run: the planner explicitly says it is not
required, and the builder code did not change.

## 7. Databricks bundle

- Built: 1297 files, 124.71 MiB, manifest `70fe2827...`.
- Validated: **passed**, parity checks `chart_row_values: 16`,
  `extract_row65_values: 8`.
- Bundle-versus-source parity: confirmed by the validator.
- App startup inside the bundle: chart sources byte-identical.
- Not published from this branch.

**One honest gap.** Manifest re-verification *after* a real app boot still
fails, because `load_evidence_pack` continues to write
`artifacts/data_source_manifest.json` and `artifacts/*_source_table.csv`. Those
writes are pre-existing on `origin/main`, untouched here, and outside issue #31.
This change strictly reduces what startup writes; it adds nothing. Two probe
artefacts that *were* mine — the server log and `__pycache__` — were fixed.

## 8. Validators

All six edited validators executed. `validate_chart_sources`,
`validate_dashboard_data`, `validate_semantic_labels` and
`validate_light_ruc_reproducibility` exit 0. `validate_120_gates` and
`validate_80_gates` exit 1 — **identically on `origin/main`**, from missing
developer-local screenshot and schema scratch artefacts, not chart sources. Gates
101, 102, 103, 109, 110 and 114 (the chart-source gates) all PASS, reporting
"21 chart source tables exist".

## 9. Not done here

Docker lanes and hosted CI were left to the pull request, per the local-first
sequence. Nothing was merged.
