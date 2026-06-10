from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


NUMERIC_FORECAST_AVAILABLE = "numeric_forecast_available"
GOVERNED_GAP = "governed_gap"
PARITY_FAILED = "parity_failed"
INSUFFICIENT_ARTIFACTS = "insufficient_artifacts"

CAPABILITY_STATES = {
    NUMERIC_FORECAST_AVAILABLE,
    GOVERNED_GAP,
    PARITY_FAILED,
    INSUFFICIENT_ARTIFACTS,
}


@dataclass(frozen=True)
class ForwardScorerAudit:
    stream: str
    stream_label: str
    model: str
    capability_status: str
    gap_code: str | None
    gap_reason: str
    repo_artifact_basis: str
    scorer_version: str
    parity_status: str
    max_parity_delta: float | None = None
    stored_replay_max_delta: float | None = None
    source_artifact_hashes: dict[str, str] = field(default_factory=dict)
    missing_artifacts: tuple[str, ...] = ()
    required_components: tuple[str, ...] = ()
    forecast_capability_available: bool = False

    def to_capability_record(self) -> dict[str, Any]:
        return {
            "stream": self.stream,
            "stream_label": self.stream_label,
            "model": self.model,
            "forecast_capability_available": bool(self.forecast_capability_available),
            "capability_status": self.capability_status,
            "gap_code": self.gap_code,
            "gap_reason": self.gap_reason,
            "repo_artifact_basis": self.repo_artifact_basis,
            "scorer_version": self.scorer_version,
            "parity_status": self.parity_status,
            "max_parity_delta": self.max_parity_delta if self.max_parity_delta is not None else pd.NA,
            "stored_replay_max_delta": self.stored_replay_max_delta if self.stored_replay_max_delta is not None else pd.NA,
            "source_artifact_hashes": json.dumps(self.source_artifact_hashes, sort_keys=True),
            "missing_artifacts": "; ".join(self.missing_artifacts),
            "required_components": "; ".join(self.required_components),
            "required_for_forward_forecast": True,
        }


def repo_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def existing_basis(root: Path, paths: list[Path]) -> str:
    return "; ".join(repo_relative(root, path) for path in paths if path.exists())


def missing_paths(root: Path, paths: list[Path]) -> tuple[str, ...]:
    return tuple(repo_relative(root, path) for path in paths if not path.exists())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in paths:
        if path.exists() and path.is_file():
            hashes[repo_relative(root, path)] = sha256_file(path)
    return hashes


def json_record(audit: ForwardScorerAudit) -> dict[str, Any]:
    record = audit.to_capability_record()
    record["max_parity_delta"] = None if pd.isna(record["max_parity_delta"]) else record["max_parity_delta"]
    record["stored_replay_max_delta"] = None if pd.isna(record["stored_replay_max_delta"]) else record["stored_replay_max_delta"]
    record["source_artifact_hashes"] = audit.source_artifact_hashes
    record["missing_artifacts"] = list(audit.missing_artifacts)
    record["required_components"] = list(audit.required_components)
    return record
