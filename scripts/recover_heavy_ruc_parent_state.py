from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
from typing import Any, Iterable
import zipfile

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/heavy_ruc")
DEBUG_DIR = Path("artifacts/heavy_ruc_forward_parity_debug")
PARITY_AUDIT = REPRO_ROOT / "forward_scorer_parity_audit.json"
FORWARD_STATE_MANIFEST = REPRO_ROOT / "forward_state_manifest.json"
PARENT_FORWARD_STATE_DIR = REPRO_ROOT / "parent_forward_state"
PARENT_FEATURE_MATRIX_DIR = REPRO_ROOT / "parent_feature_matrices"
MAX_VENDOR_BYTES = 50 * 1024 * 1024
PARITY_TOLERANCE = 1e-6
FINAL_GOVERNED_GAP_CONCLUSION = (
    "Original parent C3/C4 fitted estimator or feature matrix not retained. "
    "Heavy RUC cannot safely score new assumption rows from repo-local artifacts."
)

SEARCH_PATTERNS = (
    "heavy_ruc_fullgrid_rescue_closure*",
    "heavy_ruc_reconciliation*",
    "heavy_ruc_reproducibility_audit*",
    "heavy_ruc_finalist_exact_reproducibility_audit*",
)
INTERESTING_SUFFIXES = {".pkl", ".pickle", ".joblib", ".parquet", ".csv", ".xlsx", ".py", ".json", ".md"}
STATE_SUFFIXES = {".pkl", ".pickle", ".joblib"}
MATRIX_SUFFIXES = {".parquet", ".csv"}
TOKEN_GROUPS = {
    "state": ("model_state", "fitted", "estimator", "predictor", "joblib", "pickle"),
    "feature_matrix": ("feature_matrix", "training_matrix", "feature_rows", "feature_column", "target_lag_state"),
    "component_predictions": (
        "component_prediction",
        "component_predictions",
        "all_quarterly_predictions",
        "base_quarterly_predictions",
        "quarterly_predictions",
        "final_pred",
        "ensemble_weights",
    ),
    "source_code": ("heavy_ruc_fullgrid_rescue_closure.py", "reconciliation", "reproducibility_audit"),
}
LOCAL_PATH_TOKENS = ("C:\\Users", "C:/Users", "Downloads", "OneDrive", "AppData")


