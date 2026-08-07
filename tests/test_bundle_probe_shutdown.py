"""The bundle probe must exit 0 with valid JSON - and with no warmer thread.

Regression cover for a real publish-gate failure. The probe used to let the
app spawn its ``revenue-outlook-cache-warmer`` daemon threads; instrumented
runs showed them still alive inside native numpy/pyarrow code at interpreter
exit in EVERY run, crashing teardown in about half:

    terminate called without an active exception
    Fatal Python error: Aborted / Segmentation fault

so the publish workflow failed on a coin flip (hosted runs 31219276724 and
31224208227, diagnosis under artifacts/ci_optimisation/probe_matrix/). The fix
sets ``REVENUE_OUTLOOK_CACHE_WARMER=0`` in ``probe_env`` - the same disable,
for the same reason, that tests/conftest.py applies to the test suite.

Why these tests assert the census and not merely a clean exit: before the fix
a clean exit happened ~50% of the time, so "ran once, exited 0" is nearly
worthless as a regression signal. "The warmer thread does not exist" is
deterministic.

The probe body is the validator's own ``_PROBE`` string, executed as a real
subprocess under the validator's own ``probe_env`` - the exact gate path, not
a reconstruction. Do NOT weaken these to accept valid JSON with a non-zero
exit; the process exit code is part of the validation contract.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

WARMER_THREAD_NAME = "revenue-outlook-cache-warmer"
ABORT_SIGNATURE = "terminate called without an active exception"

# Appended after the probe's final statement, so it is the last Python to run
# before interpreter teardown - the census reflects exactly what teardown will
# have to survive.
CENSUS_SNIPPET = (
    "\n"
    "import threading as _census_threading\n"
    'print("===THREAD-CENSUS-BEGIN===")\n'
    "for _census_thread in _census_threading.enumerate():\n"
    "    print(f\"thread name={_census_thread.name!r} daemon={_census_thread.daemon}\")\n"
    'print("===THREAD-CENSUS-END===", flush=True)\n'
)


@pytest.fixture(scope="module")
def validator():
    spec = importlib.util.spec_from_file_location(
        "validate_databricks_app_bundle",
        ROOT / "scripts" / "validate_databricks_app_bundle.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_probe_subprocess(
    validator, cwd: pathlib.Path, monkeypatch
) -> subprocess.CompletedProcess:
    # tests/conftest.py sets REVENUE_OUTLOOK_CACHE_WARMER=0 for the whole test
    # process, and probe_env copies os.environ - so under pytest the warmer is
    # disabled by INHERITANCE even if probe_env stops disabling it. The first
    # mutation check of this suite proved it: with the fix deleted, these tests
    # still passed. Removing the variable here forces probe_env to supply the
    # disable itself, which is the thing being regression-tested. The publish
    # workflow has no conftest.
    monkeypatch.delenv("REVENUE_OUTLOOK_CACHE_WARMER", raising=False)
    return subprocess.run(
        [sys.executable, "-c", validator._PROBE + CENSUS_SNIPPET],
        cwd=cwd,
        env=validator.probe_env(cwd),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )


def assert_clean_probe(result: subprocess.CompletedProcess, label: str) -> None:
    stderr_tail = (result.stderr or "")[-1500:]

    # The contract, in full: exit 0 AND complete valid JSON AND no abort.
    assert ABORT_SIGNATURE not in (result.stderr or ""), (
        f"{label}: native teardown abort recurred:\n{stderr_tail}"
    )
    assert result.returncode == 0, (
        f"{label}: probe exited {result.returncode}, not 0:\n{stderr_tail}"
    )
    begin = result.stdout.find("===PROBE-JSON-BEGIN===")
    end = result.stdout.find("===PROBE-JSON-END===")
    assert begin >= 0 and end > begin, f"{label}: probe JSON markers missing"
    payload = json.loads(
        result.stdout[begin + len("===PROBE-JSON-BEGIN===") : end].strip()
    )
    assert payload.get("errors") == [], f"{label}: probe errors: {payload.get('errors')}"

    # The mechanism, asserted deterministically: the warmer must never spawn.
    census_start = result.stdout.find("===THREAD-CENSUS-BEGIN===")
    assert census_start >= 0, f"{label}: census never ran"
    assert WARMER_THREAD_NAME not in result.stdout, (
        f"{label}: a {WARMER_THREAD_NAME!r} thread was spawned inside the probe. "
        "probe_env must disable it (REVENUE_OUTLOOK_CACHE_WARMER=0): a live "
        "warmer at interpreter exit crashed teardown in ~half of measured runs."
    )


def test_probe_env_disables_the_cache_warmer(validator):
    """The cheap, instant assertion on the gate's own environment builder."""
    env = validator.probe_env(ROOT)
    assert env.get("REVENUE_OUTLOOK_CACHE_WARMER") == "0"


def test_probe_env_is_a_hard_disable_not_a_default(validator, monkeypatch):
    """An inherited '1' from the caller's environment must not re-enable it."""
    monkeypatch.setenv("REVENUE_OUTLOOK_CACHE_WARMER", "1")
    env = validator.probe_env(ROOT)
    assert env.get("REVENUE_OUTLOOK_CACHE_WARMER") == "0", (
        "probe_env must override an inherited warmer setting; a deterministic "
        "gate cannot host a background warmer under any configuration"
    )


def test_source_probe_exits_cleanly_with_no_warmer_thread(validator, monkeypatch):
    """Source execution: the case the failing hosted validator never reached."""
    if not (ROOT / "data" / "current_revenue_outlook").is_dir():
        pytest.skip("governed packs not present")
    result = run_probe_subprocess(validator, ROOT, monkeypatch)
    assert_clean_probe(result, "source probe")


def test_bundle_probe_exits_cleanly_with_no_warmer_thread(validator, tmp_path, monkeypatch):
    """Bundled execution: the case that actually gates publication."""
    if not (ROOT / "data" / "current_revenue_outlook").is_dir():
        pytest.skip("governed packs not present")

    bundle = tmp_path / "app"
    build = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_databricks_app_bundle.py"),
            "--source", str(ROOT),
            "--output", str(bundle),
            "--clean",
        ],
        text=True,
        capture_output=True,
        timeout=900,
    )
    assert build.returncode == 0, f"bundle build failed:\n{build.stderr[-1500:]}"

    result = run_probe_subprocess(validator, bundle, monkeypatch)
    assert_clean_probe(result, "bundle probe")
