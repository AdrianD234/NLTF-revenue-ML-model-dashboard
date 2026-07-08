"""CLI for the Diagnostics Lab: one adaptive search round per invocation.

Usage:
    python scripts/run_diagnostics_lab.py --stream PED
    python scripts/run_diagnostics_lab.py --stream LIGHT_RUC --budget 24
    python scripts/run_diagnostics_lab.py --stream PED --steer steer.json
    python scripts/run_diagnostics_lab.py --stream PED --reset

Each round writes artifacts/diagnostics_lab/<stream>/round_N/{candidates.parquet,
report.md}; review the report (and optionally provide a steer JSON with
``arm_quotas`` / ``retire_arms`` / ``extra_specs`` / ``max_configs``) before
running the next round.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.diaglab_orchestrator import LAB_DIR, export_winners, run_round  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream", required=True, choices=["PED", "LIGHT_RUC", "HEAVY_RUC"])
    parser.add_argument("--budget", type=int, default=40)
    parser.add_argument("--steer", type=Path, default=None, help="JSON file with round overrides")
    parser.add_argument("--reset", action="store_true", help="Delete the stream's lab state and start over")
    parser.add_argument("--export", action="store_true", help="Export winner predictions + registry summaries instead of running a round")
    args = parser.parse_args()

    stream_dir = REPO_ROOT / LAB_DIR / args.stream.lower()
    if args.reset and stream_dir.exists():
        shutil.rmtree(stream_dir)
        print(f"reset: removed {stream_dir}")

    if args.export:
        out_dir = export_winners(REPO_ROOT, args.stream)
        print(f"winners exported: {out_dir}")
        for path in sorted(out_dir.glob("*.summary.json")):
            print(f"  {path.name}")
        return 0

    steer = json.loads(args.steer.read_text(encoding="utf-8")) if args.steer else None
    round_dir = run_round(REPO_ROOT, args.stream, budget=args.budget, steer=steer)
    print(f"round complete: {round_dir}")
    print((round_dir / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
