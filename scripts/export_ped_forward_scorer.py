from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PYARROW24 = ROOT / ".runtime_pyarrow24"
if RUNTIME_PYARROW24.exists() and str(RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(RUNTIME_PYARROW24))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forward_scorer_governance import json_record
from model_dashboard.ped_forward import evaluate_ped_forward_scorer


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the PED fixed-finalist forward-scorer audit.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root. Defaults to the current directory.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    record = json_record(evaluate_ped_forward_scorer(args.repo_root))
    text = json.dumps(record, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
