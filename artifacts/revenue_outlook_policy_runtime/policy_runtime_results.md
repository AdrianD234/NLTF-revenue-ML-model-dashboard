# Materialised policy runtime — results

Measured on the isolated worktree at `48a499b` + this branch, three fresh
interpreters per engine.

    python scripts/build_revenue_outlook_policy_runtime.py --all
    python scripts/benchmark_revenue_outlook_policy_runtime.py --repeats 3

Raw numbers: `policy_runtime_benchmark.csv`, `policy_runtime_benchmark_raw.json`.

## Against the targets

| Measurement | Target | ar1 p95 | ensemble p95 | Met |
|---|---|---:|---:|:--:|
| Pure policy-state lookup | ≤ 100 ms | **33.4 ms** | **33.4 ms** | ✅ |
| Policy switch API (incl. selected-series filtering + bands) | ≤ 200 ms | **58.3 ms** | **57.4 ms** | ✅ |
| First selection of a state, end to end | < 500 ms | **95.1 ms** | **96.6 ms** | ✅ |
| Repeat of a previously selected state | < 500 ms | **9.8 ms** | **10.1 ms** | ✅ |

Medians are far lower than p95 because the p95 is dominated by the *first*
touch of each state, which pays the parquet read; the median lookup is 0.01 ms
(a dict hit) and the median switch is 8.8 ms. Both are reported, because
quoting only the warm number would be measuring the memoisation rather than
the design.

Against the reference path this is **13.5 s → 95 ms on first selection**, a
~140× reduction, and the cost no longer returns when the process restarts.

## Resources

| | ar1 | ensemble |
|---|---:|---:|
| Cold resource load (open the pack) | 56.4 ms | 54.1 ms |
| States materialised | 9 | 9 |
| Rows materialised | 432,732 | 432,732 |
| Policy-aware band rows | 3,000 | 3,000 |
| On disk | 9,395 KB | 9,396 KB |
| Peak resident, all three policy states decoded | 2,674 KB | 2,674 KB |
| Reference cost avoided per process | 148.2 s | 145.4 s |

18 states total, 18.8 MB committed.

## What was NOT built

The full Cartesian product over every value-changing control is unbounded —
`custom_ev_levers` alone is 13 continuous inputs, and the e-RUC block adds
five more. Even collapsing every continuous lever to its preset and counting
only the discrete controls (3 uptake bases × 5⁴ sensitivity levels × 2 PED
retention × 2 Heavy-BEV × 4 long-run schedules × the shape vintages × 3 × 3
policy states × 2 engines) exceeds **10⁵ combinations per engine**.

What is materialised instead: the two finite policy dimensions (3 × 3), per
engine, at the governed default of every other control. Anything else returns
`reference_path_required` with the field that differs named in the message.

## Frames per state

| Frame | Purpose |
|---|---|
| `chart_rows` | the overlay chain output — every trace, grain and series |
| `line_reconciliation` | aligned detail, built against one official vintage |
| `formula_residuals` | identity closure per (scenario, FY, series) |
| `stack_components` | composition stack |
| `bridge_components` | gross-to-net bridge |
| `policy_audit` | what the policy adjusted, and by how much |
| `vfm_fast_chart_rows` | MoT VFM Fast composition under this policy state |
| `vfm_slow_chart_rows` | MoT VFM Slow composition under this policy state |

The last two exist because `cached_view_cone_band` re-runs the whole overlay
chain twice more and inherits the live policy state — roughly half the switch
cost. The presets are fixed, so they are two more frames, not a new catalogue
dimension.

### One asymmetry worth knowing about

The official-comparator vintage selection is a genuine post-cache row filter
for `chart_rows` and the two VFM frames: the overlay chain computes every
vintage's rows and the selection decides which are shown.

It is **not** for the aligned detail frames.
`cached_aligned_scenario_detail_frames` filters the chart rows *before*
aligning, so the line reconciliation, residuals and stack are built against
one vintage — 5,080 / 7,221 / 9,362 line rows at the default vintage / MBU26 /
analyst overlay. Those are different computations, not filters of one.

So the pack records `detail_frame_vintage_scope`, and `policy_detail_frames`
raises for any other vintage or with the overlay on, naming the scope it was
built at. `policy_chart_rows` keeps working for those keys, because for chart
rows the filter really is exact.

## Policy-aware bands

`policy_band_dependency_audit_<engine>.csv` records, for every (series, FY),
whether the central value changes under policy, whether the rate changes,
whether the activity changes, whether the band should change, and why.

For ar1, over 1,040 (series, FY) pairs:

| Band should change | Reason | Rows |
|---|---|---:|
| no | not priced by the fuel rate and no activity response | 672 |
| no | rate-priced but outside every affected year | 13 |
| yes | central moves through a governed identity term | 192 |
| yes | rate-priced leaf: the collection rate changed, volume did not | 131 |
| yes | activity responded inside the fixed-finalist replay window | 20 |
| yes | rate and the modelled activity response both changed | 12 |

Two cases worth reading together:

* `ped_vkt_per_capita` — the band **moves** in FY2027–FY2030, where the
  fixed-finalist replay carries a modelled demand response, and is
  **identical** from FY2031, where the policy does not touch the series. That
  is the handoff's rule holding in both directions: unchanged bounds on an
  unchanged series are the correct answer, and they arise here by
  construction, because the same draws propagate through the same identities
  onto the same centre.
* `net_mvr_revenue` — never moves under any policy state. Registration revenue
  is not priced by the fuel rate.

Methodology is unchanged from PR #15: the same 10,000 seeded draws, the same
three parent shocks, the same Gaussian copula on the shrunk Spearman rank
correlation, the same monotone quantile map, the same FY2030 evidence seam and
FY2031–FY2050 plateau, and `FORMULA_DEFINITIONS` evaluated draw by draw. The
only policy-dependent input is the central path the draws are applied to. No
aggregate endpoint is ever rescaled by a ratio.

Proof rather than assertion:
`test_delayed_state_reproduces_the_committed_offline_uncertainty_pack`
reproduces every one of the 1,000 committed band rows in
`data/revenue_outlook_uncertainty/` to 1e-9, from the policy-aware
propagation, at the production state the committed pack was built under. That
pack is byte-unchanged on this branch.

## Invalidation

The manifest digest chains:

* the promoted pack's own per-file hash map and schema version;
* the PR #16 compiled replay cache's `source_digest` and output hashes;
* the uncertainty pack's scenario-key digest, seed and draw count;
* the policy factor configuration (`fed_rate_paths.csv`), the official-vintage
  registry and spine, the VFM base shares, and the June-year error source;
* every repo-local calculation module **plus `app.py`**;
* the schema version.

`app.py` matters specifically: the overlay chain that produces these states
lives there, and the inherited PR #16 hashing covers only `model_dashboard/`
and `pipeline/`. Without it an edit to the chain would pass the digest and the
pack would serve superseded rows indefinitely.

Missing, stale or corrupt fails closed with:

    python scripts/build_revenue_outlook_policy_runtime.py --all
