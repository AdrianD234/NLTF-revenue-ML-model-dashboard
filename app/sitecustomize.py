"""Prefer repo-local parquet runtime wheels when available.

The committed evidence packs were written with a newer PyArrow than the base
Conda runtime in this Windows workspace. Python imports this module at startup
when the repo root is on ``sys.path``, before pandas chooses a parquet engine.
"""

from __future__ import annotations

from pathlib import Path
import sys


_RUNTIME = Path(__file__).resolve().parent / ".runtime_pyarrow24"
if _RUNTIME.exists():
    runtime_path = str(_RUNTIME)
    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)
