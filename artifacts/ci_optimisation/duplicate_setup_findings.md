# Duplicate-setup findings

Section 9 of the optimisation brief expected repeated work to be the target:
repeated pack loads, repeated reference-pipeline construction, repeated AppTest
cold starts, repeated identical frame construction per parameter.

**That is largely not what this suite is doing.** The evidence is below, because
the conclusion changes which lever is worth pulling.

## What the suite already does right

| fixture scope | count |
| --- | --- |
| `scope="module"` | 91 |
| `scope="session"` | 6 |
| function-scoped (default) | 6 |

Expensive setup has already been hoisted. Only 6 test files instantiate a
Streamlit `AppTest` at all, and `tests/conftest.py` already pins
`REVENUE_OUTLOOK_CACHE_WARMER=0` specifically to stop the background warmer
burning ~20s of CPU per AppTest process.

## Where the time actually is

Measured over one clean profiling pass (1910 executed tests, 41m 53s):

| share of runtime | slowest N tests | as % of tests |
| --- | --- | --- |
| 50% | **10** | 0.5% |
| 75% | 59 | 3.1% |
| 90% | 168 | 8.8% |

| seconds | test |
| --- | --- |
| 377.4 | `test_view_invariant_sweep.py::test_actuals_are_immutable_under_every_sensitivity[ar1]` |
| 356.9 | `test_view_invariant_sweep.py::test_actuals_are_immutable_under_every_sensitivity[ensemble]` |
| 121.7 | `test_revenue_outlook_policy_runtime.py::test_every_materialised_state_equals_the_reference_pipeline[ar1]` |
| 119.4 | `test_revenue_outlook_policy_runtime.py::test_every_materialised_state_equals_the_reference_pipeline[ensemble]` |
| 57.6 | `test_quarterly_disaggregation.py::test_delayed_base_and_iran_net_revenue_quarters_reconcile_exactly...` |
| 56.4 | `test_revenue_outlook_replay_cache.py::test_replay_cache_matches_reference_exactly[ensemble]` |
| 55.4 | `test_fuel_price_scenario.py::test_fixed_finalist_replay_preserves_base_and_orders_governed_conflict...` |
| 49.6 | `test_revenue_outlook_replay_cache.py::test_replay_cache_matches_reference_exactly[ar1]` |
| 48.4 | `test_fuel_price_scenario.py::test_ar1_pack_replays_twelve_paths_and_retains_source_lineage` |
| 47.0 | `test_view_performance_caches.py::test_current_and_mbu_policy_nine_state_matrix...` |

## Why none of these is duplicate setup

### 1. `test_view_invariant_sweep.py` — 734s, 29.3% of the suite

The two headline numbers are **not** two slow tests. They are the module-scoped
`sweep_context` fixture, and pytest attributes fixture setup to the first test
that requests it. That fixture builds

    series_labels × {june_year, quarterly} × {off, fleet_med, pt_med, freight_med}

distinct `cached_revenue_outlook_view` results, once per engine, and **five**
tests then share the grid. It is already the optimisation the brief asks for.

Every cell is a distinct cache key, so nothing is recomputed. Shrinking the grid
would not remove duplicate work — it would remove coverage. The module's docstring
is explicit that the point is to walk the whole grid rather than eyeball
individual charts, and each invariant reports the exact failing
`(series, grain, sensitivity)` cell.

**Verdict: do not touch.** Attack it by not running it when the diff cannot
reach it, and by running it in parallel with the rest.

### 2. The reference-pipeline comparisons — ~350s combined

`test_every_materialised_state_equals_the_reference_pipeline` and
`test_replay_cache_matches_reference_exactly` re-run the reference pipeline and
compare a materialised pack against it. That is expensive **by design**, and
`pytest.ini` says why:

> `slow`: re-runs the reference pipeline to prove a materialised pack equals it.
> Deselect with `-m "not slow"` for a fast loop; CI runs them, because a
> materialisation nobody compares to its reference is just a cache.

Caching the reference across tests would compare a materialised pack against
itself — explicitly forbidden by section 9 of the brief, and it would silently
void the only check that the pack is not stale.

**Verdict: do not touch.** These are the assurance.

### 3. Everything else

Below the top 10, no single test exceeds 37s and the tail is genuinely flat:
1,742 of 1,910 tests together account for 10% of the runtime. There is no
population of medium-cost tests sharing redundant setup.

## Marker coverage gap (actionable)

Only **3 tests across 2 files** carry `@pytest.mark.slow`, yet 10 tests hold 50%
of the runtime. The marker is accurate about what it labels but does not label
everything expensive — notably `test_view_invariant_sweep.py`, the single
biggest item.

This is not a correctness problem (nothing is skipped that should run), but it
means `-m "not slow"` is a much weaker fast loop than it looks: deselecting
`slow` removes ~350s of a 2,506s suite while leaving the 734s sweep in place.

**Recommended, and deliberately left as a follow-up rather than done here:** mark
`test_view_invariant_sweep.py` and the `[ar1]`/`[ensemble]` reference
comparisons consistently, so `-m "not slow"` becomes a genuine fast loop. It is
left out of this change because relabelling tests alters what a developer's
habitual command selects, and that deserves its own reviewed commit rather than
riding along inside a CI refactor.

## Conclusion

The suite is not slow because it repeats itself. It is slow because it does a
large amount of genuine, load-bearing computation, concentrated in ~10 tests.

The three levers that remain, in order of value:

1. **Selection** — do not run a 734s invariant sweep for a caption change.
   `scripts/ci_plan.py` handles this and is where nearly all the hosted saving
   comes from.
2. **Parallelism** — 90% of the runtime spans 38 distinct files, so
   module-scoped parallel distribution has real headroom. Benchmarked
   separately; see `xdist_benchmark.md`.
3. **Not running it twice per change, and not on every draft push** — see
   `baseline_summary.md`, where this is over half the measured spend.

Optimising the tests themselves is fourth, and would trade assurance for
seconds.
