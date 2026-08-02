"""Materialise the Revenue Outlook quarterly-display pack.

The dashboard derives quarterly rows for annual-only series with a Denton
benchmarking solve on every Streamlit rerun. Nothing about that solve depends
on what the reader selected, so it is computed once here and committed; the
runtime then serves a filter over an indexed frame instead.

The same build materialises the official annual rows that
``DISPLAY_SERIES_ORDER`` drops - today that is ``light_petrol_vkt``, whose
BEFU26 and MBU26 lines exist in the source packs but never reach a chart row.

    .venv\\Scripts\\python.exe scripts\\build_revenue_outlook_quarterly_display_pack.py

Deterministic: build it twice and the files are byte-identical.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.revenue_outlook_series_coverage import (  # noqa: E402
    build_quarterly_display_pack,
)

# The owner-facing copies of the two governance tables. The pack carries them
# for the runtime; these are the reviewable ones.
ARTIFACTS = ROOT / "artifacts" / "revenue_outlook_series_coverage"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = build_quarterly_display_pack(
        repo_root=args.repo_root, output_dir=args.output_dir
    )
    if args.output_dir is None:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        pack.series_contract.to_csv(
            ARTIFACTS / "quarterly_series_contract.csv", index=False, lineterminator="\n"
        )
        pack.coverage_status.to_csv(
            ARTIFACTS / "quarterly_coverage_table.csv", index=False, lineterminator="\n"
        )

    manifest = pack.manifest
    print(f"schema           {manifest['schema_version']}")
    print(f"contract         {manifest['contract_version']}")
    print(f"source digest    {manifest['source_digest'][:16]}...")
    print(f"quarterly rows   {manifest['quarterly_rows']}")
    print(f"official rows    {manifest['official_annual_rows']}")
    print(f"restored series  {', '.join(manifest['official_series_restored']) or '(none)'}")
    print(f"traces           {', '.join(manifest['quarterly_traces'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
