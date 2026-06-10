from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forecast_runner import (
    DEFAULT_FORECAST_HORIZON_QUARTERS,
    build_forecast_input_template,
    forecast_template_filename,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a governed variable-horizon NLTF forecast input template.")
    parser.add_argument("--quarters", type=int, default=None, help="Forecast quarters to generate. Defaults to 20 when --end-period is omitted.")
    parser.add_argument("--end-period", default=None, help="Final forecast quarter to generate, for example 2050Q4.")
    parser.add_argument("--output", type=Path, default=None, help="Workbook path to write.")
    args = parser.parse_args()
    if args.quarters is not None and args.end_period:
        parser.error("Use either --quarters or --end-period, not both.")
    if args.quarters is not None and args.quarters < 1:
        parser.error("--quarters must be at least 1.")
    quarters = args.quarters if args.quarters is not None else DEFAULT_FORECAST_HORIZON_QUARTERS
    output_path = args.output or ROOT / "templates" / forecast_template_filename(
        quarters=None if args.end_period else quarters,
        end_period=args.end_period,
    )
    output = build_forecast_input_template(
        output_path,
        repo_root=ROOT,
        quarters=None if args.end_period else quarters,
        end_period=args.end_period,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
