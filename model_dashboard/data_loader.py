from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .labels import IGNORED_RUN_FOLDER_NAMES, humanize_label
from .metrics import (
    add_stream_fields,
    derive_paired_from_summary,
    normalise_paired,
    normalise_predictions,
    normalise_recommended,
    normalise_stress,
    normalise_summary,
    normalise_weights,
    percent_unit_warnings,
)
from .schema import FILE_ALIASES, SHEET_HINTS, WORKBOOK_ALIASES, WORKBOOK_DATASETS


@dataclass(frozen=True)
class LoadedRun:
    run_dir: Path
    data: dict[str, pd.DataFrame]
    file_status: pd.DataFrame
    warnings: tuple[str, ...]


CURATED_FILE_MAP = {
    "finalist_accuracy": "finalist_accuracy.csv",
    "candidate_landscape": "candidate_landscape_sample.csv",
    "schiff_benchmark": "schiff_benchmark.csv",
    "pdf_comparison": "pdf_comparison.csv",
    "stress_horizon": "stress_horizon.csv",
    "ensemble_composition": "ensemble_composition.csv",
    "paired_vs_schiff_selected": "paired_vs_schiff_selected.csv",
    "annual_predictions_selected": "annual_predictions_selected.csv",
    "quarterly_predictions_selected": "quarterly_predictions_selected.csv",
}


