from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forecast_runner import TEMPLATE_FILENAME, build_forecast_input_template

DEFAULT_OUTPUT = ROOT / "templates" / TEMPLATE_FILENAME


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the governed NLTF 12-quarter forecast input template.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Workbook path to write.")
    args = parser.parse_args()
    output = build_forecast_input_template(args.output, repo_root=ROOT)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
