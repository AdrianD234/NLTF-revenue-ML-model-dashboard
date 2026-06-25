"""Export loader-derived NLTF revenue source-pack tables.

These outputs are reproducible from the repo-local normalized source pack and
are safe to commit. They provide a compact handoff for audits and dashboard
downloads without loading the raw workbook at runtime.
"""

from __future__ import annotations

import argparse
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
    "source_gap_register.csv": "Structured source-pack gaps for release values, FED path scenarios, Crown top-up, quarterly rows, and bridge replay.",
    "remaining_decisions_handoff.csv": "Unresolved revenue decisions linked to runtime gaps and dashboard treatment.",
    "series_role_audit.csv": "Explicit role contract for modeled activity, revenue bridges, pass-through lines, deductions, overlays, and source gaps.",
    "hybrid_annual_revenue.csv": "Replacement-only annual NLTF hybrid roll-up audit using source-backed PED/FED, Light RUC and Heavy RUC bridge inputs plus MOT fixed components.",
    "annual_completeness_audit.csv": "June-year annual actual completeness audit and chart-treatment contract.",
    "series_trace_contract.csv": "Per-series trace contract for valid controls, actual source, primary current forecast source, legacy benchmark source, bridge and cutoffs.",
    "series_junction_audit.csv": "FY2024-FY2027 actual/current/legacy junction audit with quarter coverage, cutoffs, nowcast components and discontinuity flags.",
    "data_vintage_manifest.json": "Model/source observation cutoffs and repo-local current Revenue Outlook/source-pack hashes.",
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
        "hybrid_annual_revenue.csv": pack.hybrid_annual_revenue,
        "annual_completeness_audit.csv": pack.annual_completeness_audit,
        "series_trace_contract.csv": pack.series_trace_contract,
        "series_junction_audit.csv": pack.series_junction_audit,
        "validation_issues.csv": pack.validation_issues,
    }
    manifest: dict[str, object] = {
        "schema_version": "nltf-revenue-source-pack-loader-exports-v1",
        "created_at": pack.manifest.get("created_at", ""),
        "created_at_source": "source_pack_manifest_created_at",
        "determinism_policy": "No wall-clock timestamp is used; identical source-pack inputs produce identical export manifests.",
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
    data_vintage_path = pack_dir / "data_vintage_manifest.json"
    data_vintage_path.write_text(json.dumps(pack.data_vintage_manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    manifest["exports"]["data_vintage_manifest.json"] = {
        "sha256": sha256(data_vintage_path),
        "row_count": None,
        "role": EXPORT_FILES["data_vintage_manifest.json"],
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
