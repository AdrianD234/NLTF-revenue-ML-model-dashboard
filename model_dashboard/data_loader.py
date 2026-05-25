from __future__ import annotations

from .data.config import (
    DEFAULT_DIAGNOSTIC_AUDIT_ROOT,
    DEFAULT_DIAGNOSTIC_DATA_ROOT,
    DEFAULT_INFORMATION_PACK_ROOT,
    DashboardData,
    PARQUET_CANDIDATE_FILE,
    PARQUET_CSV_MIRROR_FILE,
    PARQUET_METADATA_FILE,
)
from .data.legacy_loader import (
    curated_manifest_matches,
    curated_signature,
    discover_run_folders,
    legacy_review_warning,
    load_curated_run,
    load_run,
    run_has_outputs,
    run_signature,
)
from .data.locate import locate_dashboard_file
from .data.parquet_loader import (
    build_ensemble_composition_source_table,
    build_horizon_comparison_source_table,
    build_scenario_comparison_source_table,
    load_parquet_dashboard,
    parquet_pack_signature,
)


LoadedRun = DashboardData

STALE_FINALIST_VALUES = {
    "PED": 5.49,
    "LIGHT_RUC": 11.55,
    "HEAVY_RUC": 12.38,
}

__all__ = [
    "DEFAULT_DIAGNOSTIC_AUDIT_ROOT",
    "DEFAULT_DIAGNOSTIC_DATA_ROOT",
    "DEFAULT_INFORMATION_PACK_ROOT",
    "DashboardData",
    "LoadedRun",
    "PARQUET_CANDIDATE_FILE",
    "PARQUET_CSV_MIRROR_FILE",
    "PARQUET_METADATA_FILE",
    "STALE_FINALIST_VALUES",
    "build_ensemble_composition_source_table",
    "build_horizon_comparison_source_table",
    "build_scenario_comparison_source_table",
    "curated_manifest_matches",
    "curated_signature",
    "discover_run_folders",
    "legacy_review_warning",
    "load_curated_run",
    "load_parquet_dashboard",
    "load_run",
    "locate_dashboard_file",
    "parquet_pack_signature",
    "run_has_outputs",
    "run_signature",
]
