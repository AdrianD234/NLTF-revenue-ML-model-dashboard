from __future__ import annotations

from pathlib import Path

from .config import DashboardData


def legacy_review_warning(path: str | Path) -> str:
    return (
        "Legacy run-folder CSV/XLSX loading is available only for review and migration. "
        f"It is not the governed default dashboard source: {Path(path).expanduser()}"
    )


__all__ = ["DashboardData", "legacy_review_warning"]
