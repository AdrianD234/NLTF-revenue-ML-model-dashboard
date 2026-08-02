# Validation — compiled Revenue Outlook replay cache

## Parity

| gate | result |
| --- | --- |
| Every compiled frame equals the live replay, both engines, fresh process | **PASS** — 35/35 frames per engine, `assert_frame_equal(check_exact=True)` |
| Post-overlay `chart_rows` identical (fast vs reference, AR1) | **PASS** — 4198×96, exact |
| Overlay audit frames identical (uptake, e-RUC, FED policy, conflict) | **PASS** — exact |
| Builder refuses to publish unless every frame round-trips | **PASS** — enforced in `build_engine`, and it did block two real encoding defects |

The exhaustive parity test is
`tests/test_revenue_outlook_replay_cache.py::test_replay_cache_matches_reference_exactly`
(marked `slow`; it re-runs both live replays, ~150 s for both engines). It runs
in a **separate process** from the build, so it also proves cross-process
reproducibility — this is what caught the `PYTHONHASHSEED` column-order defect.

## Cross-environment reproducibility (a finding, not a cache property)

Comparing the compiled cache (Python 3.13 / numpy 2.4.6 / Windows) against a
reference recomputed under CI (Python 3.11 / Linux) shows **17 of 35 frames
differ**, by 7.28e-12 to 9.54e-07 absolute (~1.3e-13 relative). Full list in
`cross_environment_drift.csv`.

Seven of those are the **raw forward model outputs** (`future_forecasts`,
`component_forecasts`, `superseded_component_forecasts`). So this is the
model's forward computation not being bit-reproducible across
interpreter/library versions — **not** a property of the compiled cache, whose
serialisation is exact and separately gated.

Nothing in the repo had measured this before: the existing "Replay parity" CI
jobs write one fingerprint per OS and never compare them, so they cannot fail
on a value difference.

All 17 sit inside `revenue_outlook.py::_values_close(abs_tol=1e-6,
rel_tol=1e-9)` — the closure tolerance every revenue formula here already has
to satisfy — with ~7,700× margin. That governed line is what the
cross-environment gate adopts; exact equality is still required, with no escape
hatch, wherever the cache was built.

**Open governance question:** the committed cache freezes one environment's
floats into a Linux-hosted app. At 1e-13 that is far inside anything governed,
and it arguably improves determinism (every viewer sees the same committed
numbers rather than values varying with the host's libraries). Building the
cache in CI on Linux is the alternative. Not settled here.

## Fail-closed behaviour

| gate | result |
| --- | --- |
| Missing cache raises with the rebuild command | **PASS** |
| Changed source digest ⇒ `stale`, load refuses | **PASS** |
| **Edited replay module alone** (no data change, no version bump) ⇒ `stale`, message names the module | **PASS** |
| Calculation code is in the digest (33 modules, incl. `fuel_price_scenario`, `forecast_runner`, `mbu26_source_spine`, `conflict_gdp_paths`, `pipeline/vnext_forward`) | **PASS**, both engines |
| Tampered frame refused **specifically by frame-hash validation** | **PASS** — asserts `failed hash validation` and names `fuel.annual_factors` |
| Named fast path invokes no live replay (both replays monkeypatched to raise) | **PASS**, both engines |
| Schema-version mismatch ⇒ stale | **PASS** (asserted via status contract) |
| Absent / empty mode ⇒ `fast`; explicit unknown value raises | **PASS** |
| Missing cache produces a governed page message naming the rebuild command | **PASS** |
| Shadow mode really replays and compares | **PASS** — 56 s first lookup, 0.7 ms cached, `35 frames identical` |

`test_corrupt_frame_fails_hash_validation` now reuses the committed manifest's
own digest and materialises the recorded modules under the temp root, so the
load reaches frame hashing and the assertion proves frame-hash rejection
specifically rather than accepting an unrelated stale-source result.

## Determinism / invalidation

| gate | result |
| --- | --- |
| Rebuild twice from identical sources | **PASS** — 0 of 72 files changed |
| Manifest excludes wall-clock timings (would break byte-identity) | **PASS** — timings printed, not committed |
| Digest covers pack content, fitted state, official vintages, conflict/macro config, builder + schema version | **PASS** — `provenance.source_hashes`, 45 external inputs captured by `sys.addaudithook` open-trace, not guessed |

## Browser acceptance

`tests/test_playwright_replay_cache_runtime.py`, Chromium, server on :8501:

| gate | result |
| --- | --- |
| Revenue Outlook opens on the compiled cache, plots real values, no console errors, no fail-closed panel | **PASS** |
| A named value-changing selection moves the plotted values (read from Plotly arrays, waited on VALUES not trace names) | **PASS** |
| No horizontal overflow at 1920×1080 and 1440×900 | **PASS** |
| Missing cache ⇒ governed panel naming the rebuild command, no traceback, no chart, no silent fallback | **PASS** (verified live: cache dir renamed, fresh server, page text asserted, then restored) |

Deliberately independent of `test_playwright_dashboard.py`'s Revenue Outlook
contract, which is stale (see below).

## Pre-existing e2e staleness (NOT caused by this branch)

5 tests in `tests/test_playwright_dashboard.py` fail on this branch **and fail
identically in `reference` mode**, which is the live-replay path — i.e. main's
behaviour. They assert a pre-PR #15 chart contract: an allowed trace set with
no 50%/80% conditional bands and no `BEFU26 official`, and a
`"Select legend items"` button that PR #15 replaced with the unified "Show on
chart" multiselect. The file was last touched by `d1f3535`, a mid-PR #15 WIP
commit. `pytest.ini` sets `addopts = -m "not e2e"`, so CI never ran them and
the staleness shipped with PR #15.

## Regression suites run (all on this branch)

| suite | result |
| --- | --- |
| `test_revenue_outlook_replay_cache.py` (fast) | 13 passed |
| `test_revenue_outlook_replay_cache.py` (slow parity) | 2 passed |
| `test_view_performance_caches.py`, `test_revenue_scenario_key.py`, `test_revenue_chart_layers.py` | 67 passed |
| `test_view_invariant_sweep.py`, `test_revenue_outlook_long_run.py`, `test_vfm_long_run_composition.py`, `test_revenue_uncertainty_draws.py` | 160 passed |
| `test_chart_source_tables.py` | 7 passed |
| `test_r2_ladder.py` | 14 passed |
| **complete local suite** (`pytest -q -p no:randomly`) | **1546 passed, 50 skipped, 41 deselected, 0 failed** (28m52s) |
| `compileall` | clean |
| conflict scenario extract validation | **21/21 passed** |
| Streamlit deploy readiness | PASS |
| replay-seed diagnostic | PASS (0 missing supported keys, 0 reclassified) |
| GDP sign-guard audit | written, no violations |
| replay parity fingerprint | 248 inputs hashed, 3576 rows fingerprinted |

An earlier full-suite run reported 16 failures. Those were an artefact of
editing `app.py` **while that run was in progress**: every one of the 16 is a
source-inspection test calling `inspect.getsource(app.render_revenue_outlook_page)`,
which reads the file from disk at call time, so the source no longer matched
the code object loaded at collection. The clean re-run with no concurrent edits
shows 0 failures. No code change was needed and none was made.

## Values

No model, coefficient, scenario input, policy definition, conflict definition,
formula, unit, layer default or colour was changed. The only source edits
outside the new modules are two `list(<set>)` → ordered-tuple column selections,
which change column ORDER only, and the replay-mode wiring in `app.py`.

The uncertainty pack is untouched: not duplicated, not regenerated, not read
differently. The 10,000-draw simulation is not run at runtime, as before.
