# Chart-source read/write contract

## The contract

| Context | Chart-source behaviour | Mechanism |
| --- | --- | --- |
| Local Streamlit startup | read-only | `load_evidence_pack(materialize_chart_sources=False)` |
| Hosted Streamlit startup | read-only | same |
| Databricks App startup | read-only | same; verified by probing the built bundle |
| Page navigation, reruns, engine switching, cache warming | read-only | the warmer never touched chart sources; navigation never did either |
| Tests | scratch only | `tests/conftest.py` per-worker, per-pid directory; canonical writes raise |
| Validators and tooling | scratch only | `materialize_scratch_chart_sources()` under `test-output/chart_sources/<label>-<pid>` |
| Explicit promotion | writes the governed directory | `scripts/promote_chart_sources.py`, `mode=promote`, ensemble identity |
| Engine diagnostics | engine-keyed, never canonical | `artifacts/diagnostics/chart_sources/<engine>/` |

## Write modes

`write_chart_source_tables(repo_root, data, output_dir=None, *, mode, engine=None,
allow_noncanonical_engine=False)`.

- `READ_ONLY` — raises. Read-only callers use `build_chart_source_tables`, which
  computes exactly the same tables without publishing them. Computation and
  materialisation are separate.
- `SCRATCH` (default) — writes to the resolved destination, but **refuses** the
  canonical tracked directory. This is what the loader uses, so no load path can
  reach governed evidence however it is configured.
- `PROMOTE` — the only mode permitted at the canonical destination, and only for
  the governed `ensemble` identity. AR(1) is refused with a message naming both
  identities and pointing at the diagnostic directory, unless
  `allow_noncanonical_engine=True` is passed deliberately.

Destination precedence is unchanged: explicit `output_dir` > the
`NLTF_CHART_SOURCE_OUTPUT_DIR` environment override > the canonical default. The
environment variable is retained for deployment and test overrides, but it is no
longer the only line of defence: the Python-level mode contract is independent of
it, and both are tested.

## What the app reads

The dashboard does not read these files for data. `app.py:5383` recomputes the
R-squared ladder in memory from the loaded pack. Engine-specific in-memory values
are still displayed exactly as before; nothing was replaced with the ensemble
pair to stabilise the files.

There is one read, and it is a count, not content:

```python
app.py:14374  chart_source_count = len(list((repo_root / "artifacts" / "chart_sources").glob("*.csv")))
app.py:14867  ("Chart-source isolation", "untouched", f"{chart_source_count} main chart-source CSVs guarded", ...)
```

**Consequence, stated plainly.** On a fresh clone or in the Databricks bundle,
that card now reads "3 main chart-source CSVs guarded" instead of "22", because
only the three governed CSVs are committed and the app no longer generates the
other 19. In a developer tree where the files already exist it still reads 22.
No test asserts the number, and the neighbouring literals "untouched" and "no
writes" are now true rather than aspirational.

This was left alone on purpose: correcting the counter means editing `app.py`,
which repins the policy runtime, escalates the change scope to `governed_pack`
and forces a full-assurance CI cycle. That is a poor trade for a cosmetic
counter. It is flagged here for the owner rather than fixed silently.

## Out of scope, and unchanged

`load_evidence_pack` still writes two non-chart-source artefacts on every load:

```python
model_dashboard/evidence_pack.py:243  write_data_source_manifest(repo_path, source_manifest)
model_dashboard/evidence_pack.py:244  _write_compat_source_tables(repo_path, data)
```

These produce `artifacts/data_source_manifest.json` and
`artifacts/*_source_table.csv`, all untracked and gitignored. They are
pre-existing behaviour on `origin/main`, untouched by this change, and issue #31
is specifically about governed chart-source evidence. This change strictly
*reduces* what app startup writes; it introduces nothing.

The one visible consequence is that a Databricks bundle manifest
re-verification still fails after a real app boot, because those files appear on
disk without being in the manifest. That is true on `origin/main` too. Worth a
separate issue.
