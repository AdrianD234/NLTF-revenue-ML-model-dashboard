from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.revenue_outlook import build_current_revenue_outlook_runtime_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the committed Revenue Outlook runtime pack from repo-local governed sources."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--promoted-by", default="repo_source_runtime_rebuild")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pack = build_current_revenue_outlook_runtime_pack(
        repo_root=args.repo_root,
        output_dir=args.output_dir,
        promoted_by=args.promoted_by,
    )
    print(f"REVENUE_OUTLOOK_RUNTIME_REBUILT {pack.output_dir}")
    print(f"chart_rows={len(pack.revenue_chart_rows)}")
    print(f"bridge_rows={len(pack.revenue_bridge_components)}")
    print(f"future_revenue_rows={len(pack.future_revenue_forecasts)}")


if __name__ == "__main__":
    main()
