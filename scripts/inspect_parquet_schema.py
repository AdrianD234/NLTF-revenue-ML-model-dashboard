from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PYARROW24 = ROOT / ".runtime_pyarrow24"
if RUNTIME_PYARROW24.exists() and str(RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(RUNTIME_PYARROW24))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.evidence_pack import (  # noqa: E402
    REQUIRED_EVIDENCE_TABLES,
    load_evidence_pack,
    resolve_evidence_pack_root,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the Stage 1 dashboard evidence-pack schema.")
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def write_outputs(report: str, payload: dict[str, Any]) -> None:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "data_schema_report.md").write_text(report, encoding="utf-8")
    (artifacts / "data_schema.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "None."
    columns = [str(column) for column in df.columns]
    rows = df.fillna("").astype(str).values.tolist()
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "/") for value in row) + " |")
    return "\n".join(lines)


def table_payload(data_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in REQUIRED_EVIDENCE_TABLES:
        path = data_dir / filename
        if not path.exists():
            rows.append(
                {
                    "file": filename,
                    "path": str(path),
                    "status": "missing",
                    "rows": None,
                    "columns": None,
                    "column_names": [],
                    "size": None,
                }
            )
            continue
        frame = pd.read_parquet(path)
        rows.append(
            {
                "file": filename,
                "path": str(path),
                "status": "present",
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "column_names": list(frame.columns),
                "size": int(path.stat().st_size),
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    pack_root = resolve_evidence_pack_root(args.data_root)
    manifest_path = pack_root / "manifest.json"
    data_dir = pack_root / "data"
    candidate_path = data_dir / "candidate_cone.parquet"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        payload = {
            "status": "failed",
            "source_mode": "dashboard_evidence_pack",
            "requested_data_root": str(args.data_root),
            "resolved_root": str(pack_root),
            "manifest_path": str(manifest_path),
            "data_dir": str(data_dir),
            "parquet_path": str(candidate_path) if candidate_path.exists() else None,
            "metadata_path": str(manifest_path) if manifest_path.exists() else None,
            "csv_mirror_path": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
        report = "\n".join(
            [
                "# Data Schema Report",
                "",
                "Status: **failed**.",
                f"Requested root: `{args.data_root}`",
                f"Resolved root: `{pack_root}`",
                f"Manifest path: `{manifest_path}`",
                f"Error: {payload['error']}",
            ]
        )
        write_outputs(report, payload)
        print(report)
        return 1

    try:
        loaded = load_evidence_pack(pack_root, args.repo_root)
        tables = table_payload(data_dir)
        missing = [row["file"] for row in tables if row["status"] != "present"]
        candidate = loaded.data.get("candidate_df", pd.DataFrame())
        finalists = loaded.data.get("recommended", pd.DataFrame())
        schiff = loaded.data.get("schiff_benchmark", pd.DataFrame())
    except Exception as exc:
        tables = table_payload(data_dir) if data_dir.exists() else []
        missing = [row["file"] for row in tables if row["status"] != "present"]
        payload = {
            "status": "failed",
            "source_mode": "dashboard_evidence_pack",
            "requested_data_root": str(args.data_root),
            "resolved_root": str(pack_root),
            "manifest_path": str(manifest_path),
            "data_dir": str(data_dir),
            "parquet_path": str(candidate_path) if candidate_path.exists() else None,
            "metadata_path": str(manifest_path),
            "csv_mirror_path": None,
            "required_files": list(REQUIRED_EVIDENCE_TABLES),
            "missing_required_files": missing,
            "tables": tables,
            "error": f"{type(exc).__name__}: {exc}",
        }
        report = "\n".join(
            [
                "# Data Schema Report",
                "",
                "Status: **failed**.",
                f"Resolved evidence pack: `{pack_root}`",
                f"Manifest path: `{manifest_path}`",
                f"Candidate path: `{candidate_path if candidate_path.exists() else 'not found'}`",
                f"Error: {payload['error']}",
                "",
                "## Required Tables",
                *[f"- {row['file']}: {row['status']}" for row in tables],
            ]
        )
        write_outputs(report, payload)
        print(report)
        return 1

    table_frame = pd.DataFrame(
        [
            {
                "file": row["file"],
                "rows": row["rows"],
                "columns": row["columns"],
                "size": row["size"],
            }
            for row in tables
        ]
    )
    stream_counts = (
        candidate.groupby("stream_label", dropna=False).size().to_dict() if "stream_label" in candidate.columns else {}
    )
    flag_counts = {
        column: int(candidate[column].fillna(False).astype(bool).sum())
        for column in [
            "plot_default_include",
            "is_plot_candidate",
            "is_current_recommended",
            "is_pure_schiff",
            "is_pdf_reference",
            "is_frontier",
            "is_distribution_sample",
        ]
        if column in candidate.columns
    }
    current = finalists[[c for c in ["stream", "stream_label", "model", "quarterly_mape", "annual_mape"] if c in finalists.columns]]
    pure_schiff = schiff[[c for c in ["stream", "stream_label", "model", "quarterly_mape", "annual_mape"] if c in schiff.columns]]
    payload: dict[str, Any] = {
        "status": "passed",
        "source_mode": "dashboard_evidence_pack",
        "schema_version": manifest.get("schema_version"),
        "requested_data_root": str(args.data_root),
        "resolved_root": str(pack_root),
        "manifest_path": str(manifest_path),
        "data_dir": str(data_dir),
        "parquet_path": str(candidate_path),
        "metadata_path": str(manifest_path),
        "csv_mirror_path": None,
        "required_files": list(REQUIRED_EVIDENCE_TABLES),
        "missing_required_files": missing,
        "tables": tables,
        "stream_counts": stream_counts,
        "flagged_counts": flag_counts,
        "current_recommended_rows": current.to_dict(orient="records"),
        "pure_schiff_rows": pure_schiff.to_dict(orient="records"),
    }
    report = "\n".join(
        [
            "# Data Schema Report",
            "",
            "Status: **passed**.",
            f"Source mode: `{payload['source_mode']}`",
            f"Schema version: `{payload['schema_version']}`",
            f"Requested root: `{args.data_root}`",
            f"Resolved evidence pack: `{pack_root}`",
            f"Manifest path: `{manifest_path}`",
            f"Candidate path: `{candidate_path}`",
            "",
            "## Required Tables",
            markdown_table(table_frame),
            "",
            "## Row Counts By Stream",
            *[f"- {stream}: {count:,}" for stream, count in stream_counts.items()],
            "",
            "## Flagged Candidate Rows",
            *[f"- {key.replace('_', ' ').title()}: {value:,}" for key, value in flag_counts.items()],
            "",
            "## Current Finalist Rows",
            markdown_table(current),
            "",
            "## Pure Schiff Rows",
            markdown_table(pure_schiff),
        ]
    )
    write_outputs(report, payload)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
