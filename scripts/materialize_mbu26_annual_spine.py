from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.mbu26_source_spine import MBU26_SOURCE_PACK_DIR, materialize_mbu26_annual_spine


DEFAULT_WORKBOOK = Path.home() / "Downloads" / "Revenue forecast error, annual view from BEFU 2013-25.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize the repo-local MBU26 annual source spine from the offline MOT workbook."
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--extracted-by", default="codex_mbu26_rebuild")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.repo_root / MBU26_SOURCE_PACK_DIR
    manifest = materialize_mbu26_annual_spine(
        args.workbook,
        repo_root=args.repo_root,
        output_dir=output_dir,
        extracted_by=args.extracted_by,
    )
    workbook = manifest.get("workbook") or {}
    print(f"MBU26_ANNUAL_SPINE_MATERIALIZED {manifest.get('repo_relative_output_dir')}")
    print(f"workbook={workbook.get('basename')}")
    print(f"workbook_sha256={workbook.get('sha256')}")
    print(f"files={len(manifest.get('normalized_files') or {})}")


if __name__ == "__main__":
    main()
