# HIGH PRIORITY FOLLOW-UP — PED calibration R² drift and unisolated chart-source writes

**Status: open. Not addressed in `performance/ci-runtime-optimisation`, by
design.**

Raised 2026-08-07 while benchmarking parallel test execution for the CI runtime
optimisation. Full evidence: `artifacts/ci_optimisation/xdist_benchmark.md`.

This lives here rather than in `BUG_BACKLOG.md` because
`tests/test_locked_backlogs_closed.py` requires that file to contain no
unchecked items, and this is genuinely open work — recording it there would
either break that contract or misrepresent it as closed.

---

## What happened

A `pytest -n 4 --dist=loadscope` run rewrote a tracked, governed artifact and
moved a published R² value. **Every test passed.** Nothing flagged it. It was
caught only by an incidental `git status` during the benchmark.

`artifacts/chart_sources/r2_ladder_summary.csv`, PED VKT per capita
`calibration_r2`:

| basis | committed | after the parallel run |
| --- | --- | --- |
| operational pooled | `0.5591936636031876` | `0.5803595524485978` |
| paper horizon mean | `0.9230110422702978` | `0.9448430187011027` |

Displayed values move 0.559 → 0.580 and 0.923 → 0.945, and the human-readable
narration in the same rows moves with them.

The regenerated values were **not committed**. The file was restored to the
committed version.

## Why it happened

`load_evidence_pack()` writes `artifacts/chart_sources/*.csv` into the tracked
checkout as a side effect of loading. At least seven test modules call it, two
from `@pytest.fixture(scope="session", autouse=True)`:

```
tests/test_r2_ladder.py
tests/test_r2_metrics.py
tests/test_chart_source_tables.py
tests/test_chart_data_reconciliation.py
tests/test_evidence_pack.py
tests/test_light_ruc_reproducibility_pack.py
tests/test_performance_budget.py
```

Under xdist, `scope="session"` is per **worker process**, not per run. Four
processes rebuilt and rewrote the same tracked files concurrently.

Sequential execution left the file untouched — proved by the `git status`
captured between the sequential and parallel runs
(`artifacts/ci_optimisation/xdist/tree_before_1.txt`).

Running `tests/test_r2_ladder.py` **alone**, sequentially, also does not
reproduce the drift (14 passed, tree clean). So the computed value depends on
what else has run in the process, not on that module's own logic.

## Why this is more than a CI problem

Two separable defects, and the second is the serious one:

1. **The suite writes into the tracked tree.** So "running the tests leaves the
   checkout unchanged" is not currently true, and no clean-clone claim can be
   fully honest until it is.

2. **The computed R² depends on test ordering.** That is a provenance question
   about the model, not about pytest. Something about what has already been
   loaded in the process changes the inputs to a governance calculation. Until
   that is understood, it is not known whether the committed values or the
   regenerated ones are correct — or whether either is.

## What this follow-up must determine

- Which R² values are authoritative — the committed ones or the regenerated ones?
- **Why does worker/test ordering change the calculation inputs at all?**
- Is the committed artifact stale relative to current code?
- Should `load_evidence_pack` be read-only?
- Should chart sources be generated only by an explicit promotion command?
- Should tests write solely to run-scoped temporary directories?

## Do not resolve this by redirecting output

Pointing the write at a temporary directory stops the corruption and hides the
question. The calculation and provenance discrepancy must be understood **before
any new R² value is promoted**. A green suite that writes the "right" number to
a safe location still would not tell you which number is right.

## What has already been done

- **Detection is permanent.** `scripts/assert_governed_tree_unchanged.py`
  snapshots every tracked file plus everything under `data/` before each test
  lane and verifies it afterwards. It is wired into every local tier
  (`ci/entrypoint.sh`) and the hosted `fast`, `affected` and `full-assurance`
  jobs. Any lane that changes tracked or governed content now fails and lists
  the changed paths with before/after hashes. Verified against this exact
  incident: it passes on a clean run and catches the injected drift.

- **Global `pytest-xdist` is rejected** for now. Measured potential was **2.15×**
  (41m54s → 19m27s at `-n 4 --dist=loadscope`), and the test results themselves
  showed no parallelism defects. It is rejected *solely* because it moved
  governed content. It becomes available again once the writes are isolated and
  the authoritative values are established.

## Relationship to the roadmap

The forthcoming work list already contains **"PED calibration R² drift"** as a
governance item. This is very likely the same phenomenon, surfacing from a
different direction. Whoever picks up that roadmap item should start here.
