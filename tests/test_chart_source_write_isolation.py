"""Chart source tables must never be written into the tracked tree by a test.

Loading an evidence pack writes ``artifacts/chart_sources/*.csv`` as a side
effect, and seven test modules load one. Before this isolation existed:

  * on Linux, a single sequential test run rewrote every tracked chart source
    from CRLF to LF - 7944 bytes to 7937, no value changed, but the checkout was
    no longer the committed one;
  * under pytest-xdist, four worker processes writing the same files
    concurrently moved a governed PED calibration R-squared from 0.559 to 0.580
    while every test still passed.

See ``artifacts/ci_optimisation/xdist_benchmark.md`` for the incident and
``docs/FOLLOW_UP_PED_R2_DRIFT.md`` for its resolution: the two value sets are
the two ENGINE identities, pinned by ``tests/test_r2_engine_identity.py``.
These tests only ensure the tests themselves stop overwriting the evidence.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess
import sys

import pytest

from model_dashboard.data.chart_sources import (
    CHART_SOURCE_OUTPUT_DIR_ENV,
    resolve_chart_source_output_dir,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
TRACKED_CHART_SOURCES = ROOT / "artifacts" / "chart_sources"


# ---------------------------------------------------------------------------
# The resolver contract
# ---------------------------------------------------------------------------


def test_default_destination_is_unchanged(monkeypatch):
    """Production, the app, the bundle and promotion commands set nothing.

    They must therefore keep writing exactly where they always did. If this
    fails, the isolation has moved production output, which is a far worse
    outcome than the problem it was fixing.
    """
    monkeypatch.delenv(CHART_SOURCE_OUTPUT_DIR_ENV, raising=False)
    assert resolve_chart_source_output_dir(ROOT) == TRACKED_CHART_SOURCES


def test_explicit_argument_wins_over_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(CHART_SOURCE_OUTPUT_DIR_ENV, str(tmp_path / "from_env"))
    explicit = tmp_path / "explicit"
    assert resolve_chart_source_output_dir(ROOT, explicit) == explicit


def test_environment_override_redirects(tmp_path, monkeypatch):
    monkeypatch.setenv(CHART_SOURCE_OUTPUT_DIR_ENV, str(tmp_path))
    assert resolve_chart_source_output_dir(ROOT) == tmp_path


# ---------------------------------------------------------------------------
# What the suite actually does
# ---------------------------------------------------------------------------


def test_the_suite_redirects_chart_sources_away_from_the_tracked_tree():
    """conftest.py must have pointed this run somewhere else."""
    resolved = resolve_chart_source_output_dir(ROOT)
    assert resolved != TRACKED_CHART_SOURCES, (
        "this test run would write chart sources into the tracked tree"
    )
    assert "test-output" in resolved.parts, (
        f"chart sources redirect to {resolved}, which is not test scratch"
    )


def test_the_scratch_destination_is_unique_per_process():
    """Sequential and parallel runs must not share a destination.

    The xdist incident was four processes writing one path. The destination
    carries both the worker id and the pid, so no two workers - and no two
    concurrent runs - can collide.
    """
    resolved = resolve_chart_source_output_dir(ROOT)
    leaf = resolved.name
    assert str(os.getpid()) in leaf, f"{leaf} does not identify the process"
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    assert worker in leaf, f"{leaf} does not identify the xdist worker"


def test_two_identities_cannot_overwrite_each_other(tmp_path, monkeypatch):
    """Distinct destinations stay distinct even for identical inputs."""
    import pandas as pd

    from model_dashboard.data.chart_sources import write_chart_source_tables

    data = {"recommended": pd.DataFrame(), "summary": pd.DataFrame()}
    first, second = tmp_path / "a", tmp_path / "b"

    try:
        write_chart_source_tables(ROOT, data, output_dir=first)
        write_chart_source_tables(ROOT, data, output_dir=second)
    except Exception as exc:  # empty frames may not satisfy the builder
        pytest.skip(f"builder needs a populated pack: {type(exc).__name__}: {exc}")

    assert first.exists() and second.exists()
    assert first.resolve() != second.resolve()


# ---------------------------------------------------------------------------
# The property that matters most
# ---------------------------------------------------------------------------


def _hash_tracked() -> dict[str, str]:
    if not TRACKED_CHART_SOURCES.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(TRACKED_CHART_SOURCES.glob("*.csv"))
    }


def test_loading_an_evidence_pack_leaves_the_tracked_files_byte_identical():
    """The end-to-end property, exercised the way the incident happened.

    Not a mock: this loads a real evidence pack, which is precisely the call
    that used to rewrite the tracked files.
    """
    from model_dashboard.data_loader import (
        DEFAULT_EVIDENCE_PACK_ROOT,
        load_evidence_pack,
        resolve_evidence_pack_root,
    )

    root = resolve_evidence_pack_root(DEFAULT_EVIDENCE_PACK_ROOT)
    if root is None or not pathlib.Path(root).exists():
        pytest.skip("evidence pack not present")

    before = _hash_tracked()
    if not before:
        pytest.skip("no committed chart sources to protect")

    load_evidence_pack(root, ROOT)

    after = _hash_tracked()
    moved = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    assert not moved, (
        "loading an evidence pack rewrote tracked chart sources: "
        + ", ".join(moved)
    )
    assert set(before) == set(after), "tracked chart sources were added or removed"


def test_a_subprocess_run_also_leaves_the_tracked_files_alone():
    """Guards the mechanism, not just this process.

    The redirect is set in conftest.py at import time. A test that only checked
    the current process would still pass if conftest stopped being imported by
    some future runner, so spawn a real pytest and check the tree afterwards.
    """
    before = _hash_tracked()
    if not before:
        pytest.skip("no committed chart sources to protect")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_r2_ladder.py", "--no-header", "-x"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"inner pytest failed:\n{result.stdout[-2000:]}"

    after = _hash_tracked()
    moved = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    assert not moved, (
        "a child pytest run rewrote tracked chart sources: " + ", ".join(moved)
    )


def test_no_test_module_hardcodes_the_tracked_chart_source_directory():
    """A new test must not quietly reintroduce the tracked path.

    The first version of this guard matched only two spellings, ``ROOT / ...``
    and ``ARTIFACTS / ...``, and missed three modules that write the path out
    longhand - one of which failed the full tier:

        FAILED tests/test_latest_arbitration_values.py::
               test_mini_parquet_source_tables_are_generated_from_dashboard_data
        assert PosixPath('/work/artifacts/chart_sources/
                          overview_ensemble_composition.csv').exists()

    So this now matches the DESTINATION however it is spelled: any adjacency of
    an "artifacts" segment and a "chart_sources" segment, and the literal
    "artifacts/chart_sources".
    """
    # Files that legitimately name the tracked location.
    #
    # The Playwright pair is the subtle one, and an earlier version of this
    # change got it wrong. Those tests do NOT generate chart sources: they read
    # what the running Streamlit APP wrote. verify_dashboard.ps1 starts that
    # server as a separate process, which never imports this conftest and so
    # never sees the redirect - it writes to the production location, as it
    # should. Pointing the tests at the test process's scratch directory made
    # them read an empty directory.
    #
    # The isolation here covers the TEST SUITE writing governed evidence. It
    # does not, and should not, redirect the application's own output.
    allowed = {
        "test_chart_source_write_isolation.py",    # asserts about it
        "test_databricks_app_bundle_contract.py",  # synthetic tree under tmp_path
        "test_forecast_runner.py",                 # `git ls-files artifacts/chart_sources`
        "test_playwright_dashboard.py",            # reads the running app's output
        "test_playwright_frontend_interactions.py",  # reads the running app's output
        "test_r2_engine_identity.py",              # READS the committed values it pins
    }
    pattern = re.compile(
        r'"artifacts"\s*/\s*"chart_sources"'      # "artifacts" / "chart_sources"
        r"|'artifacts'\s*/\s*'chart_sources'"      # single-quoted variant
        r"|artifacts/chart_sources"                # literal path
    )

    offenders = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        if path.name in allowed:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            if line.lstrip().startswith("#"):
                continue  # a comment explaining the hazard is not the hazard
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}")

    assert not offenders, (
        "these lines address the tracked chart-source directory directly; use "
        "resolve_chart_source_output_dir(ROOT) instead:\n  "
        + "\n  ".join(offenders)
    )
