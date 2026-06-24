from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.forecast_runner import run_forecast_workbook, write_forecast_scenario_comparison
from model_dashboard.revenue_outlook import CURRENT_REVENUE_OUTLOOK_DIR, promote_revenue_outlook_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote reviewed Forecast Builder workbooks to the Revenue Outlook pack.")
    parser.add_argument("--basecase", required=True, type=Path, help="Reviewed basecase forecast workbook.")
    parser.add_argument(
        "--comparison",
        action="append",
        required=True,
        type=Path,
        help="Reviewed comparison forecast workbook. Repeat for multiple comparison scenarios.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Dashboard repo root.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Revenue Outlook output directory.")
    parser.add_argument("--scratch-dir", type=Path, default=Path("test-output/tmp/revenue_outlook_promotion"))
    parser.add_argument("--run-timestamp", default="current_revenue_outlook")
    parser.add_argument("--expected-end-period", default="")
    parser.add_argument("--promoted-by", default="codex_reviewed_workbook_promotion")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    scratch_dir = (repo_root / args.scratch_dir).resolve() if not args.scratch_dir.is_absolute() else args.scratch_dir.resolve()
    output_dir = args.output_dir or repo_root / CURRENT_REVENUE_OUTLOOK_DIR
    if not args.basecase.exists():
        raise FileNotFoundError(f"Basecase workbook not found: {args.basecase}")
    for path in args.comparison:
        if not path.exists():
            raise FileNotFoundError(f"Comparison workbook not found: {path}")

    expected_end_period = args.expected_end_period.strip() or None
    results = [
        run_forecast_workbook(
            args.basecase,
            output_dir=scratch_dir / "basecase",
            repo_root=repo_root,
            workbook_filename=args.basecase.name,
            run_timestamp=args.run_timestamp,
            scenario_name="current_basecase",
            scenario_role="basecase",
            is_test_fixture=False,
            expected_end_period=expected_end_period,
        )
    ]
    for index, path in enumerate(args.comparison, start=1):
        results.append(
            run_forecast_workbook(
                path,
                output_dir=scratch_dir / f"comparison_{index}",
                repo_root=repo_root,
                workbook_filename=path.name,
                run_timestamp=args.run_timestamp,
                scenario_name=f"current_comparison_{index}",
                scenario_role="comparison",
                is_test_fixture=False,
                expected_end_period=expected_end_period,
            )
        )

    comparison = write_forecast_scenario_comparison(
        results,
        output_dir=scratch_dir / "scenario_comparison",
        repo_root=repo_root,
        run_timestamp=args.run_timestamp,
    )
    pack = promote_revenue_outlook_pack(
        comparison,
        repo_root=repo_root,
        output_dir=output_dir,
        promoted_by=args.promoted_by,
    )
    print(f"PROMOTED_REVENUE_OUTLOOK {pack.output_dir}")
    print(f"rows.future_revenue_forecasts={len(pack.future_revenue_forecasts)}")
    print(f"rows.revenue_bridge_components={len(pack.revenue_bridge_components)}")
    print(f"rows.revenue_chart_rows={len(pack.revenue_chart_rows)}")


if __name__ == "__main__":
    main()
