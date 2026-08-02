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

## Fail-closed behaviour

| gate | result |
| --- | --- |
| Missing cache raises with the rebuild command | **PASS** |
| Changed source digest ⇒ `stale`, load refuses | **PASS** |
| Tampered frame file refused (hash validation) | **PASS** |
| Named fast path invokes no live replay (both replays monkeypatched to raise) | **PASS**, both engines |
| Schema-version mismatch ⇒ stale | **PASS** (asserted via status contract) |

Note: `test_corrupt_frame_fails_hash_validation` copies the cache to a temp
root, so the source scan for that root also differs; the assertion therefore
accepts either the hash-validation or the stale rejection. Both are
fail-closed, but that test does not isolate hash validation on its own.

## Determinism / invalidation

| gate | result |
| --- | --- |
| Rebuild twice from identical sources | **PASS** — 0 of 72 files changed |
| Manifest excludes wall-clock timings (would break byte-identity) | **PASS** — timings printed, not committed |
| Digest covers pack content, fitted state, official vintages, conflict/macro config, builder + schema version | **PASS** — `provenance.source_hashes`, 45 external inputs captured by `sys.addaudithook` open-trace, not guessed |

## Regression suites run (all on this branch)

| suite | result |
| --- | --- |
| `test_revenue_outlook_replay_cache.py` (fast) | 13 passed |
| `test_revenue_outlook_replay_cache.py` (slow parity) | 2 passed |
| `test_view_performance_caches.py`, `test_revenue_scenario_key.py`, `test_revenue_chart_layers.py` | 67 passed |
| `test_view_invariant_sweep.py`, `test_revenue_outlook_long_run.py`, `test_vfm_long_run_composition.py`, `test_revenue_uncertainty_draws.py` | 160 passed |
| `test_chart_source_tables.py` | 7 passed |
| `test_r2_ladder.py` | 14 passed |

**263 tests passed, 0 failed.**

The full ~1,500-test suite, targeted AppTest, Playwright browser acceptance and
deployment-readiness checks have **not** been run for this stage.

## Values

No model, coefficient, scenario input, policy definition, conflict definition,
formula, unit, layer default or colour was changed. The only source edits
outside the new modules are two `list(<set>)` → ordered-tuple column selections,
which change column ORDER only, and the replay-mode wiring in `app.py`.

The uncertainty pack is untouched: not duplicated, not regenerated, not read
differently. The 10,000-draw simulation is not run at runtime, as before.
