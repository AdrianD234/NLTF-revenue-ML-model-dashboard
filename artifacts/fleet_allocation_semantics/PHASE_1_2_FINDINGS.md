# Phases 1 and 2: both target-semantics gates return decisive answers

Investigation only. No production code, governed pack, checkpoint or dashboard
value has been altered.

## Phase 1 - PED target is petrol-only

```
max | PED target  -  light_petrol_vkt_total_km / population |  =  0.0
```

Exactly zero on every historical observation. The AR(1) dependent variable IS
petrol VKT per capita. No de-electrification or all-light counterfactual
reconstruction exists anywhere upstream; the target is taken directly from the
petrol series.

The forward output therefore has the same definition as its historical
dependent variable: petrol-only, post-whatever-electrification-already-happened.

## Phase 2 - Light RUC target is conventional-only

The hard gate. Model target compared against conventional-only and against the
total pool (conventional + Light BEV + PHEV), by fiscal year:

| FY | Model target | Conventional | Total pool | vs conventional | vs total pool |
|---|---:|---:|---:|---:|---:|
| 2018 | 11,112.227 | 11,112.227 | 11,112.227 | **0.000%** | 0.000% |
| 2019 | 11,898.225 | 11,898.225 | 11,898.225 | **0.000%** | 0.000% |
| 2020 | 11,385.937 | 11,385.937 | 11,385.937 | **0.000%** | 0.000% |
| 2021 | 11,998.163 | 11,998.163 | 11,998.163 | **0.000%** | 0.000% |
| 2022 | 12,644.208 | 12,644.208 | 12,644.208 | **0.000%** | 0.000% |
| 2023 | 13,553.288 | 13,553.288 | 13,553.288 | **0.000%** | 0.000% |
| 2024 | 10,355.551 | 10,355.551 | 10,964.012 | **0.000%** | −5.550% |
| 2025 | 12,273.984 | 12,273.984 | 13,529.743 | **0.000%** | −9.281% |

Residual against conventional is **exactly 0.0 million km in every year**.

The definition-break test is the decisive part. Through FY2023 the two
candidates are identical, because BEV and PHEV RUC are not separately
recorded. From FY2024 they diverge - and the target tracks **conventional**,
not the total pool, to the last digit.

Classification: **`conventional_light_only`**, evidenced, not inferred.

## What this means

Both structural hypotheses in the brief are supported by the target evidence:

**PED.** A petrol-only forecast receives an additional prospective EV/PHEV
migration reduction. Unless that layer is documented as incremental beyond a
measured model-embedded baseline, petrol travel is removed twice.

**Light RUC.** A conventional-only forecast is treated as the total light-RUC
pool and then split by VFM conventional/BEV/PHEV shares. If conventional is
about 73% of the pool by FY2030, this mechanically reduces conventional Light
RUC by roughly 27% before any economics enter, and manufactures BEV and PHEV
kilometres from a series that never contained them.

## Not yet established

- Which runtime stage the Workstream A decomposition actually read. Until the
  Phase 0 stage waterfall is built, its headline numbers stay provisional.
- Whether the VFM overlay is documented as incremental uptake.
- The structural variant matrix, conservation and revenue identity audits,
  PHEV petrol treatment, and the falsification tests.

No variant has been scored and no production recommendation is made here.
