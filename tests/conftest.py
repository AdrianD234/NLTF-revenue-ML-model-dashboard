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
