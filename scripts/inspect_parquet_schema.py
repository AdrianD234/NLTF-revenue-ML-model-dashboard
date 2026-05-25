from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data_loader import (  # noqa: E402
    DEFAULT_DIAGNOSTIC_DATA_ROOT,
    PARQUET_CANDIDATE_FILE,
    PARQUET_METADATA_FILE,
    _candidate_search_roots,
    locate_dashboard_file,
    normalise_parquet_candidate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the Stage 1 Parquet dashboard schema.")
    parser.add_argument("--data-root", default=str(DEFAULT_DIAGNOSTIC_DATA_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def bool_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    return int(df[column].fillna(False).astype(bool).sum())


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


def discover_support_files(roots: list[Path]) -> list[dict[str, Any]]:
    patterns = (
        "model_diagnostic_audit_tables.xlsx",
        "model_diagnostic_audit_report.md",
        "*selected*.csv",
        "*prediction*.csv",
        "*diagnostic*.csv",
        "*residual*.csv",
        "*acf*.csv",
        "*schiff*.csv",
        "*.png",
    )
    found: dict[str, Path] = {}
    ignored_parts = {".git", "__pycache__", "test-output", ".pytest_cache", ".uv-cache", ".venv"}
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.rglob(pattern):
                if path.is_file() and not ignored_parts.intersection(path.parts):
                    found[str(path).lower()] = path
    rows = []
    for path in sorted(found.values(), key=lambda item: str(item).lower()):
        stat = path.stat()
        rows.append(
            {
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    roots = _candidate_search_roots(args.data_root, args.repo_root)
    parquet_path = locate_dashboard_file(PARQUET_CANDIDATE_FILE, roots)
    metadata_path = locate_dashboard_file(PARQUET_METADATA_FILE, roots)
    csv_mirror_path = locate_dashboard_file("stage1_curated_candidate_cone.csv", roots)
    support_files = discover_support_files(roots)
    support_lines = (
        [f"- `{row['path']}` ({row['size']:,} bytes)" for row in support_files]
        if support_files
        else ["None."]
    )
    if parquet_path is None:
        report = "\n".join(
            [
                "# Data Schema Report",
                "",
                f"Status: **failed**. `{PARQUET_CANDIDATE_FILE}` was not found.",
                f"Metadata path: `{metadata_path}`" if metadata_path else "Metadata path: not found.",
                f"CSV mirror path: `{csv_mirror_path}`" if csv_mirror_path else "CSV mirror path: not found.",
                "",
                "Searched roots:",
                *[f"- `{root}`" for root in roots],
                "",
                "## Diagnostic And Support Files Found",
                *support_lines,
            ]
        )
        write_outputs(
            report,
            {
                "status": "failed",
                "parquet_path": None,
                "metadata_path": str(metadata_path) if metadata_path else None,
                "csv_mirror_path": str(csv_mirror_path) if csv_mirror_path else None,
                "support_files": support_files,
                "searched_roots": [str(root) for root in roots],
            },
        )
        print(report)
        return 1

    raw = pd.read_parquet(parquet_path)
    df = normalise_parquet_candidate(raw)
    stream_counts = df.groupby("stream_label", dropna=False).size().to_dict() if "stream_label" in df.columns else {}
    flagged = {
        "current_recommended": bool_count(df, "is_current_recommended"),
        "pure_schiff": bool_count(df, "is_pure_schiff"),
        "pdf_reference": bool_count(df, "is_pdf_reference"),
        "frontier": bool_count(df, "is_frontier"),
        "distribution_sample": bool_count(df, "is_distribution_sample"),
        "plot_default_include": bool_count(df, "plot_default_include"),
    }
    current = df.loc[df["is_current_recommended"], ["stream", "stream_label", "model", "quarterly_mape", "annual_mape"]]
    schiff = df.loc[df["is_pure_schiff"], ["stream", "stream_label", "model", "quarterly_mape", "annual_mape"]]

    payload: dict[str, Any] = {
        "status": "passed",
        "parquet_path": str(parquet_path),
        "metadata_path": str(metadata_path) if metadata_path else None,
        "csv_mirror_path": str(csv_mirror_path) if csv_mirror_path else None,
        "support_files": support_files,
        "shape": list(raw.shape),
        "columns": list(raw.columns),
        "normalised_columns": list(df.columns),
        "stream_counts": stream_counts,
        "flagged_counts": flagged,
        "current_recommended_rows": current.to_dict(orient="records"),
        "pure_schiff_rows": schiff.to_dict(orient="records"),
    }
    report = "\n".join(
        [
            "# Data Schema Report",
            "",
            f"Status: **passed**. Resolved Parquet path: `{parquet_path}`.",
            f"Metadata path: `{metadata_path}`" if metadata_path else "Metadata path: not found.",
            f"CSV mirror path: `{csv_mirror_path}`" if csv_mirror_path else "CSV mirror path: not found.",
            f"Rows: {len(df):,}",
            f"Columns: {len(raw.columns):,}",
            "",
            "## Columns",
            *[f"- `{column}`" for column in raw.columns],
            "",
            "## Row Counts By Stream",
            *[f"- {stream}: {count:,}" for stream, count in stream_counts.items()],
            "",
            "## Flagged Rows",
            *[f"- {key.replace('_', ' ').title()}: {value:,}" for key, value in flagged.items()],
            "",
            "## Current Recommended Rows",
            markdown_table(current),
            "",
            "## Pure Schiff Rows",
            markdown_table(schiff),
            "",
            "## Diagnostic And Support Files Found",
            *support_lines,
        ]
    )
    write_outputs(report, payload)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
