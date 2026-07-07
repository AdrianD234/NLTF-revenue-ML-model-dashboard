"""Pack-driven curated-data regenerator.

Rebuilds ``artifacts/curated_data/`` (git-ignored scratch consumed by the
Stage 1 governance tests and dashboard) from the *vendored* Stage 1 finalist
arbitration run inside the ped_inner_hpo reproducibility pack, so a fresh
clone never needs the original (OneDrive-era) run directory.

Sources (all committed, hash-backed in ``source_artifacts_manifest.json``):

- ``data/dashboard_evidence_pack_reproducibility/ped_inner_hpo/source_artifacts/
  finalist_arbitration_run_20260520_002339/``
  -> final_summary.csv, paired_vs_schiff.csv, stress_tests.csv,
     ensemble_weights.csv, recommended_finalists_primary.csv
- ``pdf_expected_comparison.csv`` is reconstructed exactly as
  ``stage1_finalist_arbitration.py`` wrote it: primary finalist metrics joined
  with the frozen PDF_EXPECTED reference values.

Usage:
    python scripts/regenerate_curated_data_from_pack.py [--out-dir artifacts/curated_data]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_curated_dashboard_data as builder  # noqa: E402

PACK_SOURCE_ARTIFACTS = (
    ROOT
    / "data"
    / "dashboard_evidence_pack_reproducibility"
    / "ped_inner_hpo"
    / "source_artifacts"
)

# Frozen previous-PDF reference values, identical to PDF_EXPECTED in the
# vendored scripts/stage1_finalist_arbitration.py (source_artifacts/scripts).
PDF_EXPECTED = {
    "PED": {"quarterly_mape": 2.48, "annual_mape": 2.42},
    "LIGHT_RUC": {"quarterly_mape": 9.16, "annual_mape": 6.25},
    "HEAVY_RUC": {"quarterly_mape": 3.80, "annual_mape": 3.07},
}

RUN_FILES = [
    "final_summary.csv",
    "paired_vs_schiff.csv",
    "stress_tests.csv",
    "ensemble_weights.csv",
]


def locate_arbitration_run() -> Path:
    runs = sorted(PACK_SOURCE_ARTIFACTS.glob("finalist_arbitration_run_*"))
    if not runs:
        raise FileNotFoundError(
            f"No vendored finalist_arbitration_run_* directory under {PACK_SOURCE_ARTIFACTS}"
        )
    return runs[-1]


def reconstruct_pdf_expected_comparison(run_dir: Path) -> pd.DataFrame:
    primary = pd.read_csv(run_dir / "recommended_finalists_primary.csv")
    rows = []
    for _, r in primary.iterrows():
        stream = r["stream"]
        expected = PDF_EXPECTED.get(stream, {})
        rows.append(
            {
                "stream": stream,
                "selected_model": r["model"],
                "selected_quarterly_mape": r["quarterly_mape"],
                "pdf_quarterly_mape": expected.get("quarterly_mape", np.nan),
                "selected_minus_pdf_q_pp": r["quarterly_mape"] - expected.get("quarterly_mape", np.nan),
                "selected_annual_mape": r["annual_mape"],
                "pdf_annual_mape": expected.get("annual_mape", np.nan),
                "selected_minus_pdf_a_pp": r["annual_mape"] - expected.get("annual_mape", np.nan),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", default=str(ROOT / "artifacts" / "curated_data"))
    parser.add_argument("--max-candidate-rows", type=int, default=400)
    args = parser.parse_args()

    run_dir = locate_arbitration_run()
    with tempfile.TemporaryDirectory(prefix="curated_run_stage_") as staged:
        staged_dir = Path(staged)
        for name in RUN_FILES:
            source = run_dir / name
            if not source.exists():
                raise FileNotFoundError(f"Vendored arbitration run is missing {name}: {source}")
            shutil.copy2(source, staged_dir / name)
        reconstruct_pdf_expected_comparison(run_dir).to_csv(
            staged_dir / "pdf_expected_comparison.csv", index=False
        )
        outputs = builder.build_curated_data(
            staged_dir, Path(args.out_dir), args.max_candidate_rows
        )

    print(f"Regenerated curated data from vendored pack run: {run_dir.name}")
    for name, frame in outputs.items():
        print(f"  {name}: {len(frame)} rows")


if __name__ == "__main__":
    main()