@dataclass(frozen=True)
class SearchRoot:
    source_location_class: str
    source_scope: str
    path: Path
    broad_repo_scan: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Final Heavy RUC parent-state recovery search.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEBUG_DIR)
    parser.add_argument("--update-parity-audit", action="store_true", default=True)
    parser.add_argument("--no-update-parity-audit", action="store_false", dest="update_parity_audit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = _resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    search_roots = _search_roots(repo_root)
    candidates, searched_sources = _collect_candidates(repo_root, search_roots)
    parent_state_candidates = [row for row in candidates if row["artifact_role"] == "original_parent_fitted_state"]
    parent_matrix_candidates = [row for row in candidates if row["artifact_role"] == "exact_parent_feature_matrix"]

    vendored_state = _vendor_parent_state(repo_root, parent_state_candidates, now)
    vendored_matrices = _vendor_parent_feature_matrices(repo_root, parent_matrix_candidates, now)

    recovered_parent_state = bool(vendored_state)
    recovered_parent_matrix = bool(vendored_matrices)
    capability_decision = (
        "requires_parent_state_parity_rerun"
        if recovered_parent_state or recovered_parent_matrix
        else "keep_parity_failed"
    )
    parity_rerun_status = (
        "not_run_recovered_parent_artifacts_require_explicit_parity_runner"
        if recovered_parent_state or recovered_parent_matrix
        else "not_run_no_parent_state_or_exact_matrix_recovered"
    )
    existing_parity = _read_json(_resolve(repo_root, PARITY_AUDIT))
    existing_forward_state = _read_json(_resolve(repo_root, FORWARD_STATE_MANIFEST))

    manifest = {
        "audit_name": "heavy_ruc_final_parent_state_recovery",
        "audit_version": "heavy-ruc-final-parent-state-search-v1",
        "created_at": now,
        "stream": "HEAVY_RUC",
        "stream_label": "Heavy RUC volume",
        "finalist_model": "HEAVY_RUC__RECON_STATIC_REBUILT",
        "parity_tolerance": PARITY_TOLERANCE,
        "max_vendor_bytes": MAX_VENDOR_BYTES,
        "search_scope": _public_search_scope(repo_root, search_roots),
        "search_patterns": list(SEARCH_PATTERNS),
        "searched_sources": searched_sources,
        "candidate_count": len(candidates),
        "candidate_role_counts": _counts(row["artifact_role"] for row in candidates),
        "candidate_status_counts": _counts(row["status"] for row in candidates),
        "recoverable_parent_state_found": recovered_parent_state,
        "recoverable_parent_feature_matrix_found": recovered_parent_matrix,
        "parent_forward_state": {
            "status": "vendored" if vendored_state else "not_found",
            "artifact_records": vendored_state,
        },
        "parent_feature_matrices": {
            "status": "vendored" if vendored_matrices else "not_found",
            "artifact_records": vendored_matrices,
        },
        "existing_source_refit_state": _existing_artifact_reference(repo_root, _resolve(repo_root, FORWARD_STATE_MANIFEST)),
        "existing_parity_audit": _existing_artifact_reference(repo_root, _resolve(repo_root, PARITY_AUDIT)),
        "existing_forward_state_manifest_summary": {
            "audit_name": existing_forward_state.get("audit_name"),
            "capability_decision": existing_forward_state.get("capability_decision"),
            "state_export_status": (existing_forward_state.get("state_export") or {}).get("status"),
            "state_file_count": (existing_forward_state.get("state_export") or {}).get("state_file_count"),
        },
        "existing_parity_summary": {
            "audit_name": existing_parity.get("audit_name"),
            "parity_status": existing_parity.get("parity_status"),
            "data_scope": existing_parity.get("data_scope"),
            "failing_component": existing_parity.get("failing_component"),
            "max_abs_delta": existing_parity.get("max_abs_delta"),
        },
        "stored_prediction_replay_status": "available_from_stored_parent_component_predictions",
        "training_fit_source_refit_status": "available_from_source_refit_state_not_parent_fitted_state",
        "new_row_forward_scoring_status": (
            "unavailable_until_parent_state_parity_passes"
            if not recovered_parent_state and not recovered_parent_matrix
            else "disabled_pending_parent_state_parity_rerun"
        ),
        "parity_rerun_status": parity_rerun_status,
        "capability_decision": capability_decision,
        "final_governed_gap_conclusion": FINAL_GOVERNED_GAP_CONCLUSION,
        "public_path_sanitization": "repo-relative paths or source classes only; no user-local absolute paths emitted",
        "artifact_outputs": [
            _repo_relative(repo_root, output_dir / "parent_state_search_manifest.json"),
            _repo_relative(repo_root, output_dir / "parent_state_search_report.md"),
            _repo_relative(repo_root, output_dir / "parent_state_candidates.csv"),
            _repo_relative(repo_root, output_dir / "final_heavy_forward_capability_decision.md"),
        ],
    }

    _write_candidates_csv(output_dir / "parent_state_candidates.csv", candidates)
    (output_dir / "parent_state_search_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (output_dir / "parent_state_search_report.md").write_text(_search_report(manifest, candidates), encoding="utf-8")
    (output_dir / "final_heavy_forward_capability_decision.md").write_text(
        _final_decision_markdown(manifest),
        encoding="utf-8",
    )

    _assert_public_outputs_sanitized(output_dir)
    if args.update_parity_audit:
        _update_parity_audit(repo_root, manifest)
    print(json.dumps({"status": "ok", "capability_decision": capability_decision, "candidate_count": len(candidates)}))


def _search_roots(repo_root: Path) -> list[SearchRoot]:
    home = Path.home()
    return [
        SearchRoot("repo_source_artifacts", "heavy_ruc_source_artifacts", repo_root / REPRO_ROOT / "source_artifacts", True),
        SearchRoot("repo_source_refit_state", "heavy_ruc_forward_state", repo_root / REPRO_ROOT / "forward_state", True),
        SearchRoot(
            "repo_source_refit_feature_matrices",
            "heavy_ruc_forward_feature_matrices",
            repo_root / REPRO_ROOT / "forward_feature_matrices",
            True,
        ),
        SearchRoot("repo_parity_debug", "heavy_ruc_forward_parity_debug", repo_root / DEBUG_DIR, True),
        SearchRoot("repo_model_input_history", "model_input_history", repo_root / "data" / "model_input_history", True),
        SearchRoot("repo_scripts", "repo_scripts_heavy_ruc", repo_root / "scripts", False),
        SearchRoot("external_user_candidate_drop", "local_heavy_ruc_named_candidates", home / "Downloads", False),
        SearchRoot(
            "external_model_input_candidate_drop",
            "local_model_inputs_named_candidates",
            home / "OneDrive" / "Documents" / "Playground" / "Revenue Modeling - Strategic Review" / "04 Models" / "Inputs",
            False,
        ),
    ]


def _collect_candidates(repo_root: Path, search_roots: list[SearchRoot]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    searched_sources: list[dict[str, Any]] = []
    seen: set[str] = set()

    for root in search_roots:
        if not root.path.exists():
            searched_sources.append(
                {
                    "source_location_class": root.source_location_class,
                    "source_scope": root.source_scope,
                    "status": "missing",
                    "candidate_file_count": 0,
                }
            )
            continue
        file_paths = list(_iter_root_files(root))
        searched_sources.append(
            {
                "source_location_class": root.source_location_class,
                "source_scope": root.source_scope,
                "status": "searched",
                "candidate_file_count": len(file_paths),
            }
        )
        for path in file_paths:
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.extend(_candidate_records_for_file(repo_root, root, path))

    for index, row in enumerate(candidates, start=1):
        row["candidate_id"] = f"heavy_parent_search_{index:04d}"
    return candidates, searched_sources


def _iter_root_files(root: SearchRoot) -> Iterable[Path]:
    if root.broad_repo_scan:
        yield from (path for path in root.path.rglob("*") if path.is_file())
        return
    if root.source_scope == "repo_scripts_heavy_ruc":
        yield from sorted(root.path.glob("*heavy_ruc*.py"))
        return
    selected: set[Path] = set()
    for pattern in SEARCH_PATTERNS:
        for match in root.path.glob(pattern):
            if match.is_file():
                selected.add(match)
            elif match.is_dir():
                selected.update(path for path in match.rglob("*") if path.is_file())
    selected.update(path for path in root.path.glob("*heavy_ruc*.py") if path.is_file())
    yield from sorted(selected)


def _candidate_records_for_file(repo_root: Path, root: SearchRoot, path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        return _archive_candidate_records(repo_root, root, path)
    if not _is_interesting_name(path.name):
        return []
    return [_record_for_artifact(repo_root, root, path, None, None, None)]


def _archive_candidate_records(repo_root: Path, root: SearchRoot, path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    container_sha = _sha256(path)
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                entry_name = _sanitize_archive_entry(info.filename)
                if not _is_interesting_name(entry_name):
                    continue
                entry_sha = ""
                if info.file_size <= MAX_VENDOR_BYTES:
                    try:
                        with archive.open(info) as handle:
                            entry_sha = _sha256_stream(handle)
                    except Exception:
                        entry_sha = ""
                records.append(_record_for_artifact(repo_root, root, path, info, entry_sha, container_sha))
    except zipfile.BadZipFile:
        return []
    return records


def _record_for_artifact(
    repo_root: Path,
    root: SearchRoot,
    path: Path,
    archive_info: zipfile.ZipInfo | None,
    archive_entry_sha256: str | None,
    container_sha256: str | None,
) -> dict[str, Any]:
    is_archive_entry = archive_info is not None
    raw_name = archive_info.filename if archive_info is not None else path.name
    safe_name = _sanitize_archive_entry(raw_name)
    basename = Path(safe_name).name
    suffix = Path(basename).suffix.lower()
    role, stage, status, notes = _classify(root, path, safe_name, suffix, is_archive_entry)
    size = archive_info.file_size if archive_info is not None else path.stat().st_size
    sha = archive_entry_sha256 if archive_info is not None else _sha256(path)
    if not sha and container_sha256:
        notes = f"{notes} Entry hash not computed; container hash recorded."
    return {
        "_source_path": str(path),
        "_archive_entry_raw": archive_info.filename if archive_info is not None else "",
        "candidate_id": "",
        "artifact_basename": _sanitize_text(basename),
        "container_basename": _sanitize_text(path.name if is_archive_entry else ""),
        "archive_entry_name": _sanitize_text(safe_name if is_archive_entry else ""),
        "source_location_class": root.source_location_class,
        "source_scope": root.source_scope,
        "repo_relative_path": _repo_relative(repo_root, path) if _is_relative_to(path, repo_root) else "",
        "artifact_role": role,
        "source_stage": stage,
        "size_bytes": int(size),
        "sha256": sha or "",
        "container_sha256": container_sha256 or "",
        "is_archive_entry": is_archive_entry,
        "status": status,
        "used_for_recovery": role in {"original_parent_fitted_state", "exact_parent_feature_matrix"},
        "required_for_replay": role in {"original_parent_fitted_state", "exact_parent_feature_matrix"},
        "vendor_repo_relative_path": "",
        "notes": _sanitize_text(notes),
    }


def _classify(root: SearchRoot, path: Path, name: str, suffix: str, is_archive_entry: bool) -> tuple[str, str, str, str]:
    haystack = " ".join([root.source_scope, path.name, name]).lower()
    has_state = any(token in haystack for token in TOKEN_GROUPS["state"])
    has_matrix = any(token in haystack for token in TOKEN_GROUPS["feature_matrix"])
    has_predictions = any(token in haystack for token in TOKEN_GROUPS["component_predictions"])
    has_source = any(token in haystack for token in TOKEN_GROUPS["source_code"])
    is_parent_named = "parent" in haystack or "fullgrid_rescue_closure" in haystack or "reconciliation" in haystack

    if root.source_location_class == "repo_source_refit_state" and suffix in STATE_SUFFIXES:
        return (
            "source_refit_state_not_parent",
            "source_refit_forward_state_export",
            "not_original_parent_state",
            "Source-refit state supports training-fit provenance but is not the retained parent fitted estimator.",
        )
    if root.source_location_class == "repo_source_refit_feature_matrices" and suffix in {".parquet", ".csv"}:
        return (
            "source_refit_feature_matrix_not_parent",
            "source_refit_forward_feature_export",
            "not_exact_parent_feature_matrix",
            "Feature matrix belongs to the source-refit forward audit, not to the original parent component run.",
        )
    if root.source_location_class == "repo_parity_debug":
        return (
            "parity_debug_evidence",
            "parity_debug",
            "diagnostic_evidence_not_parent_state",
            "Debug artifact documents parity status but is not a parent fitted estimator or exact parent feature matrix.",
        )
    if suffix in STATE_SUFFIXES and has_state and is_parent_named:
        return (
            "original_parent_fitted_state",
            "candidate_parent_run_state",
            "recoverable_parent_state_candidate",
            "Name and type indicate a possible retained parent fitted estimator; parity must pass before enabling Heavy numeric forecasts.",
        )
    if suffix in MATRIX_SUFFIXES and has_matrix and is_parent_named and "missing" not in haystack:
        return (
            "exact_parent_feature_matrix",
            "candidate_parent_run_feature_matrix",
            "recoverable_parent_feature_matrix_candidate",
            "Name and type indicate a possible exact parent feature matrix; parity must pass before enabling Heavy numeric forecasts.",
        )
    if has_predictions:
        return (
            "raw_parent_component_forecast_source",
            "parent_run_prediction_lineage",
            "stored_predictions_not_forward_state",
            "Stored component/final predictions prove replay lineage but cannot score new assumption rows by themselves.",
        )
    if has_matrix:
        return (
            "feature_matrix_lineage_reference",
            "feature_matrix_or_schema_lineage",
            "not_exact_parent_feature_matrix",
            "Feature-matrix reference found, but it is not an exact recoverable parent-run matrix.",
        )
    if has_state:
        return (
            "state_lineage_reference",
            "state_or_estimator_lineage",
            "not_original_parent_state",
            "State/estimator reference found, but it is not an original parent fitted estimator.",
        )
    if has_source or suffix == ".py":
        return (
            "source_code_reference",
            "source_code_lineage",
            "source_code_only",
            "Source code supports replay diagnosis but is not fitted state.",
        )
    if is_archive_entry:
        return (
            "archive_lineage_reference",
            "archive_lineage",
            "lineage_reference_only",
            "Archive entry matched the search suffix set but is not recoverable parent state.",
        )
    return (
        "lineage_reference",
        "lineage",
        "lineage_reference_only",
        "Artifact matched the search suffix set but is not recoverable parent state.",
    )


def _vendor_parent_state(repo_root: Path, candidates: list[dict[str, Any]], copied_at: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        if int(candidate["size_bytes"]) > MAX_VENDOR_BYTES:
            candidate["status"] = "oversized_not_vendored"
            continue
        target = _resolve(repo_root, PARENT_FORWARD_STATE_DIR) / candidate["artifact_basename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _copy_candidate_bytes(repo_root, candidate, target):
            continue
        record = _vendored_record(repo_root, candidate, target, copied_at)
        records.append(record)
        candidate["vendor_repo_relative_path"] = record["repo_relative_path"]
        candidate["status"] = "vendored_pending_parity"
    return records


def _vendor_parent_feature_matrices(repo_root: Path, candidates: list[dict[str, Any]], copied_at: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        if int(candidate["size_bytes"]) > MAX_VENDOR_BYTES:
            candidate["status"] = "oversized_not_vendored"
            continue
        source_bytes = _candidate_bytes(repo_root, candidate)
        if source_bytes is None:
            continue
        target = _resolve(repo_root, PARENT_FEATURE_MATRIX_DIR) / (Path(candidate["artifact_basename"]).stem + ".parquet")
        target.parent.mkdir(parents=True, exist_ok=True)
        suffix = Path(str(candidate["artifact_basename"])).suffix.lower()
        if suffix == ".parquet":
            target.write_bytes(source_bytes)
        elif suffix == ".csv":
            pd.read_csv(io.BytesIO(source_bytes)).to_parquet(target, index=False)
        else:
            candidate["status"] = "not_vendored_unsupported_matrix_format"
            continue
        record = _vendored_record(repo_root, candidate, target, copied_at)
        records.append(record)
        candidate["vendor_repo_relative_path"] = record["repo_relative_path"]
        candidate["status"] = "vendored_pending_parity"
    return records


def _copy_candidate_bytes(repo_root: Path, candidate: dict[str, Any], target: Path) -> bool:
    if candidate.get("is_archive_entry"):
        data = _candidate_bytes(repo_root, candidate)
        if data is None:
            return False
        target.write_bytes(data)
        return True
    source = _candidate_source_path(repo_root, candidate)
    if source is None:
        return False
    shutil.copy2(source, target)
    return True


def _candidate_bytes(repo_root: Path, candidate: dict[str, Any]) -> bytes | None:
    if candidate.get("is_archive_entry"):
        source_path = Path(str(candidate.get("_source_path") or ""))
        entry = str(candidate.get("_archive_entry_raw") or "")
        if not source_path.exists() or not entry:
            return None
        try:
            with zipfile.ZipFile(source_path) as archive:
                with archive.open(entry) as handle:
                    return handle.read()
        except Exception:
            return None
    source = _candidate_source_path(repo_root, candidate)
    if source is None or not source.exists():
        return None
    return source.read_bytes()


def _candidate_source_path(repo_root: Path, candidate: dict[str, Any]) -> Path | None:
    if candidate.get("is_archive_entry"):
        return None
    repo_relative_path = str(candidate.get("repo_relative_path") or "")
    if repo_relative_path:
        return _resolve(repo_root, Path(repo_relative_path))
    source_path = Path(str(candidate.get("_source_path") or ""))
    if source_path.exists():
        return source_path
    return None


def _vendored_record(repo_root: Path, candidate: dict[str, Any], target: Path, copied_at: str) -> dict[str, Any]:
    return {
        "artifact_name": target.name,
        "repo_relative_path": _repo_relative(repo_root, target),
        "original_basename": candidate["artifact_basename"],
        "artifact_role": candidate["artifact_role"],
        "source_stage": candidate["source_stage"],
        "size_bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "copied_at": copied_at,
        "used_by_exporter": False,
        "required_for_replay": True,
        "status": "vendored_pending_parity",
        "notes": "Vendored by final parent-state recovery search; Heavy numeric forecasts remain disabled until parity passes.",
    }


def _update_parity_audit(repo_root: Path, manifest: dict[str, Any]) -> None:
    audit_path = _resolve(repo_root, PARITY_AUDIT)
    audit = _read_json(audit_path)
    diagnosis = audit.get("diagnosis") if isinstance(audit.get("diagnosis"), dict) else {}
    diagnosis.update(
        {
            "capability_decision": manifest["capability_decision"],
            "final_parent_state_recovery_status": (
                "original_parent_state_or_matrix_recovered_pending_parity"
                if manifest["recoverable_parent_state_found"] or manifest["recoverable_parent_feature_matrix_found"]
                else "original_parent_state_not_found"
            ),
            "parent_state_search_manifest": "artifacts/heavy_ruc_forward_parity_debug/parent_state_search_manifest.json",
            "parent_state_search_report": "artifacts/heavy_ruc_forward_parity_debug/parent_state_search_report.md",
            "parent_state_candidates": "artifacts/heavy_ruc_forward_parity_debug/parent_state_candidates.csv",
            "final_heavy_forward_capability_decision": (
                "artifacts/heavy_ruc_forward_parity_debug/final_heavy_forward_capability_decision.md"
            ),
            "final_parent_state_search": {
                "recoverable_parent_state_found": manifest["recoverable_parent_state_found"],
                "recoverable_parent_feature_matrix_found": manifest["recoverable_parent_feature_matrix_found"],
                "candidate_count": manifest["candidate_count"],
                "candidate_role_counts": manifest["candidate_role_counts"],
                "parity_rerun_status": manifest["parity_rerun_status"],
                "final_governed_gap_conclusion": manifest["final_governed_gap_conclusion"],
            },
            "stored_prediction_replay_status": manifest["stored_prediction_replay_status"],
            "training_fit_source_refit_status": manifest["training_fit_source_refit_status"],
            "new_row_forward_scoring_status": manifest["new_row_forward_scoring_status"],
        }
    )
    audit.update(
        {
            "audit_name": "heavy_ruc_final_parent_state_recovery",
            "audit_version": "heavy-ruc-final-parent-state-search-v1",
            "data_scope": "canonical_source_script_history_component_replay_with_source_refit_state_export_final_parent_state_search",
            "capability_status": "parity_failed",
            "capability_decision": manifest["capability_decision"],
            "parity_status": "failed",
            "missing_feature_or_artifact": (
                f"{FINAL_GOVERNED_GAP_CONCLUSION} Source-script Stage 1 workbook history was recovered and "
                "deterministic source-refit state was exported, but the target-lagged GBM components C3/C4 still "
                "exceed parity tolerance; parent fitted component estimators or parent feature matrices were not "
                "found in the final sanitized search."
            ),
            "notes": (
                "Exact stored prediction replay is available from parent component predictions; Heavy training-fit "
                "R2/provenance is available from source-refit state; new-row forward scoring remains unavailable "
                "until original parent state or exact parent feature matrices pass parity."
            ),
            "diagnosis": diagnosis,
        }
    )
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _write_candidates_csv(path: Path, candidates: list[dict[str, Any]]) -> None:
    fieldnames = [
        "candidate_id",
        "artifact_basename",
        "container_basename",
        "archive_entry_name",
        "source_location_class",
        "source_scope",
        "repo_relative_path",
        "artifact_role",
        "source_stage",
        "size_bytes",
        "sha256",
        "container_sha256",
        "is_archive_entry",
        "status",
        "used_for_recovery",
        "required_for_replay",
        "vendor_repo_relative_path",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in candidates:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _search_report(manifest: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    role_counts = manifest["candidate_role_counts"]
    status_counts = manifest["candidate_status_counts"]
    lines = [
        "# Heavy RUC Final Parent-State Search",
        "",
        f"- Audit: `{manifest['audit_name']}`",
        f"- Created: `{manifest['created_at']}`",
        f"- Candidate artifacts inspected: `{manifest['candidate_count']}`",
        f"- Recoverable parent fitted state found: `{str(manifest['recoverable_parent_state_found']).lower()}`",
        f"- Recoverable exact parent feature matrix found: `{str(manifest['recoverable_parent_feature_matrix_found']).lower()}`",
        f"- Capability decision: `{manifest['capability_decision']}`",
        f"- Parity rerun status: `{manifest['parity_rerun_status']}`",
        "",
        "## Final Conclusion",
        "",
        FINAL_GOVERNED_GAP_CONCLUSION,
        "",
        "Exact stored prediction replay remains available from stored parent component predictions. "
        "Training-fit R2/provenance remains available from the source-refit state export. "
        "New-row Heavy RUC forward scoring remains unavailable until original parent state or exact parent feature "
        "matrices are recovered and pass component plus final weighted replay parity.",
        "",
        "## Candidate Role Counts",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(role_counts.items()))
    lines.extend(["", "## Candidate Status Counts", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(status_counts.items()))
    lines.extend(["", "## Search Sources", ""])
    for row in manifest["searched_sources"]:
        lines.append(
            f"- `{row['source_location_class']}` / `{row['source_scope']}`: "
            f"`{row['status']}`, files scanned `{row['candidate_file_count']}`"
        )
    lines.extend(["", "## Notable Lineage", ""])
    for row in candidates[:20]:
        lines.append(
            f"- `{row['candidate_id']}` `{row['artifact_role']}` `{row['status']}`: "
            f"`{row['artifact_basename']}`"
        )
    return "\n".join(lines) + "\n"


def _final_decision_markdown(manifest: dict[str, Any]) -> str:
    return (
        "# Heavy RUC Forward Capability Decision\n\n"
        f"{FINAL_GOVERNED_GAP_CONCLUSION}\n\n"
        "- Stored prediction replay: available from stored parent component predictions.\n"
        "- Training-fit R2/provenance: available from source-refit state, not original parent fitted state.\n"
        "- New-row forward scoring: unavailable until parent state parity passes.\n"
        f"- Capability decision: `{manifest['capability_decision']}`.\n"
        f"- Parity rerun status: `{manifest['parity_rerun_status']}`.\n"
    )


def _public_search_scope(repo_root: Path, search_roots: list[SearchRoot]) -> list[dict[str, Any]]:
    scope: list[dict[str, Any]] = []
    for root in search_roots:
        scope.append(
            {
                "source_location_class": root.source_location_class,
                "source_scope": root.source_scope,
                "repo_relative_path": _repo_relative(repo_root, root.path) if _is_relative_to(root.path, repo_root) else "",
                "path_public": False if not _is_relative_to(root.path, repo_root) else True,
            }
        )
    return scope


def _existing_artifact_reference(repo_root: Path, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"repo_relative_path": _repo_relative(repo_root, path), "status": "missing", "sha256": "", "size_bytes": 0}
    return {
        "repo_relative_path": _repo_relative(repo_root, path),
        "status": "present",
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _is_interesting_name(value: str) -> bool:
    name = value.lower().replace("\\", "/")
    suffix = Path(name).suffix.lower()
    if suffix in STATE_SUFFIXES:
        return True
    return suffix in INTERESTING_SUFFIXES and any(
        token in name for group in TOKEN_GROUPS.values() for token in group
    )


def _sanitize_archive_entry(value: str) -> str:
    text = value.replace("\\", "/").strip("/")
    if any(token.lower().replace("\\", "/") in text.lower() for token in LOCAL_PATH_TOKENS):
        return Path(text).name
    return text


def _sanitize_text(value: Any) -> str:
    text = str(value or "")
    for token in LOCAL_PATH_TOKENS:
        text = text.replace(token, "[local-path-hidden]")
    return text


def _assert_public_outputs_sanitized(output_dir: Path) -> None:
    for name in [
        "parent_state_search_manifest.json",
        "parent_state_search_report.md",
        "parent_state_candidates.csv",
        "final_heavy_forward_capability_decision.md",
    ]:
        path = output_dir / name
        text = path.read_text(encoding="utf-8")
        leaked = [token for token in LOCAL_PATH_TOKENS if token in text]
        if leaked:
            raise RuntimeError(f"{name} contains local path token(s): {', '.join(leaked)}")


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return ""


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return _sha256_stream(handle)


def _sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_default(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return str(value)


if __name__ == "__main__":
    main()
