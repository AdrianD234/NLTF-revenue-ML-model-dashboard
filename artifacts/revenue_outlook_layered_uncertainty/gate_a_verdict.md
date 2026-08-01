# Gate A — post-P0 central-path reconciliation

**Verdict: the corrected central path closes. No further central-value changes
are needed, and none were made.**

Builders:
`scripts/build_post_p0_central_reconciliation.py`,
`scripts/build_scenario_key_collision_audit.py`

---

## 1. Result

Both engines, every governed Current scenario (`current_basecase`,
`current_comparison_1`), FY2026–FY2050, nine tracked series, four independent
views of the same number:

| | |
|---|---|
| rows compared | 2 250 |
| rows with more than one source (i.e. actually cross-checked) | **2 250** |
| residuals above the governed 1e-6 tolerance | **0** |
| official published rows changed | **none** (BEFU26 and MBU26 row counts and value sums byte-equal to the committed CSVs on both engines) |

Views compared: chart rows · line reconciliation · stack components ·
`FORMULA_DEFINITIONS` recomputed from its own leaves. The derived aggregates
(`gross_ruc_revenue`, `ruc_revenue_net_admin`, `total_ruc_net_revenue`,
`total_fed_ruc_net_revenue`, `total_nltf_net_revenue`) are each checked against
a fresh recomputation, so this is not four copies of one number.

The builder asserts non-vacuity and exits non-zero on any surviving residual or
any moved official row. It caught a bad join on the first run (`source_path`
carries the display trace name, not the scenario id) rather than passing on an
empty selection.

Per the scope rule: **case 1 — the path closes, proceed.**

---

## 2. A correction to what I reported earlier

I previously said the pre-fix state showed *"a Heavy RUC line that did not
agree with its own totals."* **That was wrong**, and it changes nothing about
whether P0 was right, but it should not stand.

The Heavy-BEV overlay is a **value-preserving reclassification**, measured per
leaf at FY2030 basecase:

| series | Heavy-BEV off | Heavy-BEV on | delta |
|---|---|---|---|
| `heavy_ruc_net_revenue` | 1561.934656 | 1547.701392 | **−14.233264** |
| `heavy_bev_ruc_net_revenue` | 32.847769 | 47.081032 | **+14.233264** |
| `gross_ruc_revenue` | 3407.646379 | 3407.646379 | 0 |
| `total_ruc_net_revenue` | 3253.937372 | 3253.937372 | 0 |
| `total_nltf_net_revenue` | 6515.261717 | 6515.261717 | 0 |

The revenue reclassification nets to exactly zero at FY2030, FY2040 and FY2050.
The aggregates being unchanged is therefore **correct by construction**, not a
broken rollup. Gate A's reconciliation closes in *both* states, which is why
the pre-fix comparison row also reports zero residuals.

My earlier claim came from summing a hand-picked list of components outside the
governed registry (`FORMULA_DEFINITIONS` defines
`gross_ruc_revenue = light + heavy + light_bev + heavy_bev + phev + refunds`,
which my list omitted) and then over-reading the aggregate-stability column of
the propagation table. The corrected reading is recorded in
`heavy_bev_transfer_audit.csv` and in a correction note inside
`heavy_bev_rollup_propagation_audit.csv`.

The owner's own hypothesis — *"the totals were already consistent with
Heavy-BEV Off, while the displayed Heavy line was wrong"* — is also not quite
right for the same reason: the totals are consistent with **both** states.

### What is still true, and is the actual case for P0

- The collision was real. `bool("BEFU26")` switched Heavy-BEV reclassification
  **on** in every production render, against its own documented "Off by
  default" and the settled `HEAVY_RUC: not_reclassified` contract. Nobody chose
  that; a slot did.
- The **chart** carries `heavy_ruc_net_km` and `heavy_ruc_net_revenue` but not
  their `heavy_bev_*` counterparts. So a reader saw Heavy RUC 14.23 lower with
  no visible destination for it — the data was coherent, the *displayed story*
  was not.
- P0's value impact is exactly those two chart series, 100 rows across both
  engines, and nothing else.

---

## 3. One observation, not fixed here

The reclassification is value-preserving on **revenue** but not on
**kilometres**:

| series | off | on | delta |
|---|---|---|---|
| `heavy_ruc_net_km` | 4230.412229 | 4191.862234 | **−38.549995** |
| `heavy_bev_ruc_net_km` | 88.956869 | 88.956869 | **0** |

38.55 million km leave the conventional Heavy series and do not arrive in
`heavy_bev_ruc_net_km`, while the corresponding revenue does arrive in
`heavy_bev_ruc_net_revenue`.

This may be intended — `heavy_bev_ruc_net_km` could be defined from a separate
fleet-share source rather than as the destination of the reclassification — so
it is **reported, not changed**. It only manifests when Heavy-BEV is
explicitly switched on, which after P0 is never the default. Deciding it would
mean touching the composition architecture, which under the scope rule is
**case 3: stop for owner review**.

It also matters for the uncertainty engine: if a draw-level identity is ever
written for Heavy kilometres, this is the row it will fail on.
