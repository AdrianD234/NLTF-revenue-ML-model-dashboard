# Data Validation Review

Status: **passed**.

Latest CSV-preview run retained for smoke testing: `run_20260520_002339`.
Primary Parquet validation remains authoritative for completion.

- [pass] Parquet resolved: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\information pack\stage1_curated_candidate_cone.parquet`.
- [pass] Candidate rows loaded: 300.
- [pass] All three streams have candidate rows.
- [pass] Current finalist rows exist for all streams.
- [pass] Pure Schiff rows exist and are not contaminated by blend/residual/solver names.
- [pass] Candidate landscape contains cone distribution and frontier roles.
- [pass] Candidate landscape default sample is capped at 287 rows.
- [pass] User-facing labels are underscore-free.
- [pass] Stale old finalist MAPE values are not current.
- [pass] Stress aliases coalesce correctly across PED, Light RUC and Heavy RUC finalist rows.
- [pass] Loader builds curated default sample and derived stress/horizon datasets.
- [pass] Diagnostic fields are available.
