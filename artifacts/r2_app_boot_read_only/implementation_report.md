# Implementation report: issue #31

## Boundary changed

`model_dashboard/`, not `app.py`. `app.py` is deliberately untouched, so no
policy-runtime repin is triggered *by the app surface* and the change does not
escalate to a full-assurance CI cycle on that account.

### 1. Writer boundary — `model_dashboard/data/chart_sources.py`

Added an explicit write-mode contract and a guard:

- `CHART_SOURCE_WRITE_READ_ONLY` / `_SCRATCH` / `_PROMOTE`
- `CANONICAL_CHART_SOURCE_ENGINE = "ensemble"`
- `ChartSourceWriteRefused`
- `canonical_chart_source_dir(repo_root)`
- `engine_diagnostic_chart_source_dir(repo_root, engine)`
- `materialize_scratch_chart_sources(repo_root, data, label)` for tooling

`write_chart_source_tables` gained keyword-only `mode`, `engine` and
`allow_noncanonical_engine`. Writing the canonical directory now requires
`mode=PROMOTE` **and** the governed engine identity. The guard runs before any
table is built, so a refused call has no side effect at all.

### 2. Loader boundary — `evidence_pack.py` and `parquet_loader.py`

`load_evidence_pack` and `load_parquet_dashboard` gained
`materialize_chart_sources: bool = False` and `chart_source_output_dir`. When
asked to materialise they use `SCRATCH`, so **no load path can reach the
governed directory**, regardless of environment. Materialisation is opt-in; the
tracked write is not the implicit default of a generic load function.

### 3. Explicit promotion — `scripts/promote_chart_sources.py` (new)

The one sanctioned publisher. Names the engine (`--engine`, default `ensemble`),
resolves the matching pack, validates all 21 expected tables for presence,
non-emptiness and required columns, checks for `.tmp` residue, and prints the
before/after PED calibration R-squared pair. `--engine ar1` routes to
`artifacts/diagnostics/chart_sources/ar1/` rather than the canonical filenames;
`--dry-run` renders into a throwaway directory. Writes are atomic via the
existing pid-unique temp-and-rename helper.

### 4. Host-process check — `scripts/check_app_boot_read_only.py` (new)

Starts a real Streamlit server outside pytest, drives it with Chromium, stops
it, and requires every file under `artifacts/chart_sources` to be byte-identical
plus `git status` unchanged. Logs outside the target root and sets
`PYTHONDONTWRITEBYTECODE=1`, so it can probe the Databricks bundle without
invalidating the bundle manifest.

### 5. Consumers repaired rather than broken

Six validators materialise into a run-scoped scratch directory instead of
reading the tracked tree. Two of them were previously **failing open** on a fresh
clone, which this change fixes as a side benefit:

- `validate_semantic_labels.py` silently skipped its Light RUC gain check when
  the file was absent.
- `validate_80_gates.py` returned PASS on a missing file, making the stress
  bucket gate vacuous.

`ci/r2_writer_audit.py` now requests materialisation explicitly; otherwise it
would have compared against an empty directory and reported success while
proving nothing.

Ten test modules ask for materialisation explicitly. Two cross-test ordering
dependencies were removed in the process: `test_governance_reproducibility_page`
and `test_light_ruc_reproducibility_pack` both relied on some *other* test having
populated the scratch directory first.

## Design choices worth defending

- **Default off, guard on.** The default alone would be enough for today's
  callers; the guard is what makes it structural. A future caller that forgets
  the flag gets a refusal naming the promotion command, not a silent overwrite.
- **The environment variable stays, but is no longer load-bearing alone.** It
  remains for deployment and test overrides, paired with the Python-level mode
  contract. Both are tested.
- **Engine-keyed diagnostics.** Two identities never share a canonical filename.
- **No value was hardcoded into production logic.** Neither R-squared pair
  appears in `model_dashboard/`; the constants live only in the test that pins
  them.
- **The app still displays engine-specific in-memory values.** Nothing was
  replaced with the ensemble pair to make files stable.

## Known limitation, deliberately not fixed

The Governance page status card counts CSVs on disk (`app.py:14374`). On a fresh
clone it now reads "3 main chart-source CSVs guarded" rather than "22". No test
asserts it. Fixing it requires editing `app.py`, which forces a full-assurance
cycle for a cosmetic counter. Flagged for the owner rather than changed
silently. Detail in `read_write_contract.md`.
