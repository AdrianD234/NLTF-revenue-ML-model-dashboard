from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def path_text(path: Path | None) -> str:
    return str(path.resolve() if path and path.exists() else path or "")


def build_data_source_manifest(
    *,
    requested_data_root: str | Path,
    search_roots: list[Path],
    parquet_path: Path | None,
    metadata_path: Path | None,
    csv_mirror_path: Path | None,
    diagnostic_paths: dict[str, Path],
    source_mode: str,
) -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_mode": source_mode,
        "requested_data_root": str(Path(requested_data_root).expanduser()),
        "search_roots": [path_text(path) for path in search_roots],
        "resolved_paths": {
            "candidate_parquet": path_text(parquet_path),
            "candidate_metadata": path_text(metadata_path),
            "candidate_csv_mirror": path_text(csv_mirror_path),
            "diagnostics": {name: path_text(path) for name, path in sorted(diagnostic_paths.items())},
        },
    }


def write_data_source_manifest(repo_root: str | Path, manifest: dict[str, Any]) -> Path:
    output_path = Path(repo_root).expanduser() / "artifacts" / "data_source_manifest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_path
