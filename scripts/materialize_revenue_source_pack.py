"""Materialize the normalized NLTF revenue source pack from the distilled workbook.

The raw revenue workbook is lineage only and is never copied into the repo. This
script verifies its SHA256, then exports the compact normalized contract sheets
from the distilled workbook into data/revenue_model_source_pack/2026_05_19.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


EXPECTED_RAW_SHA256 = "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"
SOURCE_PACK_VERSION = "2026_05_19"
DEFAULT_OUTPUT_DIR = Path("data") / "revenue_model_source_pack" / SOURCE_PACK_VERSION

SHEET_EXPORTS = {
    "Series Master": ("series_master.csv", "Series ID"),
    "Aggregation Rules": ("aggregation_rules.csv", "Rule ID"),
    "Current Selections": ("current_selections.csv", "Control ID"),
    "Model Coefficients": ("model_coefficients.csv", "Forecast cell"),
    "Annual Actuals": ("annual_actuals.csv", "Group"),
    "Annual Model Paths": ("annual_model_paths.csv", "Model basis"),
    "Release Registry": ("release_registry.csv", "Source sheet"),
    "Open Decisions": ("unresolved_decisions.csv", "Priority"),
    "Formula Errors": ("formula_errors.csv", "Sheet"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    return value


def _slug(value: str) -> str:
    chars = []
    for char in value.strip().lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "_":
            chars.append("_")
    return "".join(chars).strip("_")


def _sheet_rows(workbook: Any, sheet_name: str) -> list[list[Any]]:
    sheet = workbook[sheet_name]
    return [[_cell_value(value) for value in row] for row in sheet.iter_rows(values_only=True)]


def _find_header_index(rows: list[list[Any]], first_header: str) -> int:
    for index, row in enumerate(rows):
        if row and str(row[0]).strip() == first_header:
            return index
    raise ValueError(f"Could not find header {first_header!r}")


def _trim(row: list[Any], width: int) -> list[Any]:
    row = row[:width]
    if len(row) < width:
        row = row + [""] * (width - len(row))
    return row


def export_table(workbook: Any, sheet_name: str, output_path: Path, first_header: str) -> int:
    rows = _sheet_rows(workbook, sheet_name)
    header_index = _find_header_index(rows, first_header)
    header = [str(value).strip() for value in rows[header_index]]
    while header and not header[-1]:
        header.pop()
    width = len(header)
    data_rows = []
    for row in rows[header_index + 1 :]:
        trimmed = _trim(row, width)
        if not any(str(value).strip() for value in trimmed):
            continue
        data_rows.append(trimmed)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(data_rows)
    return len(data_rows)


def export_markdown(workbook: Any, sheet_name: str, output_path: Path, title: str) -> None:
    rows = _sheet_rows(workbook, sheet_name)
    lines = [f"# {title}", ""]
    for row in rows:
        values = [str(value).strip() for value in row if str(value).strip()]
        if not values:
            lines.append("")
        elif len(values) == 1:
            lines.append(f"## {values[0]}")
        else:
            lines.append(f"- **{values[0]}:** {' | '.join(values[1:])}")
    while lines and lines[-1] == "":
        lines.pop()
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dashboard_controls(workbook: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _sheet_rows(workbook, "Dashboard Controls")
    header_index = _find_header_index(rows, "Control ID")
    header = [str(value).strip() for value in rows[header_index]]
    controls: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        record = dict(zip(header, _trim(row, len(header)), strict=False))
        if not str(record.get("Control ID", "")).strip():
            continue
        options_raw = record.get("Options", "")
        try:
            options = json.loads(options_raw) if isinstance(options_raw, str) and options_raw.strip().startswith("[") else []
        except json.JSONDecodeError:
            options = []
        controls.append(
            {
                "control_id": record.get("Control ID", ""),
                "legacy_cell": record.get("Legacy cell", ""),
                "source_list": record.get("Source list", ""),
                "option_count": record.get("Option count", ""),
                "options": options,
            }
        )

    selection_rows = _sheet_rows(workbook, "Current Selections")
    selection_header_index = _find_header_index(selection_rows, "Control ID")
    selection_header = [str(value).strip() for value in selection_rows[selection_header_index]]
    selections: dict[str, Any] = {}
    for row in selection_rows[selection_header_index + 1 :]:
        record = dict(zip(selection_header, _trim(row, len(selection_header)), strict=False))
        control_id = str(record.get("Control ID", "")).strip()
        if control_id:
            selections[control_id] = {
                "workbook_cell": record.get("Workbook cell", ""),
                "current_value": record.get("Current value", ""),
            }
    return controls, selections


def write_front_end_config(workbook: Any, output_path: Path) -> None:
    controls, current_selections = dashboard_controls(workbook)
    payload = {
        "source": "Dashboard Controls and Current Selections sheets",
        "controls": controls,
        "current_selections": current_selections,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def materialize(raw_workbook: Path, distilled_workbook: Path, output_dir: Path) -> dict[str, Any]:
    raw_hash = sha256(raw_workbook)
    if raw_hash.lower() != EXPECTED_RAW_SHA256:
        raise ValueError(f"Raw workbook SHA256 mismatch: expected {EXPECTED_RAW_SHA256}, got {raw_hash}")
    distilled_hash = sha256(distilled_workbook)
    output_dir.mkdir(parents=True, exist_ok=True)

    workbook = load_workbook(distilled_workbook, read_only=True, data_only=True)
    try:
        row_counts: dict[str, int] = {}
        for sheet_name, (filename, first_header) in SHEET_EXPORTS.items():
            row_counts[filename] = export_table(workbook, sheet_name, output_dir / filename, first_header)
        export_markdown(workbook, "Read Me", output_dir / "README.md", "NLTF Revenue Model Distilled Source Pack")
        export_markdown(workbook, "Overview", output_dir / "MODEL_WORKFLOW.md", "NLTF Revenue Model Workflow")
        write_front_end_config(workbook, output_dir / "front_end_config.json")
        manifest = {
            "schema_version": "nltf-revenue-source-pack-v1",
            "source_pack_version": SOURCE_PACK_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo_relative_output_dir": output_dir.as_posix(),
            "raw_workbook": {
                "basename": raw_workbook.name,
                "sha256": raw_hash.lower(),
                "status": "verified_lineage_only_not_committed",
            },
            "distilled_workbook": {
                "basename": distilled_workbook.name,
                "sha256": distilled_hash.lower(),
                "status": "normalized_contract_source",
            },
            "source_policy": "runtime uses repo-local normalized files only; raw workbook is lineage-only and never loaded by Streamlit",
            "normalized_files": {
                filename: {
                    "sha256": sha256(output_dir / filename),
                    "row_count": row_counts[filename],
                    "source_sheet": sheet_name,
                }
                for sheet_name, (filename, _first_header) in SHEET_EXPORTS.items()
            },
            "config_files": {
                "README.md": {"sha256": sha256(output_dir / "README.md")},
                "MODEL_WORKFLOW.md": {"sha256": sha256(output_dir / "MODEL_WORKFLOW.md")},
                "front_end_config.json": {"sha256": sha256(output_dir / "front_end_config.json")},
            },
            "workbook_sheets": workbook.sheetnames,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return manifest
    finally:
        workbook.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-workbook", type=Path, required=True)
    parser.add_argument("--distilled-workbook", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = materialize(args.raw_workbook, args.distilled_workbook, args.output_dir)
    print(json.dumps({"output_dir": manifest["repo_relative_output_dir"], "source_pack_version": manifest["source_pack_version"]}, sort_keys=True))


if __name__ == "__main__":
    main()
