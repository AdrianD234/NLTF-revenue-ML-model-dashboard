from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest


RUNTIME_PYARROW24 = Path(__file__).resolve().parents[1] / ".runtime_pyarrow24"
if RUNTIME_PYARROW24.exists() and str(RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(RUNTIME_PYARROW24))

# The app's cloud-runtime preview defaults ON for humans; the suite exercises
# local analyst behaviour, so pin the default OFF here. Tests that assert the
# ON default explicitly monkeypatch this variable away (test_executive_mode).
os.environ.setdefault("CLOUD_PREVIEW_DEFAULT", "0")

# The background cache warmer would burn ~20s of CPU per AppTest process and
# add nondeterminism; the suite exercises the cold and warm paths explicitly.
os.environ.setdefault("REVENUE_OUTLOOK_CACHE_WARMER", "0")

# Chart source tables are written as a SIDE EFFECT of loading an evidence pack,
# and seven test modules load one. Left alone, the suite therefore rewrites
# tracked files under artifacts/chart_sources on every run:
#
#   * on Linux that alone rewrote CRLF to LF (7944 -> 7937 bytes, no value
#     changed), so "the suite leaves the checkout unchanged" was simply untrue;
#   * under pytest-xdist, four worker processes writing the same files
#     concurrently moved a governed PED calibration R-squared from 0.559 to
#     0.580 while every test still passed.
#
# See artifacts/ci_optimisation/xdist_benchmark.md and
# docs/FOLLOW_UP_PED_R2_DRIFT.md.
#
# Redirect every test-run write to a process-unique scratch directory. The
# xdist worker id and the pid both appear, so no two workers - and no two
# concurrent runs - can ever target the same path. Production is untouched:
# nothing outside the tests sets this variable, so the committed location
# remains the default.
#
# A plain ``setdefault`` is NOT enough. Under pytest-xdist the CONTROLLER
# imports this conftest first and its setdefault lands in the environment the
# workers inherit, so every worker's setdefault then keeps the controller's
# directory and all workers share one destination - which is the incident this
# redirect exists to prevent, merely relocated into scratch. (Measured: two
# workers racing in one shared scratch directory produced FileNotFoundError
# collisions in the atomic CSV writer's tmp-rename. See
# artifacts/governed_artifact_reproducibility/r2_parallel_diagnosis.md.)
#
# The sentinel records the value this conftest derived. If the variable equals
# the sentinel it was inherited from a parent test process, not set by a user,
# and is re-derived for THIS process. A user-supplied override never matches
# the sentinel and is always honoured.
#
# This does NOT resolve which R-squared values are authoritative. That is a
# governance question, answered in tests/test_r2_engine_identity.py.
_CHART_SOURCE_SCRATCH = (
    Path(__file__).resolve().parents[1]
    / "test-output"
    / "chart_sources"
    / f"{os.environ.get('PYTEST_XDIST_WORKER', 'main')}-{os.getpid()}"
)
_CHART_SOURCE_SENTINEL = "NLTF_CHART_SOURCE_OUTPUT_DIR_AUTOSET"
_existing = os.environ.get("NLTF_CHART_SOURCE_OUTPUT_DIR")
if _existing is None or _existing == os.environ.get(_CHART_SOURCE_SENTINEL):
    _CHART_SOURCE_SCRATCH.mkdir(parents=True, exist_ok=True)
    os.environ["NLTF_CHART_SOURCE_OUTPUT_DIR"] = str(_CHART_SOURCE_SCRATCH)
    os.environ[_CHART_SOURCE_SENTINEL] = str(_CHART_SOURCE_SCRATCH)


@pytest.fixture
def tmp_path() -> Path:
    root = Path(__file__).resolve().parents[1] / "test-output" / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid4().hex
    path.mkdir()
    return path


@pytest.fixture
def real_chart_rows():
    """The committed production chart rows.

    Fault injection runs against the real promoted frame rather than a
    hand-built stub, so a mutation test proves the gate fires on the shape
    production actually has.
    """
    import pandas as pd

    path = Path(__file__).resolve().parents[1] / "data" / "current_revenue_outlook" / "revenue_chart_rows.csv"
    if not path.exists():
        pytest.skip("committed revenue outlook pack is not present")
    return pd.read_csv(path, low_memory=False)


@pytest.fixture(scope="module")
def vfm_analyst_layers_enabled():
    """Run a test with the paused MoT VFM Fast/Slow surface switched back on.

    The public dashboard hides those layers
    (``REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = False``) and, deliberately,
    hiding them also stops their calculations running - the Fast/Slow cone band
    is simply not built. The calculation chain and its governance identities
    are RETAINED so the feature can be restored by flipping that one constant,
    so the tests that protect it opt in here rather than being deleted.

    The view cache is cleared either side: entries computed under the other
    setting carry a different cone band and must not leak in or out.

    Module-scoped on purpose: these suites build their figure or view through
    a module-scoped fixture, and pytest sets higher-scoped fixtures up first,
    so a function-scoped gate would not yet be open when they are built.
    """
    import app
    import model_dashboard.revenue_outlook_presentation_policy as policy

    previous_policy = policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
    previous_app = app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
    policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = True
    app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = True
    app.cached_revenue_outlook_view.clear()
    try:
        yield
    finally:
        policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = previous_policy
        app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = previous_app
        app.cached_revenue_outlook_view.clear()
