"""Mint the ped_ar1 reproducibility pack (fitted state, parity audit, manifest).

Usage: python scripts/build_ar1_engine_state.py
Deterministic: refit from data/model_input_history/ped_inputs.parquet.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.ar1_engine import capability_record, write_repro_pack  # noqa: E402


def main() -> int:
    sdir = write_repro_pack(REPO_ROOT)
    print(f"ped_ar1 pack written: {sdir}")
    record = capability_record(REPO_ROOT)
    print(f"capability: {record['capability_status']} (gate delta {record['stored_replay_max_delta']})")
    return 0 if record["forecast_capability_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
