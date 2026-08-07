# HIGH PRIORITY FOLLOW-UP — which PED calibration R² values are authoritative?

**Status: open. Deliberately not answered in `performance/ci-runtime-optimisation`.**

Raised 2026-08-07 while benchmarking parallel test execution for the CI runtime
optimisation. This document was rewritten once the diagnosis completed: the
first version listed four candidate causes, and the writer matrix eliminated
three of them. Read the *Settled* section before the *Open* one.

Evidence: `artifacts/ci_optimisation/xdist_benchmark.md`,
`artifacts/ci_optimisation/phase_a/writer_matrix.csv`, and the Phase A scripts
under `ci/phase_a_*.sh`.

---

## The incident

A `pytest -n 4 --dist=loadscope` run rewrote a tracked, governed artifact and
moved a published R² value. **Every test passed.** It was caught only by an
incidental `git status` during a benchmark.

`artifacts/chart_sources/r2_ladder_summary.csv`, PED VKT per capita
`calibration_r2`:

| basis | committed | after the parallel run |
| --- | --- | --- |
| operational pooled | `0.5591936636031876` | `0.5803595524485978` |
| paper horizon mean | `0.9230110422702978` | `0.9448430187011027` |

The regenerated values were **not committed**. The file was restored.

---

## Settled — with evidence

### Withdrawn: "the last writer wins between differing identities"

**Refuted.** `ci/phase_a_writer_matrix.sh` ran each of the seven modules that
call `load_evidence_pack` **alone and sequentially**, from the committed state,
inside the Python 3.11 container:

```
tests/test_r2_ladder.py                       -> 4a247e03540d54f0
tests/test_r2_metrics.py                      -> 4a247e03540d54f0
tests/test_chart_source_tables.py             -> 4a247e03540d54f0
tests/test_chart_data_reconciliation.py       -> 4a247e03540d54f0
tests/test_evidence_pack.py                   -> 4a247e03540d54f0
tests/test_light_ruc_reproducibility_pack.py  -> 4a247e03540d54f0
tests/test_performance_budget.py              -> 4a247e03540d54f0
```

**All seven produce byte-identical output.** There are not competing identities
writing different content; there is one content.

### Withdrawn: "differing data roots or engines"

**Refuted by the same run.** Every call site resolves the same
`DEFAULT_EVIDENCE_PACK_ROOT` (`data/dashboard_evidence_pack`).

### Withdrawn: "the values are environment-dependent (Python 3.11 vs 3.13)"

**Refuted.** This was stated during the investigation and was wrong. The
regenerated file differs from the committed one **only in line endings**:

```
COMMITTED    : 7944 bytes, 7 lines, 7 CR lines
REGENERATED  : 7937 bytes, 7 lines, 0 CR lines
identical once carriage returns are ignored
```

Seven bytes, seven carriage returns. A cell-by-cell comparison
(`ci/phase_a_diff_detail.sh`) reports **no cell differs**, across 6 data rows and
every column. The committed files were written on Windows (CRLF); the container
writes LF.

The PED calibration R² values are **unchanged** by any sequential run, in either
environment:

```
COMMITTED    current_grid_operational_pooled  calibration_r2=0.5591936636031876
             schiff_paper_horizon_mean        calibration_r2=0.9230110422702978
REGENERATED  current_grid_operational_pooled  calibration_r2=0.5591936636031876
             schiff_paper_horizon_mean        calibration_r2=0.9230110422702978
```

### Confirmed: the parallel race is real, and is the only value movement

Sequential execution — Windows `.venv`, Linux container, single module or a
108-test subset — never moved a value. Only `pytest-xdist` did. Under
`--dist=loadscope`, `scope="session"` is per **worker process**, so four
processes rebuilt and rewrote the same files concurrently.

Global xdist remains **rejected**. Measured potential was 2.15× (41m54s →
19m27s) with no defects in the test *results*; it is rejected solely because it
moved governed content.

### Fixed: tests no longer write into the tracked tree

`write_chart_source_tables` now takes an explicit `output_dir`;
`resolve_chart_source_output_dir` applies explicit argument → the
`NLTF_CHART_SOURCE_OUTPUT_DIR` override → the committed default. Production, the
app, the Databricks bundle and any promotion command set nothing and are
unaffected.

`tests/conftest.py` redirects test runs to
`test-output/chart_sources/<worker>-<pid>`, so no two workers and no two
concurrent runs can share a destination.
`tests/test_chart_source_write_isolation.py` pins all of it, including that the
default destination is unchanged.

`scripts/assert_governed_tree_unchanged.py` fails any lane that changes tracked
or governed content, in every local tier and the hosted `fast`, `affected` and
`full-assurance` jobs.

---

## Open — the actual governance question

Nothing above establishes **which R² values are authoritative**, and this branch
deliberately does not decide. The sequential evidence shows the committed values
reproduce exactly, which is reassuring but not the same as correct.

This follow-up must determine:

1. **Are the committed artifacts stale?** They reproduce today. Do they reflect
   the current promoted models, or an older run that happens to still reproduce?
2. **Why did concurrent execution produce a different number at all?** A race on
   file writes explains corrupted or interleaved *bytes*. It does not obviously
   explain two internally consistent but different R² values. Something about
   concurrent construction changed an input, and that is worth understanding
   even though xdist is now rejected.
3. **Do different engines or data roots legitimately produce different R²
   values?** Not exercised here — every call site used the same root.
4. **Do numerical library versions contribute?** Not detectable in this
   evidence, because no value moved between Python 3.11 and 3.13 sequentially.
5. **Which command alone should be authorised to publish chart sources?**
   Currently any `load_evidence_pack` caller writes them.
6. **Should `load_evidence_pack` become fully read-only**, with chart-source
   production moved to an explicit materialisation command? The write isolation
   here is the narrow fix; this is the structural one.

### Do not resolve this by promoting whichever value a run produced

Neither the container output nor the xdist output has any claim to authority.
The question is which values the governance process intends to publish, and that
is answered by understanding the calculation, not by picking a hash.

---

## Relationship to the roadmap

The forthcoming work list already contains **"PED calibration R² drift"** as a
governance item. Question 2 above is very likely the same phenomenon seen from
another direction, and is the natural starting point.
