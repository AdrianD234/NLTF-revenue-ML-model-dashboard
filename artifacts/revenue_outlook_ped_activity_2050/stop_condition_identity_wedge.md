# Stop condition — the quarterly PED identity cannot close against rendered annuals

Reached at section 13 / section 27:

> the quarterly petrol/VKTpc/population identity cannot be preserved without an
> unapproved assumption

Evidence: `overlay_identity_wedge_audit.csv` (100 rows, both engines, both
governed scenarios, FY2026-FY2050).

## What is blocked

Only **`ped_vkt_per_capita` quarterly, FY2031-FY2050**. Everything else in the
workstream is complete and verified end to end through the real pipeline:

| series | annual | quarterly |
|---|---|---|
| `ped_vkt_per_capita` | FY2025-FY2050 ✅ | 2026Q1-**2030Q4** ❌ blocked |
| `light_petrol_vkt` | FY2026-**FY2050** ✅ | 2025Q3-**2050Q2** ✅ |

## The conflict

The joint constructor assumes the governed identity

    light_petrol_vkt_fy = ped_vkt_per_capita_fy * scenario_population_fy / 1e6

That identity holds **exactly** in the post-model constructor's own output - it
is how `scenario_population` is defined there
(`post_model_extrapolation.py:290-297`) - and the pre-overlay bridge frame
confirms it: FY2031 implied population 5.568625e6 against quarterly scenario
populations of 5.55e6-5.58e6.

It does **not** hold in the rendered annual rows. After the scenario overlays,
the ratio of implied to scenario population is:

| FY | 2026 | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2040 | 2050 |
|---|---|---|---|---|---|---|---|---|---|
| ratio | 1.00065 | 1.00250 | 1.00623 | 1.01010 | 1.01396 | 1.01396 | 1.01396 | 1.01396 | 1.01396 |

Consequence for the seam solve: the two annual constraints demand an average
population of 5.6464e6 for FY2031, which is **above every quarterly population
in that year**. With two quarters held at their native values there is no
positive solution - the 2x2 solve returns -51,136 and +54,187 - and the
constructor refuses it.

## This is pre-existing, not introduced here

The wedge accumulates across **FY2026-FY2030**, where `light_petrol_vkt` annual
rows existed before this branch, and is then flat at 1.013961 for every year
FY2031-FY2050. The post-model rows inherit the FY2030 ratio exactly, so the
seam is smooth. Nothing in this branch widened it. Merged main simply never
exercised it, because no quarterly path ran past 2030Q4 and Light petrol VKT
had no long-run Current line at all.

The overlays move the two series by different factors (FY2031: petrol +1.49%,
VKT per capita +0.09%), which is plausible as governed behaviour - an e-RUC or
EV-uptake transition can move petrol activity without moving a per-capita
demand driver by the same proportion - but it means the two series are not in
a fixed population relationship once overlaid.

## Current branch state is safe

`_post_model_ped_activity_quarters` catches `PostModelQuarterlyError` and
returns empty, so the page keeps exactly its previous quarterly coverage rather
than raising. No wrong number is published and the annual work is unaffected.

## Resolution options for the owner

**Option A - two per-year factors (tested, works).** Scale each series to its
own annual target:

    scale_vktpc = target_vktpc_fy / sum_q(raw_vktpc_q)
    scale_petrol = target_petrol_fy / sum_q(raw_petrol_q)

Measured over FY2031-FY2050, both scenarios: both annual constraints close to
≤7.3e-12, all quarters positive (minimum 328.8), and the two factors differ by
a **constant** 1.013967-1.013969 - the overlay wedge itself, not drift. The
within-year raw shape is preserved for both series.

The cost: the published quarterly identity then holds against an *effective*
population 1.4% above the scenario population, not against the scenario
population. Section 12 explicitly warns against a split that lets the two
series drift apart; this does not drift, but it is a different method from the
approved single factor, so it needs approval.

**Option B - reconcile the annual wedge first.** Establish whether the overlays
*should* preserve the identity for the PED family. If they should, the fix
belongs in the overlay layer and both the annual and quarterly views become
consistent; if they should not, Option A is the correct published method and
the wedge should be documented as governed behaviour.

**Option C - publish Light petrol VKT quarterly only.** It already reaches
2050Q2 through the existing governed Denton path, reconciling to its own
annual. `ped_vkt_per_capita` quarterly stays at 2030Q4 with the existing
short-coverage note. Smallest change, leaves the stated goal half met.

Recommendation: **Option A**, with the constant wedge recorded per year in the
quarterly provenance so a reader can see it, and Option B raised separately as
a question about the overlay layer rather than about this publication work.
