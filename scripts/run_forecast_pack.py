from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forecast_runner import run_forecast_workbook



def main() -> int:
    parser = argparse.ArgumentParser(description="Run a governed 12-quarter NLTF forecast pack from a completed workbook.")
    parser.add_argument("workbook", type=Path, help="Completed forecast input workbook.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Forecast-run output directory.")
    args = parser.parse_args()
    result = run_forecast_workbook(
        args.workbook,
        output_dir=args.output_dir,
        repo_root=ROOT,
        workbook_filename=args.workbook.name,
    )
    print(f"Forecast run: {result.output_dir}")
    print(f"Validation: {result.manifest['validation_status']}")
    print(f"Forecast status: {result.manifest['forecast_status']}")
    if result.validation.errors:
        print("Validation errors:")
        for message in result.validation.errors:
            print(f"- {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
