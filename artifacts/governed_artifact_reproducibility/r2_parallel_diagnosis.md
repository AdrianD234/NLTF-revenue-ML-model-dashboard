# PED calibration R² parallel movement — final diagnosis

## Verdict

**The two value sets are the two engine identities. There is no numerical
nondeterminism anywhere in the calculation.**

| identity | operational pooled | paper horizon mean |
| --- | --- | --- |
| ensemble (`data/dashboard_evidence_pack`) — committed | `0.5591936636031876` | `0.9230110422702978` |
| AR(1) (`data/engine_ar1/dashboard_evidence_pack`) — the xdist run's output | `0.5803595524485978` | `0.9448430187011027` |

Both reproduce digit-for-digit, on Windows/Python 3.13.5 and in the
`nltf-ci:local` Linux/Python 3.11 container, sequentially and under isolated
xdist workers (`r2_worker_matrix.csv`). The values the incident published were
not corrupted, raced or environment-drifted numbers — they were the AR(1)
engine's correct numbers, written to the ensemble identity's file.

## Mechanism

1. `write_chart_source_tables` is a side effect of every `load_evidence_pack`
   call. Two writer populations exist (`r2_writer_inventory.csv`): seven
   library callers that resolve `DEFAULT_EVIDENCE_PACK_ROOT` (ensemble), and
   the AppTest modules that boot `app.py` and resolve the active engine root —
   which is AR(1), because `model_dashboard.engine.engine_default()` returns
   `"ar1"` when `DASHBOARD_ENGINE_DEFAULT` is unset. Two further modules set
   that variable to `ar1` process-wide at import time.
2. Before write isolation, both populations wrote to the single tracked
   destination `artifacts/chart_sources/`. The file's final content = the last
   writer's identity.
3. Sequential runs never showed it, by accident: module collation order ends
   with `tests/test_stress_horizon_aliases.py` — an ensemble-root library
   caller — which restored the committed content after any earlier AppTest
   module had overwritten it ("streamlit" < "stress" in ASCII collation).
4. `pytest -n 4 --dist=loadscope` distributed the modules across workers,
   breaking the accidental ordering; an AR(1)-identity writer finished last
   and the AR(1) values were published. Every test passed because both
   identities are internally consistent.

This resolves open question 2 of the original follow-up ("why did concurrent
execution produce a different but internally consistent number") and reverses
the prior branch's "differing data roots or engines — refuted" finding: its
writer matrix only exercised the seven library callers, never the app path.

## What the matrix measured at the final SHA

`ci/phase_b_r2_matrix.sh` + `ci/r2_writer_audit.py`, in a fresh clone inside the
container (`r2_worker_matrix.csv`, `raw_final/phase_b/matrix.log`):

* **Isolated execution is exact.** Sequential, and isolated 2- and 4-worker runs
  in `load`, `loadscope` and `loadfile` — every worker directory in every
  configuration carries the committed ensemble values, and the tracked chart
  sources were verified byte-identical after each configuration.
* **The AR(1) root reproduces the incident values** exactly, in the same
  container, from the same code.
* **A shared destination is demonstrably harmful.** Recreated in scratch via the
  explicit env override, four mixed-identity workers writing one directory make
  `tests/test_chart_data_reconciliation.py::test_acf_plotted_scope_equals_selected_scope`
  **fail** (1 failed / 102 passed, in each of three repetitions): a reader saw
  another identity's file.

One honest limitation of that last reconstruction: in all three repetitions the
final file content was the *ensemble* identity's, because the last writer to
finish happened to be an ensemble-root caller. It therefore reproduces the
*mechanism* — scheduling decides the published content, and cross-identity
contamination breaks a reader — but not the incident's specific outcome, where
an AR(1) writer finished last. Which identity wins a shared destination is a
race; that it is a race at all is the defect, and isolation removes it.

## The paper-basis value is a stored constant; the operational value is derived

The "paper horizon mean" calibration R² is read verbatim from the pack's own
`diagnostic_tests.parquet` (finalist row, `calibration_r2` column — a
Mincer-Zarnowitz R² stored at promotion time). The "operational pooled" value
is recomputed at load time from `scorecard_predictions.parquet` (finalist,
valid-for-MAPE rows; MZ fit of actual on [1, pred] via `numpy.linalg.lstsq`).
`r2_input_hash_matrix.csv` records, per engine: the source-file hashes, the
selected row counts (ensemble: 606 operational / 126 paper), the actual/pred
vector hashes, the fitted intercept/slope and the SSE/SST that produce each
number. One root, one identity, deterministically.

## What was already fixed, and what this branch adds

Write isolation (explicit `output_dir` → `NLTF_CHART_SOURCE_OUTPUT_DIR` → the
governed default; per-worker scratch redirect in `tests/conftest.py`;
governed-tree gate in every lane) was merged in the CI-optimisation branch and
keeps the tracked files byte-identical in every configuration measured here.

This branch found and fixed one residual defect in that isolation: under
xdist the CONTROLLER imports `tests/conftest.py` first, its `setdefault`
lands in the environment the workers inherit, and every worker's `setdefault`
then keeps the controller's directory — all workers shared ONE scratch
destination. Measured consequence at `ac1895d`: two workers racing in the
shared directory produced `FileNotFoundError` collisions in the atomic CSV
writer's tmp-rename (`raw_phase_b_prefix/xdist_n2_load.log`). The conftest now
re-derives the destination per process unless the variable was set by a user
(sentinel `NLTF_CHART_SOURCE_OUTPUT_DIR_AUTOSET`), so worker isolation holds
under xdist as designed. The tracked tree was never at risk from this residual
— the shared destination was in scratch — but the per-worker guarantee the
isolation promised did not hold until now.

## Authoritative values

Unchanged, and now pinned. The committed values are the ensemble identity's,
they reproduce exactly from the current promoted ensemble pack (so they are
not stale), and `tests/test_r2_engine_identity.py` fails if the tracked file
ever again carries a different identity's numbers. No calibration row, R²
definition, model fit, coefficient or economist-facing interpretation was
changed; no owner decision is required; the split condition for a separate
econometric-governance branch was not triggered.

## Global xdist

Remains rejected for normal development, per the CI contract. Narrow xdist is
used only inside the regression matrix (`ci/phase_b_r2_matrix.sh`,
`tests/test_r2_engine_identity.py::test_isolated_generation_reproduces_the_committed_values`)
with isolated worker outputs.
