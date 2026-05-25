# Governance Story Review

Current Parquet refresh status: **pass**. The current finalists, pure Schiff rows, paired gains, diagnostics, chart source tables, and browser screenshots reconcile to the Parquet-backed data pack.

Reviewer: simulated governance/story reviewer

## Verdict

Pass. The dashboard answers the management questions using the latest arbitration run, not the older AutoGluon balanced run.

## Management questions

| Question | Dashboard answer | Evidence |
|---|---|---|
| Which model won? | The latest arbitration finalists are the three static convex top-18 solver ensembles. | Overview finalist accuracy, curated `finalist_accuracy.csv` |
| Did it beat Schiff? | The Overview, Scenario Comparison, and Schiff Benchmark pages compare finalists against pure Schiff rows only. | `schiff_benchmark.csv`, paired selected rows |
| Is it robust? | Stress/horizon and annual prediction views show horizon buckets, 2024+, 2022-23, and annual performance. | `stress_horizon.csv`, selected predictions |
| What remains weak? | Light RUC remains the key watch stream because its 2022-23 stress MAPE is visibly high. | Stress watch note |
| What should management do next? | Promote the latest arbitration finalists through Stage 1 governance, while carrying Light RUC stress/purchase-timing caveats into Stage 2. | Scenario Decision Lens and Overview management read |

## Latest finalist summary

| Stream | Current finalist | Quarterly MAPE | Annual MAPE | Governance read |
|---|---|---:|---:|---|
| PED VKT per capita | PED - Static solver | 2.47% | 2.39% | Strong Stage 1 volume mapping result |
| Light RUC volume | Light RUC - Static solver | 9.15% | 6.00% | Watchlist stream; stress-window effects remain important |
| Heavy RUC volume | Heavy RUC - Static solver | 3.48% | 3.02% | Material improvement over the structural benchmark |

## Caveats

- Stage 1 uses realised explanatory variables and therefore tests volume-model mapping rather than macro/fuel-input forecast error.
- Pure Schiff is intentionally separated from Schiff residual/blend/solver variants.
- Full raw candidate inventory is available by drilldown/download, but the management dashboard defaults to the curated cone sample.
