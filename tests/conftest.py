from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

import pytest


RUNTIME_PYARROW24 = Path(__file__).resolve().parents[1] / ".runtime_pyarrow24"
if RUNTIME_PYARROW24.exists() and str(RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(RUNTIME_PYARROW24))


@pytest.fixture
def tmp_path() -> Path:
    root = Path(__file__).resolve().parents[1] / "test-output" / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid4().hex
    path.mkdir()
    return path
