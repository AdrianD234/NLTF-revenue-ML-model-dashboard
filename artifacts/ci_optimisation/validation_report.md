# Local acceptance — final Docker full tier

**Frozen SHA: `714a39f23454df4abae66f809e9917bacf3557f9`**
Run: sequential, single occupant, fresh self-contained clone, no xdist.

## Result

```
2005 passed, 53 skipped, 55 deselected, 3932 warnings in 1671.66s (0:27:51)
tier exit code 0, total 29m44s
```

## The six dimensions

| # | dimension | result |
| --- | --- | --- |
| 1 | selected test inventory | 2005 passed / 53 skipped / 55 deselected — reconciles exactly, see below |
| 2 | all expected tests pass | **0 failed, 0 errors** |
| 3 | five governed pack statuses | `replay_cache` ok, `quarterly_display` ok, `uncertainty` ok, `policy_runtime` ok, `databricks_bundle` not affected |
| 4 | conflict extract | **21/21 extract validations passed** |
| 5 | deployment readiness | **Streamlit deploy readiness: PASS** |
| 6 | tracked / governed cleanliness | **Governed tree unchanged (2143 files verified)**; no tracked file outside `artifacts/` and `data/` modified; `data/` tracked changes: 0 |

Plus the two conditions this branch added:

| | |
| --- | --- |
| chart-source writes confined to scratch | tracked `artifacts/chart_sources` untouched; writes landed in `test-output/chart_sources/main-<pid>/` |
| source checkout untouched | `git status --porcelain` empty; the run used a disposable clone, discarded afterwards |

## Test inventory reconciliation

The honest comparison, stated precisely rather than as "roughly +90":

| | passed | skipped |
| --- | --- | --- |
| local sequential baseline, **pre-branch** (Python 3.13 `.venv`) | 1,910 | 53 |
| branch-added tests | **+95** | 0 |
| **expected** | **2,005** | **53** |
| **Docker full tier, this run** (Python 3.11) | **2,005** | **53** |

The +95 accounted for individually:

| module | tests | why it exists |
| --- | --- | --- |
| `tests/test_ci_plan.py` | 48 | the change classifier's own assurance |
| `tests/test_ci_safety_gates.py` | 38 | cleanliness gate + pack planner + merge-contract wiring |
| `tests/test_chart_source_write_isolation.py` | 9 | chart sources never written into the tracked tree |
| | **95** | |

Every pre-existing test is still selected and still passes. Nothing was dropped
to make the suite green.

**What this comparison is not.** The 1,910/53 baseline is the local `.venv`
profiling run on Python 3.13, not a hosted run — no prior Python 3.11 full-suite
inventory exists, because the hosted baseline predates this branch. So this is a
*pre-branch vs post-branch* reconciliation on comparable selection, not a
Docker-to-Docker comparison. The hosted `full-assurance` job still has to
confirm the same inventory on GitHub infrastructure.

## Timing, against the hosted baseline

| | hosted (run `30906665375`) | Docker, this run | change |
| --- | --- | --- | --- |
| pytest | 69m 25s (4,165s) | **27m 51s** (1,672s) | **2.49× faster** |
| whole tier / core job | 74m 09s | **29m 44s** | **2.49× faster** |

The hosted runner has 2 CPUs; this machine has 20. The gain is hardware and
filesystem, not a reduction in what runs — the inventory reconciliation above is
the evidence for that.

## What is proven, and what is not

**Proven locally:**

- the container reproduces the clean-clone contract on all six dimensions;
- Python 3.11.15 / streamlit 1.59.0 / BLAS pinned to 1 thread, matching CI;
- the fast lane is 5–8s, the dashboard-UI affected lane 2m52s for 108 tests;
- a digest-bound calculation change fails fast with one diagnostic (exit 4, 7s),
  and passes after rebuilding in the planner's governed order;
- `data_refresh` and `model_promotion` escalate to full assurance;
- the governed-tree gate fires on every exit path and reports clean here.

**Not proven, and not claimed:**

- **No hosted run yet.** The redesigned workflow's job wiring, conditional
  execution and always-run summary have been asserted by tests but never
  executed on GitHub. That is Phase 3.
- **Windows replay parity.** The image is Linux; only a Windows runner can
  answer it.
- **The browser lane.** `test_playwright_*` are e2e and deselected. Their
  chart-source constants were reverted to the tracked path (the app writes
  there); both modules collect cleanly, but the browser phase itself has not
  been run.
- **Uncertainty pack reproducibility.** Rebuilding it reverts a governed
  re-centring — see `docs/FOLLOW_UP_PED_R2_DRIFT.md`. Untouched here.

## Evidence

| file | contents |
| --- | --- |
| `phase2/full.log` | the complete tier output |
| `phase2/full_result.txt` | exit code, elapsed, summary, gate status |
| `../ci_local/714a39f23454/junit_full.xml` | per-test results |
| `../ci_local/714a39f23454/governed_tree_*.json` | before/after hashes of every governed file |
| `phase2/affected_scopes_summary.txt` | the four affected-lane probes |
| `phase2/calc_lane_*` | the calculation-lane rebuild proof |
| `xdist_benchmark.md` | why parallel execution was rejected |
| `phase_a/` | the chart-source writer-identity diagnosis |
