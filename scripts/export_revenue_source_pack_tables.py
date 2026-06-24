"""Export loader-derived NLTF revenue source-pack tables.

These outputs are reproducible from the repo-local normalized source pack and
are safe to commit. They provide a compact handoff for audits and dashboard
downloads without loading the raw workbook at runtime.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from model_dashboard.revenue_source_pack import REVENUE_SOURCE_PACK_DIR, load_revenue_source_pack


EXPORT_FILES = {
    "canonical_revenue_long.csv": "Canonical long schema across actuals and model paths.",
    "source_pack_intake_status.csv": "Repo-local source-pack intake status, hashes, and replay gaps.",
    "path_trace_status.csv": "Availability and plotting status for required Revenue Outlook total-path traces.",
    "reconciliation_report.csv": "Hierarchy roll-up reconciliation and explicit gap report.",
    "source_gap_register.csv": "Structured source-pack gaps for release values, Crown top-up, quarterly rows, and bridge replay.",
    "remaining_decisions_handoff.csv": "Unresolved revenue decisions linked to runtime gaps and dashboard treatment.",
    "series_role_audit.csv": "Explicit role contract for modeled activity, revenue bridges, pass-through lines, deductions, overlays, and source gaps.",
    "validation_issues.csv": "Loader validation warnings/errors for the source pack.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_tables(pack_dir: Path) -> dict[str, object]:
    pack = load_revenue_source_pack(pack_dir=pack_dir, repo_root=Path.cwd())
    if pack is None:
        raise FileNotFoundError(f"Revenue source pack not found: {pack_dir}")
    outputs = {
        "canonical_revenue_long.csv": pack.canonical_long,
        "source_pack_intake_status.csv": pack.intake_status,
        "path_trace_status.csv": pack.path_trace_status,
        "reconciliation_report.csv": pack.reconciliation_report,
        "source_gap_register.csv": pack.source_gap_register,
        "remaining_decisions_handoff.csv": pack.remaining_decisions_handoff,
        "series_role_audit.csv": pack.series_role_audit,
        "validation_issues.csv": pack.validation_issues,
    }
    manifest: dict[str, object] = {
        "schema_version": "nltf-revenue-source-pack-loader-exports-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_relative_output_dir": pack_dir.as_posix(),
        "source_pack_version": pack.manifest.get("source_pack_version"),
        "source_pack_raw_sha256": pack.manifest.get("raw_workbook", {}).get("sha256"),
        "validation_status": pack.validation_status,
        "exports": {},
    }
    for filename, frame in outputs.items():
        output_path = pack_dir / filename
        frame.to_csv(output_path, index=False)
        manifest["exports"][filename] = {
            "sha256": sha256(output_path),
            "row_count": int(len(frame)),
            "role": EXPORT_FILES[filename],
        }
    loader_manifest = pack_dir / "loader_exports_manifest.json"
    loader_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", type=Path, default=REVENUE_SOURCE_PACK_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = export_tables(args.pack_dir)
    print(json.dumps({"output_dir": manifest["repo_relative_output_dir"], "exports": sorted(manifest["exports"])}, sort_keys=True))


if __name__ == "__main__":
    main()
