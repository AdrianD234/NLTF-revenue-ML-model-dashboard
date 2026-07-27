# Revenue Outlook pack provenance: the metadata difference is non-material

**Question:** did the committed pack and the promote → rebuild route consume the
same governed source content?

**Answer: yes.** The difference is which of two coexisting generator functions
ran, not what they consumed.

## The two phrases are two live functions, not two eras

Both strings entered in the same commit, `ecf50d7` "Add repo-local Revenue
Outlook scenario provenance", and both remain live in
`model_dashboard/scenario_inputs.py`:

| Function | Line | `source_policy` |
|---|---|---|
| `materialize_scenario_inputs()` | 239 | `committed scenario input artifacts only; ...` |
| `combine_scenario_input_dirs()` | 327 | `combined committed scenario input artifacts; ...` |

The committed pack was produced by materialising **both workbooks in one call**.
`promote_revenue_outlook_from_workbooks.py` materialises each workbook then
merges, so it takes the combine path. Same inputs, different assembly order.

## Source inventories are identical

| Field | Committed | Candidate | Same |
|---|---|---|---|
| `scenario_input_cells` | 15,472 | 15,472 | yes |
| `scenario_input_long` | 15,200 | 15,200 | yes |
| `scenario_input_wide` | 600 | 600 | yes |
| `scenario_feature_lineage` | 44,800 | 44,800 | yes |
| Workbooks | 2 | 2 | yes |
| Workbook SHA-256, both scenarios | — | — | **identical** |
| Scenario names and roles | — | — | identical |
| Schema version | `nltf-scenario-input-materializer-v1` | same | yes |
| Sheet inventory count | 10 | 10 | yes |

## Difference classification

| Difference | Classification | Material | Treatment |
|---|---|---|---|
| `source_policy` wording | Descriptive metadata | No | Adopt new wording with a version bump |
| `source_manifests` key (candidate only) | Additive lineage from the combine path | No | Keep; it records more provenance, not less |
| `raw_workbook_size_limit_bytes` (committed only) | Path of the single-materialise branch | No | Document as branch-specific |
| `raw_repo_relative_path` values | **My artefact** - promoting from already-prefixed raw workbooks double-prefixes the hash | No | De-prefix originals before promoting; verified to disappear when promoting in place |
| Two runtime-contract checkpoints | Downstream of the Light RUC value change | No | Re-promote alongside the pack |
| Numeric values | Light RUC and its governed cascade only | Expected | 846 rows, max 0.412%, inside the 0.48% envelope |

MBU26, actuals and historical actuals: **unchanged**, verified by
`scripts/light_ruc_repromotion_audit.py` stop conditions.

## Conclusion: Outcome A/B, no original builder needed

The source content is provably identical, so the pack difference is descriptive
metadata plus the value change the Light RUC fix intends. This qualifies as a
governed generator migration rather than a provenance mystery.

To finish, someone with authority should approve:

1. designating two-step `promote → rebuild` as the canonical generation route;
2. a pack/generator version bump and a one-time migration note;
3. re-promoting the pack, its frozen hashes and the two runtime-contract
   checkpoints, retaining old and new hashes and the headline impact table.

Not done here: that approval is a governance decision, and the migration note
should be written by whoever owns the pack contract.
