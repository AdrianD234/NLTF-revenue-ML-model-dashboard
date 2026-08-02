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

| engine | cold path before | cold path after | ratio |
| --- | ---: | ---: | ---: |
| ar1 | 67,777 ms | 7,462 ms | 9.1× |
| ensemble | 80,962 ms | 7,087 ms | 11.4× |

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

## Runtime modes

`REVENUE_OUTLOOK_RUNTIME_MODE` = `reference` | `fast` | `shadow`
(default `fast`). `reference` restores the live replay unchanged, so the
pre-existing path stays available for parity work. A missing, stale or corrupt
cache **fails closed** with the rebuild command — it never falls back silently
to the 52 s path and never serves stale values.

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

- fresh-process target E (p95 ≤ 5 s) is **not yet met** — currently ~7.2-7.6 s;
- warm navigation and display-only interactions (targets A, and B on a cache
  hit) are met — ~12 ms view + ~90 ms figure;
- **first** computation of a not-yet-cached named scenario still costs ~4.6 s,
  so target B on a cold key is not met.

No browser-visible Playwright acceptance run is included in this stage; the
timings above are Python-side and are labelled as such.
