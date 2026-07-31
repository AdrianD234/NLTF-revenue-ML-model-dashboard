"""Materialize a registered official revenue-forecast vintage pack.

Generic replacement for the MBU26-only materializer: any BEFU/PREFU/MBU
workbook with the governed schema needs only a registry entry (or the
``--sheet``/``--display-name`` flags to create one) and this command.

Example:

    python scripts/materialize_official_vintage.py \
      --workbook "references/BEFU26 revenue forecast.xlsx" \
      --vintage-id BEFU26 \
      --display-name "BEFU26 official" \
      --sheet "Baseline" \
      --set-latest \
      --set-default-comparator \
      --set-default-bridge-vintage
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.official_vintage import (  # noqa: E402
    OfficialVintageError,
    materialize_official_vintage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage-id", required=True, help="Registry vintage id, e.g. BEFU26")
    parser.add_argument("--workbook", type=Path, default=None, help="Source workbook path (defaults to the registered source_workbook)")
    parser.add_argument("--display-name", default=None, help="Display name when creating a new registry entry")
    parser.add_argument("--sheet", default=None, help="Worksheet name (required when creating a new registry entry)")
    parser.add_argument("--release-round", default=None, help="Release round label when creating a new registry entry (defaults to the vintage id)")
    parser.add_argument("--source-pack-path", default=None, help="Pack output path when creating a new registry entry")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--extracted-by", default="official_vintage_materializer")
    parser.add_argument("--set-latest", action="store_true")
    parser.add_argument("--set-default-comparator", action="store_true")
    parser.add_argument("--set-default-bridge-vintage", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = materialize_official_vintage(
            args.vintage_id,
            workbook_path=args.workbook,
            repo_root=args.repo_root,
            output_dir=args.output_dir,
            extracted_by=args.extracted_by,
            display_name=args.display_name,
            sheet=args.sheet,
            release_round=args.release_round,
            source_pack_path=args.source_pack_path,
            set_latest=args.set_latest,
            set_default_comparator=args.set_default_comparator,
            set_default_bridge_vintage=args.set_default_bridge_vintage,
        )
    except OfficialVintageError as error:
        print(f"OFFICIAL_VINTAGE_MATERIALIZATION_FAILED {args.vintage_id}", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    print(f"OFFICIAL_VINTAGE_MATERIALIZED {manifest['repo_relative_output_dir']}")
    print(f"vintage_id={manifest['vintage_id']}")
    print(f"workbook={manifest['workbook']['basename']}")
    print(f"workbook_sha256={manifest['workbook']['sha256']}")
    print(f"sentinels_validated={manifest['sentinels_validated']}")
    print(f"files={len(manifest['normalized_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
