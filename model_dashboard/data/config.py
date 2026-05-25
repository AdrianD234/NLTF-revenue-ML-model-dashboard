from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import pandas as pd


PARQUET_CANDIDATE_FILE = "stage1_curated_candidate_cone.parquet"
PARQUET_METADATA_FILE = "stage1_curated_candidate_cone_metadata.json"
PARQUET_CSV_MIRROR_FILE = "stage1_curated_candidate_cone.csv"


def env_path(*names: str, default: str | Path = "data") -> Path:
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    return Path(default).expanduser()


DEFAULT_DIAGNOSTIC_DATA_ROOT = env_path("MODEL_DIAGNOSTIC_DATA_ROOT", "STAGE1_DASHBOARD_DATA_ROOT")
DEFAULT_DIAGNOSTIC_AUDIT_ROOT = DEFAULT_DIAGNOSTIC_DATA_ROOT
DEFAULT_INFORMATION_PACK_ROOT = env_path(
    "MODEL_INFORMATION_PACK_ROOT",
    "STAGE1_INFORMATION_PACK_ROOT",
    default=DEFAULT_DIAGNOSTIC_DATA_ROOT,
)
DEFAULT_INPUT_PARENT = env_path("MODEL_INPUT_PARENT", "STAGE1_MODEL_INPUT_PARENT", default=Path("data") / "legacy_runs")
DEFAULT_BESPOKE_PARENT = env_path(
    "MODEL_BESPOKE_PARENT",
    "STAGE1_BESPOKE_PARENT",
    default=DEFAULT_INPUT_PARENT / "bespoke_solver_stage1_outputs",
)


@dataclass(frozen=True)
class DashboardData:
    """Fully prepared data contract consumed by Streamlit.

    The app should not know whether the tables came from Parquet, diagnostics,
    or a legacy review loader. It receives named frames plus status/warnings.
    """

    run_dir: Path
    data: dict[str, pd.DataFrame]
    file_status: pd.DataFrame
    warnings: tuple[str, ...]
    manifest: dict[str, Any] | None = None
