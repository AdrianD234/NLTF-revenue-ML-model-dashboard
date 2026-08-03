# Where the time goes when a reader changes the 12c policy

Measured on the PR #16 merge commit (`48a499b`) plus the no-uplift correction
described below, in fresh interpreters, three samples per engine.

    python scripts/profile_revenue_outlook_policy_toggle.py --repeats 3

Raw numbers: `policy_toggle_profile_before.csv`, `policy_toggle_profile_raw.json`.

## The headline correction

The handoff asked us not to assume the ~4 s overlay chain is caused by the
policy selection. It is not, and the 4 s figure is itself low.

| Measurement | ar1 | ensemble |
|---|---|---|
| First selection of a policy state (end to end) | **13.53 s** | **13.36 s** |
| published → delayed | **13.00 s** | **12.74 s** |
| delayed → no uplift | **13.27 s** | **12.89 s** |
| Return to an already-computed state | 22.7 ms | 19.5 ms |
| Repeat of a previously selected state | 21.4 ms | 21.5 ms |

Two things follow, and they point in opposite directions:

* A policy switch costs **~13 s**, roughly three times the assumed 4 s.
* **Applying the policy is 0.32 s of it — 2.4%.**

So the cost is not the policy arithmetic. It is that
`current_fed_policy_state` is a field of `RevenueScenarioComputationKey`, and
every cache downstream of that key is invalidated with it. The reader pays for
the macro overlay, the uptake allocation, the conflict append, the detail
alignment, the formula rebuild, the stack rebuild and the VFM Fast/Slow
envelope — none of which the policy selection changed the *method* of.

## Stage breakdown

Measured with the Streamlit caches bypassed, so each stage is timed on its own
rather than inferred from a total (median ms, ar1; ensemble within 3%):

| Stage | ms | Class |
|---|---:|---|
| conflict append | 2,362 | policy-dependent |
| detail alignment | 1,024 | policy-dependent |
| formula rebuild | 641 | policy-dependent |
| macro overlay | 586 | policy-dependent |
| stack rebuild | 459 | policy-dependent |
| **policy factor application** | **322** | **policy-dependent** |
| uptake allocation | 312 | policy-dependent |
| chart-row construction | 8 | display-only |
| uncertainty lookup | 1 | display-only |

The stages above sum to ~5.7 s, against a ~13.5 s end-to-end switch. The gap
is the **MoT VFM Fast/Slow envelope**: `cached_view_cone_band` re-runs the
entire overlay chain twice more, once per composition preset, and it inherits
the live policy state, so a policy switch pays the chain three times in total.

Key-independent work, paid once per process and *never* re-paid on a switch:

| Stage | ar1 ms | ensemble ms |
|---|---:|---:|
| compiled replay cache load (PR #16) | 860 | 806 |
| promoted pack load | 458 | 455 |
| sensitivity stage frames | 296 | 298 |
| FED uplift factor tables | 73 | 106 |
| uncertainty pack load | 5 | 5 |

Materialising any of these again would buy nothing — PR #16 already removed
the replay cost, and the rest is one pack read per process.

## Why "return to a previous state" is already fast, and why that is not enough

Returning to an already-selected state costs ~21 ms, because
`cached_revenue_outlook_view` holds 16 entries and three policy states fit
comfortably. Within one warm process the problem is already solved.

It is not solved anywhere else:

* every new process pays ~13.5 s again for each state a reader visits;
* the container restarts, and the first reader after a restart pays it;
* a reader comparing all three states pays it three times.

That is the case for materialising: the states are finite (three Current, three
official comparator), the outputs are deterministic given the promoted pack,
and nothing about them depends on who is looking.

## Classification of the other finite dimensions

| Dimension | Values | Classification |
|---|---|---|
| engine | ar1, ensemble | **required cache dimension** |
| Current 12c policy | published, delayed_6m, no uplift | **required cache dimension** |
| official comparator policy | published, delayed_6m, no uplift | **required cache dimension** |
| VFM composition preset (envelope) | fast, slow | **materialised frames**, not a dimension — the presets are fixed |
| official comparator vintage id | registry vintages | **cheap exact post-cache overlay** — a row filter over the same values |
| official comparator overlay | on/off | **cheap exact post-cache overlay** — same |
| selected series / grain / FED path / traces | many | **display-only** |
| PED bridge mode | pinned to `raw_model` | **pinned** — the selector was retired; the page always writes the default |
| bridge vintage | from the pack manifest | **pinned** — identity-only in the key, no reader indexes it |
| long-run schedule / shape vintage | pack default + analyst previews | **pinned to the pack default**; a preview selection gets the reference path |
| uptake basis, custom EV levers, e-RUC levers, sensitivities, PED retention, Heavy-BEV | unbounded / continuous | **outside the catalogue** — reference path required |

Materialised: **9 states per engine, 18 total.** The full Cartesian product over
every value-changing control — the three uptake bases plus a 13-dimensional
continuous custom lever set, five levels on each of four sensitivity families,
the e-RUC lever block, two boolean sensitivities, four long-run schedules and
the shape vintages — is unbounded, and even fixing the continuous levers to
their presets exceeds 10⁵ combinations per engine. The runtime refuses those
rather than approximating them.

## A defect the profiling exposed

The no-uplift state could not be profiled at first: it **raised** on both
engines.

    ValueError: Aligned chart/detail formula mismatch for current_basecase,
    FY2031, net_mvr_revenue: chart=417.1893944133222, rebuilt=475.330338182.

`apply_fed_rate_policy_to_chart_rows` falls back to the governed scalar rate
ratio beyond the fixed-finalist replay window (FY2030), so a permanent rate
change does not vanish from the long run. That intent is right; the scope was
not. The fallback applied to *every* series without a pair factor, so at the
FY2030/FY2031 seam:

| Series | FY2030 ratio | FY2031 ratio (before fix) |
|---|---:|---:|
| `gross_ped_revenue` | 0.8776 | 0.8777 |
| `light_ruc_net_revenue` | 0.8774 | 0.8777 |
| `ped_vkt_per_capita` | **1.0058** | **0.8777** |
| `light_ruc_net_km` | **1.0057** | **0.8777** |
| `light_bev_ruc_net_km` | **1.0000** | **0.8777** |
| `net_mvr_revenue` | **1.0000** | **0.8777** |

Only the first two are continuous, and they are the only rate-priced ones. The
rest were wrong in three distinct ways: removing an excise increase makes fuel
cheaper, so a 12% *fall* in VKT per capita has the wrong sign; BEV and PHEV
kilometres moved despite the governed "no approved class-specific charge
elasticity" contract; and motor-vehicle registration revenue was scaled by the
petrol excise ratio, which broke
`net_mvr_revenue = mvr_revenue_net_admin_coo - mvr_refunds` and is what made
every no-uplift render raise.

`model_dashboard/rate_paths.py` now scopes the fallback to the series the rate
governs (`_RATE_PRICED_LONG_RUN_SERIES`: gross petrol excise, the five nominal
RUC collection leaves, and the chart-carried RUC aggregates). After the fix all
three states close on both engines, revenue stays continuous across the seam,
and activity holds at the published path beyond the replay window instead of
flipping sign.

Unaffected: `published` applies no counterfactual at all, and `delayed_6m`
carries factors only for FY2027, so `factors.get(fy, 1.0)` was already 1.0
beyond FY2030 and the fallback never fired. The committed offline uncertainty
pack was built at `delayed_6m` and is byte-unchanged.
