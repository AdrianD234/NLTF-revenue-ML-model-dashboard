# Parallel execution benchmark — REJECTED as configured

**Verdict: do not adopt `-n 4 --dist=loadscope` globally.** It moved a governed
value in a tracked artifact that sequential execution left untouched.

This triggers stop conditions 5 ("parallel execution produces nondeterminism")
and 9 ("a proposed speed-up weakens formula, accounting, replay or
same-environment exactness"), so implementation stopped here for owner review.

---

## Runs

| | sequential | xdist |
| --- | --- | --- |
| command | `python -m pytest -q -m "not e2e and not requires_local_scratch" --durations=200 --durations-min=0.5 --junitxml=...` | `python -m pytest -q -m "not e2e and not requires_local_scratch" -n 4 --dist=loadscope --junitxml=...` |
| workers | 1 | 4 |
| distribution | — | `loadscope` |
| wall time | **41m 54s** (2513.60s) | **19m 27s** (1167.01s) |
| passed | 1910 | 1957 |
| failed | 0 | 1 |
| skipped | 53 | 53 |
| exit code | 0 | 1 |

The passed counts differ legitimately: `tests/test_ci_plan.py` (48 tests) was
added between the two runs.

**Speed-up: 2.15×.** Not the ~4× a 4-worker split suggests, because
`loadscope` distributes by module and `tests/test_view_invariant_sweep.py` is
734s on its own. That module is the critical path, so worker counts above ~4
cannot help until it is split.

### Concurrency was verified, not assumed

The owner asked whether two benchmark controllers ran at once. Process-tree
evidence says no:

```
PID 52964 -> 30236   python -m pytest ... -n 4 --dist=loadscope
                     --junitxml=.../junit_xdist_1.xml
  workers: 11836, 36480, 24888, 7304
```

One controller, one `junit_xdist_1.xml`, four workers. The second run was
queued behind a sequential `for` loop and never started
(`tree_before_2.txt` absent). Timings are uncontended.

---

## The failure was mine, not xdist's

```
FAILED tests/test_ci_plan.py::test_every_tracked_file_resolves_to_a_scope
```

Reproduced standalone, sequentially, in 0.57s: **1 failed, 47 passed.** Fully
deterministic and unrelated to parallelism.

Root cause: `ci/change_scopes.yml` had no rule for `artifacts/**` (481 tracked
files, via the `!artifacts/...` exceptions in `.gitignore`), for `scripts/**`
beyond the specific builders, or — most importantly — for
`model_dashboard/revenue_outlook_policy_runtime.py`, which computes the digest
every policy state is gated on.

The test did exactly its job. Fixed; all 2,107 tracked files now classify and
all 48 planner tests pass.

**So on its own terms, xdist produced zero parallelism defects in the test
results.** The problem is elsewhere.

---

## The disqualifying finding: a governed value moved

After the xdist run, `git status` reported:

```
 M artifacts/chart_sources/r2_ladder_summary.csv
```

The change is not corruption. It is a governed number:

| series | field | committed | after xdist |
| --- | --- | --- | --- |
| PED VKT per capita (operational pooled) | `calibration_r2` | 0.5591936636031876 | **0.5803595524485978** |
| PED VKT per capita (paper horizon mean) | `calibration_r2` | 0.9230110422702978 | **0.9448430187011027** |

Displayed values move from 0.559 → 0.580 and 0.923 → 0.945, and the human-readable
narration in the same rows moves with them.

### It was the parallel run, not the sequential one

`artifacts/ci_optimisation/xdist/tree_before_1.txt` was captured at 13:02:21 —
*after* the sequential profiling run completed and *before* the xdist run
started. It lists no `artifacts/` modification at all.

Sequential: file untouched. Parallel: file moved. That is the whole argument.

### Mechanism

`artifacts/chart_sources/*.csv` is written as a side effect of
`load_evidence_pack()`. At least seven test modules call it, several from
session-scoped `autouse` fixtures:

```
tests/test_r2_ladder.py:20        @pytest.fixture(scope="session", autouse=True)
tests/test_r2_metrics.py:18       @pytest.fixture(scope="session", autouse=True)
tests/test_chart_source_tables.py
tests/test_chart_data_reconciliation.py
tests/test_evidence_pack.py
tests/test_light_ruc_reproducibility_pack.py
tests/test_performance_budget.py
```

Under `--dist=loadscope` those modules are distributed across workers, and
"session" scope is **per worker process**, not per run. So four processes
independently rebuild and rewrite the same tracked files, concurrently.

Running `tests/test_r2_ladder.py` alone, sequentially, does **not** reproduce
the drift (14 passed, tree clean) — which confirms the value depends on what
else has run, not on the file's own logic.

---

## Why this is not simply "mark one module serial"

The owner's decision tree anticipated a stateful *module* that could be moved to
a serial lane. That is not the shape of this problem:

1. The writer is a **shared library call**, not one module. Seven modules
   reach it, and any future test that loads the evidence pack joins them.
2. `loadscope` cannot group across modules, so a serial lane would have to
   contain all seven — including `test_evidence_pack.py` and
   `test_performance_budget.py`, which have nothing to do with each other.
3. The deeper problem is that **the test suite writes into the tracked tree at
   all**. That is a latent defect independent of parallelism: it means "the
   suite leaves the checkout unchanged" is not currently true, and any
   reordering can move a governed number.

Fixing it properly means making `load_evidence_pack` write chart sources to a
run-scoped directory rather than into `artifacts/`, or making the tests read a
committed copy instead of regenerating one. Both are source changes to governed
behaviour, outside the remit of a CI change, and both deserve their own review.

---

## Recommendation

**Adopt change-aware selection and explicit job sharding. Do not adopt global
xdist.**

This costs less than it appears:

- Change-aware selection is where nearly all the hosted saving is anyway — a
  documentation change now runs no model work at all, versus 74 minutes before.
- Job sharding at the workflow level (splitting by test group across jobs, each
  single-threaded) captures much of the wall-clock benefit with **no shared
  process state**, because each job is a separate machine with its own checkout.
- On GitHub's 2-CPU standard runners, `-n 4` was never available regardless;
  `-n 2` is the ceiling, and the sweep module would still bound the critical
  path.

Parallelism can be revisited *after* the write-into-tracked-tree defect is
fixed, at which point the 2.15× is real and safe. Until then it trades a
governed number for wall time, which is not a trade this repository makes.

---

## What was NOT concluded

- Not concluded that the suite cannot be parallelised. It can, once the shared
  write is removed.
- Not concluded from a single run that xdist is inherently nondeterministic.
  The claim here is narrower and fully evidenced: **this configuration moved a
  governed value that sequential execution did not.**
- The modified file was restored (`git checkout --`) and **not committed**.
