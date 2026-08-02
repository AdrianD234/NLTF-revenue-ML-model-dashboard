# Governed Instant Revenue Outlook Runtime — stage 1

Branch: `performance/revenue-outlook-instant-runtime`
Starting main SHA: `479ff2150ec532e66d0c33c7f3c852cbe03a8d04` (PR #15 merge)
Python 3.13.5 · Streamlit 1.58.0 · pandas 3.0.3 · pyarrow 24.0.0 · Windows 11 (10.0.26200)

## The measured bottleneck was not where the brief expected

The brief carried forward a historical figure of ~10.9 s for cold Revenue
Outlook view construction. Re-measured on the PR #15 merge commit, the real
cold path is **67.7 s (AR1)** and **77.4 s (ensemble)**, and it is dominated by
two functions the brief listed only in passing:

| stage (AR1, reference) | median ms | share |
| --- | ---: | ---: |
| `cached_fuel_price_scenario_replay` | 51,384 | 76% |
| `cached_treasury_baseline_macro_replay` | 9,945 | 15% |
| `cached_scenario_overlay_rows` | 4,331 | 6% |
| `import app.py` | 941 | 1% |
| pack load | 451 | <1% |
| sensitivity stage frames | 402 | <1% |
| view assembly (cold) | 147 | <1% |
| everything else | <110 | <1% |

`cProfile` shows why: both replays call
`replay_forecast_from_scenario_inputs` → `vnext_forward_forecast` →
`pipeline/vnext_forward.forward_forecast`, plus `ar1_engine.fit_production_state`.
The conflict replay alone runs 25 forward forecasts and loads joblib fitted
state. The dashboard was re-running **model fitting and forward forecasting**
on the first Revenue Outlook render of every process.

The figure itself was never the problem: PR #15 already left figure assembly at
~90 ms and the warm cached view at ~12 ms.

## Why no scenario cube was needed

Both replays take **no reader-facing control**. Their signatures are
`(signature, _pack)` and their Streamlit caches are keyed on the pack signature
alone. Every value they produce is a pure function of the promoted pack plus
the governed model state.

So the fix has **no scenario dimension at all**: one compiled entry per
(engine, pack digest). No Cartesian product, no approximation, no second
uncertainty system, and nothing about the layered chart, the bands or the
uncertainty pack is touched.

`data/revenue_outlook_replay_cache/<engine>/` holds all 35 frames of both
result dataclasses (2.0 MB per engine, 90.9k/93.8k rows). The runtime
reconstructs the exact dataclasses, so the overlay chain, the policy pair
factors, the conflict traces and every audit surface see byte-identical frames.

## Result

### Browser-visible (the number that matters to a reader)

Measured with Playwright at 1920×1080 against a freshly started local server,
from `page.goto` through clicking Revenue Outlook to the Base-case trace being
present in Plotly's own arrays.

| measurement | reference | fast | ratio |
| --- | ---: | ---: | ---: |
| cold: click → Revenue Outlook chart | 91,033 ms | 44,848 / 47,229 ms | **2.0×** |
| cold: total (goto → RO chart) | 93,749 ms | 46,783 / 49,180 ms | 2.0× |
| **warm: away and back to RO chart** | 111 ms | **129 / 112 ms** | ~1× (already fast) |

**The headline is 2.0× browser-visible, not 9–11×.** The 9–11× figure below is
Python-side and covers only the narrow call path this change touches; that path
is roughly 7 s of a ~45 s cold page. The rest of the cold page - the VFM
Fast/Slow envelope (which runs the overlay chain twice more), the detail,
reconciliation, stack and composition frames, and every section below the chart
- is untouched by this PR and is where the remaining ~38 s sits.

Warm navigation at ~120 ms is the dominant experience after the first visit,
and it was already fast before this change.

### Python-side, narrow benchmark path

| engine | cold path before | cold path after | ratio |
| --- | ---: | ---: | ---: |
| ar1 | 67,777 ms | 7,462 ms | 9.1× |
| ensemble | 80,962 ms | 7,087 ms | 11.4× |

This benchmark calls the specific cached functions in sequence; it is a valid
measure of the replay work removed (61.3 s → 0.9 s) but it is **not** a measure
of the page.

Warm cached view is unchanged at ~12 ms (it was already fast).
Fresh-process runs, 3 samples per engine (1 for reference, which costs ~70 s a
run), p95 7,588 ms (ar1) / 7,208 ms (ensemble). See
`performance_before_after.csv` and `stage_timings.csv`.

Fast-mode stage breakdown (AR1, median of 3 fresh processes):

| stage | ms |
| --- | ---: |
| scenario overlay rows | 4,615 |
| `import app.py` | 939 |
| compiled replay load (both results) | 875 |
| pack load | 471 |
| sensitivity stage frames | 326 |
| view assembly (cold) | 138 |
| everything else | <95 |

The source digest that guards the cache hashes ~48 MB across ~640 files
(~320 ms). It is computed **once per pack signature** and threaded into the
loader rather than recomputed per lookup; doing that removed ~650 ms.

## Two source defects found and fixed

1. **Non-deterministic column order.** `conflict_gdp_input_audit` selected
   columns via `list(<set literal>)`, so `gdp_input_audit` came out with a
   different column ORDER in every process (string set iteration depends on
   `PYTHONHASHSEED`). Values were always identical, but the schema was not
   reproducible — which breaks committed artifacts, diffs and cross-platform
   replay parity. The same pattern in
   `_first_conflict_input_divergence_period` is fixed alongside it. Both are
   ordering-only; no value moves.

2. **Object-column dtype loss.** Several replay frames carry object columns
   holding mixed Python float / str cells, all-`pd.NA` cells, or uniformly
   float cells. Arrow rejects the first and silently retypes the other two.
   The codec records a per-cell type tag and restores each exactly — including
   the distinction between `None`, `pd.NA`, `pd.NaT` and `float('nan')`, which
   `assert_frame_equal` treats as three different values.

## Invalidation covers the calculation code, not just the data

The digest hashes the pack's own `output_hashes`, the governed fitted state,
the official vintage spines, the conflict/macro configuration — **and the 33
repo-local modules that actually compute the replays**, including
`fuel_price_scenario.py`, `forecast_runner.py`, `mbu26_source_spine.py`,
`conflict_gdp_paths.py` and `pipeline/vnext_forward.py`.

That module list is not hand-maintained. The builder captures it from
`sys.modules` **after** running both replays, so it comes from the real import
graph; the runtime re-hashes exactly the modules the cache recorded. A module
added later must be imported by one of these, whose own hash then changes, so
the closure stays complete.

Without this, editing `fuel_price_scenario.py` and forgetting to bump
`BUILDER_VERSION` would leave a cache built by the *old* calculation still
passing its digest, and the dashboard would serve superseded results
indefinitely. The stale message names the edited module.

## Runtime modes

`REVENUE_OUTLOOK_RUNTIME_MODE` = `reference` | `fast` | `shadow`.

- absent or empty → `fast`;
- an explicitly supplied unknown value **raises** — silently treating
  `REVENUE_OUTLOOK_RUNTIME_MODE=refrence` as "fast" would hide exactly the
  misconfiguration the operator was trying to fix;
- `reference` restores the live replay unchanged;
- `shadow` serves the compiled result **and** runs the live replay once per
  (engine, digest) per process, compares all 35 frames exactly, and on any
  discrepancy writes `shadow_mismatch.md` and raises. Verified end to end: a
  shadow lookup takes 56 s (it really replays), the second is 0.7 ms (cached),
  and the verdict is `35 frames identical`.

A missing, stale or corrupt cache **fails closed** — never a silent fallback to
the 52 s path, never a stale value. The Revenue Outlook page checks the cache
before any chart work and renders a governed panel naming the reason and the
rebuild command, rather than a raw traceback.

Rebuild: `python scripts/build_revenue_outlook_replay_cache.py --all`

## What is NOT done

The remaining cold cost is `cached_scenario_overlay_rows` at **4.55 s**, now
56% of the fast path. Profiling attributes it to two pandas hot loops inside
governed calculation code:

- `append_fuel_price_scenario_to_chart_rows` (~2.5 s) — `_leaf_delta` runs 828
  boolean-mask filters, each re-running `astype(str)` over the group, plus a
  `.at[]` scalar write loop and a `.apply(axis=1)` identity key.
- `apply_treasury_macro_to_chart_rows` (~0.7 s).

These are exactly-optimisable (index the lookups, hoist the casts) but they sit
inside `fuel_price_scenario.py` rather than in a materialisable pure function,
so they carry a different regression profile from this change and are left to a
follow-up. Until they are addressed:

- ✅ target A (navigate to Revenue Outlook in a running app, p50 ≤ 600 ms) —
  **met at ~120 ms** browser-visible;
- ❌ target E (fresh process → first meaningful chart, p95 ≤ 5 s) — **~46 s**
  browser-visible. Removing the replays took ~46 s out of it; the remaining
  ~45 s is other work this PR does not touch;
- ❌ target B on a cold key (first computation of a not-yet-cached named
  scenario) — the overlay chain alone is ~4.6 s.

The ~38 s gap between the 7.2 s narrow benchmark and the ~45 s cold page has
NOT been attributed stage by stage. The prime suspect is
`cached_view_cone_band`, which runs the whole overlay chain twice more for the
VFM Fast and Slow bounds, plus the detail/reconciliation/stack/composition
frames and the sections below the chart. That attribution is the first job of
the vectorised-overlay follow-up, not something this PR resolves.

Browser acceptance for this change lives in
`tests/test_playwright_replay_cache_runtime.py` (marked `e2e`).
