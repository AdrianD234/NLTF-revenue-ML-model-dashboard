from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forecast_runner import run_forecast_workbook, scenario_name_from_filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a governed variable-horizon NLTF forecast pack from a completed workbook.")
    parser.add_argument("workbook", type=Path, help="Completed forecast input workbook.")
    parser.add_argument("--scenario-name", default=None, help="Scenario name to write into outputs.")
    parser.add_argument("--scenario-role", choices=["basecase", "comparison"], default=None, help="Scenario comparison role.")
    parser.add_argument("--is-test-fixture", action="store_true", help="Mark this workbook as an explicitly generated test fixture.")
    parser.add_argument("--quarters", type=int, default=None, help="Expected forecast horizon in quarters.")
    parser.add_argument("--end-period", default=None, help="Expected final forecast quarter, for example 2050Q4.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Forecast-run output directory.")
    args = parser.parse_args()
    if args.quarters is not None and args.end_period:
        parser.error("Use either --quarters or --end-period, not both.")
    if args.quarters is not None and args.quarters < 1:
        parser.error("--quarters must be at least 1.")
    scenario_name = args.scenario_name or scenario_name_from_filename(args.workbook.name)
    result = run_forecast_workbook(
        args.workbook,
        output_dir=args.output_dir,
        repo_root=ROOT,
        workbook_filename=args.workbook.name,
        scenario_name=scenario_name,
        scenario_role=args.scenario_role,
        is_test_fixture=args.is_test_fixture,
        expected_quarters=args.quarters,
        expected_end_period=args.end_period,
    )
    print(f"Forecast run: {result.output_dir}")
    print(f"Scenario: {result.manifest['scenario_name']}")
    print(f"Scenario role: {result.manifest['scenario_role'] or 'ambiguous'}")
    print(f"Horizon: {result.manifest['forecast_horizon_quarters']} quarters")
    print(f"Validation: {result.manifest['validation_status']}")
    print(f"Forecast status: {result.manifest['forecast_status']}")
    if result.validation.errors:
        print("Validation errors:")
        for message in result.validation.errors:
            print(f"- {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