def discover_run_folders(parent: Path, ignore_names: set[str] | None = None) -> list[Path]:
    ignored = ignore_names or IGNORED_RUN_FOLDER_NAMES
    if not parent.exists():
        return []
    candidates: list[Path] = []
    if parent.is_dir() and parent.name.startswith("run_"):
        candidates.append(parent)
    candidates.extend(path for path in parent.rglob("run_*") if path.is_dir())
    unique = sorted(set(candidates), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return [path for path in unique if path.name not in ignored and run_has_outputs(path)]


def run_has_outputs(run_dir: Path) -> bool:
    if not run_dir.exists() or not run_dir.is_dir():
        return False
    names = {name.lower() for aliases in FILE_ALIASES.values() for name in aliases}
    for child in run_dir.iterdir():
        if child.is_file() and child.name.lower() in names and child.stat().st_size > 0:
            return True
    return False


def run_signature(run_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not run_dir.exists() or not run_dir.is_dir():
        return tuple()
    rows = []
    for child in sorted(run_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.is_file():
            stat = child.stat()
            rows.append((child.name, stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def curated_signature(curated_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not curated_dir.exists() or not curated_dir.is_dir():
        return tuple()
    rows = []
    for child in sorted(curated_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.is_file():
            stat = child.stat()
            rows.append((child.name, stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def curated_manifest_matches(curated_dir: Path, run_dir: str | Path) -> bool:
    manifest_path = curated_dir / "curation_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    manifest_run = Path(str(manifest.get("run_dir", ""))).expanduser()
    return manifest_run == Path(run_dir).expanduser()


def load_curated_run(curated_dir: str | Path, run_dir: str | Path) -> LoadedRun:
    curated_path = Path(curated_dir).expanduser()
    run_path = Path(run_dir).expanduser()
    warnings: list[str] = []
    if not curated_path.exists() or not curated_path.is_dir():
        warnings.append(f"Curated data directory does not exist: {curated_path}")
        return LoadedRun(run_path, {}, _empty_status_frame(), tuple(warnings))

    if not curated_manifest_matches(curated_path, run_path):
        warnings.append(f"Curated manifest does not match active run folder: {run_path}")

    raw: dict[str, pd.DataFrame] = {}
    status_rows: list[dict[str, Any]] = []
    for dataset, filename in CURATED_FILE_MAP.items():
        path = curated_path / filename
        dataframe = pd.DataFrame()
        warning = None
        if path.exists() and path.stat().st_size > 0:
            try:
                dataframe = pd.read_csv(path, low_memory=False)
            except Exception as exc:  # pragma: no cover - shown in dashboard
                warning = f"Could not read curated {filename}: {exc}"
        if warning:
            warnings.append(warning)
        raw[dataset] = dataframe
        status_rows.append(_status_row(dataset, path if path.exists() else None, len(dataframe) if path.exists() else None, len(dataframe.columns) if path.exists() else None))

    recommended = normalise_recommended(raw.get("finalist_accuracy", pd.DataFrame()))
    if not recommended.empty:
        recommended["is_finalist"] = True
        recommended["is_recommended_finalist"] = True
        recommended["stage"] = "final"
        recommended["variant"] = recommended.get("feature_set", "curated")
        for column in ["source_family", "model_kind", "feature_set", "variant"]:
            if column in recommended.columns:
                recommended[column] = recommended[column].map(humanize_label)

    summary = normalise_summary(raw.get("candidate_landscape", pd.DataFrame()), recommended)
    if not summary.empty:
        if "is_recommended_finalist" in summary.columns:
            summary["is_finalist"] = summary["is_recommended_finalist"].astype(bool)
        if "is_pure_schiff" in summary.columns:
            summary["is_schiff"] = summary["is_pure_schiff"].astype(bool)
        summary["stage"] = "final"
        summary["variant"] = summary.get("feature_set", "curated")

    quarterly = normalise_predictions(raw.get("quarterly_predictions_selected", pd.DataFrame()), annual=False)
    annual = normalise_predictions(raw.get("annual_predictions_selected", pd.DataFrame()), annual=True)
    stress = normalise_stress(raw.get("stress_horizon", pd.DataFrame()))
    weights = normalise_weights(raw.get("ensemble_composition", pd.DataFrame()))

    paired = normalise_paired(raw.get("paired_vs_schiff_selected", pd.DataFrame()))

    data = {
        "recommended": recommended,
        "summary": summary,
        "quarterly_predictions": quarterly,
        "annual_predictions": annual,
        "quarterly_summary": pd.DataFrame(),
        "annual_summary": pd.DataFrame(),
        "paired_vs_schiff": paired,
        "stress": stress,
        "weights": weights,
        "features": pd.DataFrame(),
        "variant_features": pd.DataFrame(),
        "leaderboards": pd.DataFrame(),
        "errors": pd.DataFrame(),
        "schiff_benchmark": add_stream_fields(raw.get("schiff_benchmark", pd.DataFrame())),
        "pdf_comparison": add_stream_fields(raw.get("pdf_comparison", pd.DataFrame())),
        "curated_manifest": pd.DataFrame([_load_manifest_row(curated_path)]),
    }
    status = pd.DataFrame(status_rows)
    return LoadedRun(run_path, data, status, tuple(warnings))


def _load_manifest_row(curated_dir: Path) -> dict[str, Any]:
    manifest_path = curated_dir / "curation_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    row = dict(manifest)
    row["curated_dir"] = str(curated_dir)
    return row


def load_run(run_dir: str | Path) -> LoadedRun:
    path = Path(run_dir).expanduser()
    warnings: list[str] = []
    if not path.exists() or not path.is_dir():
        warnings.append(f"Run folder does not exist or is not a directory: {path}")
        return LoadedRun(path, {}, _empty_status_frame(), tuple(warnings))

    raw_data: dict[str, pd.DataFrame] = {}
    status_rows: list[dict[str, Any]] = []
    workbook_cache: dict[Path, pd.ExcelFile] = {}

    files_by_name = {child.name.lower(): child for child in path.iterdir() if child.is_file()}
    for dataset, aliases in FILE_ALIASES.items():
        if dataset not in WORKBOOK_DATASETS:
            found = _find_file(files_by_name, aliases)
            status_rows.append(_status_row(dataset, found, None, None))
            continue

        dataframe, found, warning = _read_tabular_dataset(path, files_by_name, dataset, aliases, workbook_cache)
        if warning:
            warnings.append(warning)
        raw_data[dataset] = dataframe
        status_rows.append(_status_row(dataset, found, len(dataframe) if found else None, len(dataframe.columns) if found else None))

    recommended = normalise_recommended(raw_data.get("recommended", pd.DataFrame()))
    if not recommended.empty:
        recommended["is_finalist"] = True
    summary = normalise_summary(raw_data.get("summary", pd.DataFrame()), recommended)
    if summary.empty and not recommended.empty:
        summary = recommended.copy()
    quarterly = normalise_predictions(raw_data.get("quarterly_predictions", pd.DataFrame()), annual=False)
    annual = normalise_predictions(raw_data.get("annual_predictions", pd.DataFrame()), annual=True)
    paired = normalise_paired(raw_data.get("paired_vs_schiff", pd.DataFrame()))
    if paired.empty:
        paired = derive_paired_from_summary(summary)
    data = {
        "recommended": recommended,
        "summary": summary,
        "quarterly_predictions": quarterly,
        "annual_predictions": annual,
        "quarterly_summary": normalise_summary(raw_data.get("quarterly_summary", pd.DataFrame()), recommended),
        "annual_summary": normalise_summary(raw_data.get("annual_summary", pd.DataFrame()), recommended),
        "paired_vs_schiff": paired,
        "stress": normalise_stress(raw_data.get("stress", pd.DataFrame())),
        "weights": normalise_weights(raw_data.get("weights", pd.DataFrame())),
        "features": add_stream_fields(raw_data.get("features", pd.DataFrame()))
        if not raw_data.get("features", pd.DataFrame()).empty
        else pd.DataFrame(),
        "variant_features": add_stream_fields(raw_data.get("variant_features", pd.DataFrame()))
        if not raw_data.get("variant_features", pd.DataFrame()).empty
        else pd.DataFrame(),
        "leaderboards": add_stream_fields(raw_data.get("leaderboards", pd.DataFrame()))
        if not raw_data.get("leaderboards", pd.DataFrame()).empty and "stream" in raw_data["leaderboards"].columns
        else raw_data.get("leaderboards", pd.DataFrame()),
        "errors": raw_data.get("errors", pd.DataFrame()),
    }

    for dataset, frame in data.items():
        warnings.extend(percent_unit_warnings(frame, dataset))

    status = pd.DataFrame(status_rows)
    return LoadedRun(path, data, status, tuple(warnings))


def _read_tabular_dataset(
    run_dir: Path,
    files_by_name: dict[str, Path],
    dataset: str,
    aliases: list[str],
    workbook_cache: dict[Path, pd.ExcelFile],
) -> tuple[pd.DataFrame, Path | tuple[Path, str] | None, str | None]:
    found = _find_file(files_by_name, [name for name in aliases if name.lower().endswith(".csv")])
    if found and found.stat().st_size > 0:
        try:
            return pd.read_csv(found, low_memory=False), found, None
        except Exception as exc:  # pragma: no cover - shown in dashboard
            return pd.DataFrame(), found, f"Could not read {found.name}: {exc}"

    workbook_hit = _read_from_workbook(run_dir, files_by_name, dataset, workbook_cache)
    if workbook_hit[0] is not None:
        dataframe, workbook_path, sheet_name, warning = workbook_hit
        return dataframe, (workbook_path, sheet_name), warning
    return pd.DataFrame(), None, None


def _read_from_workbook(
    run_dir: Path,
    files_by_name: dict[str, Path],
    dataset: str,
    workbook_cache: dict[Path, pd.ExcelFile],
) -> tuple[pd.DataFrame | None, Path | None, str | None, str | None]:
    hints = SHEET_HINTS.get(dataset, [])
    if not hints:
        return None, None, None, None
    for workbook_name in WORKBOOK_ALIASES:
        workbook_path = _find_file(files_by_name, [workbook_name])
        if workbook_path is None or workbook_path.stat().st_size == 0:
            continue
        try:
            excel = workbook_cache.get(workbook_path)
            if excel is None:
                excel = pd.ExcelFile(workbook_path)
                workbook_cache[workbook_path] = excel
            sheet_name = _match_sheet(excel.sheet_names, hints)
            if not sheet_name:
                continue
            return excel.parse(sheet_name), workbook_path, sheet_name, None
        except Exception as exc:  # pragma: no cover - shown in dashboard
            return pd.DataFrame(), workbook_path, None, f"Could not read {workbook_path.name}: {exc}"
    return None, None, None, None


def _match_sheet(sheet_names: list[str], hints: list[str]) -> str | None:
    normalised = {_normalise_token(sheet): sheet for sheet in sheet_names}
    for hint in hints:
        token = _normalise_token(hint)
        if token in normalised:
            return normalised[token]
    for hint in hints:
        token = _normalise_token(hint)
        for sheet_token, sheet_name in normalised.items():
            if token in sheet_token:
                return sheet_name
    return None


def _normalise_token(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in str(value)).strip("_")


def _find_file(files_by_name: dict[str, Path], aliases: list[str]) -> Path | None:
    for alias in aliases:
        hit = files_by_name.get(alias.lower())
        if hit is not None:
            return hit
    return None


def _status_row(dataset: str, found: Path | tuple[Path, str] | None, rows: int | None, columns: int | None) -> dict[str, Any]:
    if isinstance(found, tuple):
        path, sheet = found
        file_label = f"{path.name} [{sheet}]"
        stat_path = path
    else:
        file_label = found.name if found is not None else ", ".join(FILE_ALIASES.get(dataset, []))
        stat_path = found
    if stat_path is not None:
        stat = stat_path.stat()
        size = _format_size(stat.st_size)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    else:
        size = "-"
        modified = "-"
    return {
        "Dataset": dataset.replace("_", " ").title(),
        "File": file_label,
        "Found?": "Yes" if found is not None else "No",
        "Rows": f"{rows:,}" if rows is not None else "-",
        "Columns": f"{columns:,}" if columns is not None else "-",
        "Size": size,
        "Last modified": modified,
    }


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _empty_status_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["Dataset", "File", "Found?", "Rows", "Columns", "Size", "Last modified"])
