"""The published PED calibration R² values are the ENSEMBLE engine's, and every
isolated writer - sequential or parallel - must reproduce them exactly.

Closure of docs/FOLLOW_UP_PED_R2_DRIFT.md Instance 1. A `pytest -n 4
--dist=loadscope` run once moved the committed values

    current_grid_operational_pooled   0.5591936636031876 -> 0.5803595524485978
    schiff_paper_horizon_mean         0.9230110422702978 -> 0.9448430187011027

with every test green. The diagnosis (artifacts/
governed_artifact_reproducibility/r2_parallel_diagnosis.md) proved this was
never numerical nondeterminism: the two value sets are the two ENGINE
identities. The committed values are computed from the ensemble evidence pack
(``data/dashboard_evidence_pack``); the moved values are computed from the
AR(1) pack (``data/engine_ar1/dashboard_evidence_pack``), which app-booting
test modules resolve because ``engine_default()`` is ``ar1``. Before write
isolation, both identities shared one tracked destination and the last writer
decided the published number; xdist merely reordered the writers.

These tests pin all of it:

* the committed CSV carries the ensemble identity, tied to the ensemble
  pack's own stored diagnostics rather than to a copied constant;
* each engine root regenerates its own identity, internally consistent;
* sequential, two-worker and four-worker isolated generation all reproduce
  the committed values, and the tracked chart sources stay byte-identical.
"""
from __future__ import annotations

import csv
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data.chart_sources import write_chart_source_tables
from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT
from model_dashboard.engine import engine_evidence_root
from model_dashboard.evidence_pack import load_evidence_pack

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ROOT / "artifacts" / "chart_sources"
PED_STREAM = "PED VKT per capita"
OPERATIONAL = "current_grid_operational_pooled"
PAPER = "schiff_paper_horizon_mean"

# The authoritative published values. Pinned as strings so a formatting change
# is as loud as a numerical one: these two numbers are governed content.
COMMITTED_PED_CALIBRATION_R2 = {
    OPERATIONAL: "0.5591936636031876",
    PAPER: "0.9230110422702978",
}


def _ped_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("stream_label") == PED_STREAM:
                rows[str(row.get("score_basis"))] = row
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked_hashes() -> dict[str, str]:
    return {
        name: _sha256(TRACKED / name)
        for name in (
            "r2_ladder_summary.csv",
            "r2_reproducibility_gap_register.csv",
            "r2_training_fit_detail.csv",
        )
    }


def _stored_ped_diagnostic(evidence_root: Path) -> dict:
    """The finalist PED diagnostic row the pack itself carries."""
    frame = pd.read_parquet(evidence_root / "data" / "diagnostic_tests.parquet")
    rows = frame[frame["stream_label"].astype(str).eq(PED_STREAM)]
    if "role" in rows.columns:
        rows = rows[rows["role"].astype(str).str.contains("finalist", case=False)]
    assert not rows.empty, f"no finalist PED diagnostic row in {evidence_root}"
    return rows.iloc[0].to_dict()


def test_the_committed_chart_sources_carry_the_ensemble_identity():
    """The tracked CSV equals the ensemble pack's own numbers, exactly.

    Ties the published paper-basis value to the ensemble pack's stored
    diagnostic rather than to a copied constant, so this fails in exactly two
    honest ways: the tracked file was overwritten by another identity (the
    incident), or the ensemble pack itself was re-promoted (in which case the
    chart sources must be re-materialised and re-committed).
    """
    rows = _ped_rows(TRACKED / "r2_ladder_summary.csv")
    assert set(COMMITTED_PED_CALIBRATION_R2) <= set(rows), (
        f"PED rows missing from the tracked ladder summary: {sorted(rows)}"
    )
    for basis, expected in COMMITTED_PED_CALIBRATION_R2.items():
        assert rows[basis]["calibration_r2"] == expected, (
            f"tracked PED calibration_r2[{basis}] is {rows[basis]['calibration_r2']}, "
            f"not the committed {expected} - the governed file has been "
            "overwritten, most plausibly by the AR(1) identity"
        )
    stored = _stored_ped_diagnostic(ROOT / DEFAULT_EVIDENCE_PACK_ROOT)
    assert rows[PAPER]["calibration_r2"] == repr(float(stored["calibration_r2"])), (
        "the tracked paper-basis value does not equal the ensemble pack's own "
        "stored finalist diagnostic; the CSV and the pack have diverged"
    )
    assert rows[PAPER]["model"] == str(stored.get("model", rows[PAPER]["model"])), (
        "the tracked PED row names a different model than the ensemble pack's "
        "finalist diagnostic row"
    )


@pytest.mark.parametrize("engine", ["ensemble", "ar1"])
def test_each_engine_root_regenerates_its_own_identity(engine, tmp_path):
    """One evidence root, one identity - written where it is told to write."""
    evidence_root = engine_evidence_root(engine)
    pack = load_evidence_pack(evidence_root, repo_root=ROOT)
    write_chart_source_tables(ROOT, pack.data, output_dir=tmp_path)
    rows = _ped_rows(tmp_path / "r2_ladder_summary.csv")
    stored = _stored_ped_diagnostic(evidence_root)

    # Internal consistency: the paper-basis value is the pack's own stored
    # finalist diagnostic, whichever engine produced it.
    assert rows[PAPER]["calibration_r2"] == repr(float(stored["calibration_r2"])), (
        f"{engine}: the written paper-basis value is not the pack's stored "
        "diagnostic; the writer mixed identities"
    )
    if engine == "ensemble":
        for basis, expected in COMMITTED_PED_CALIBRATION_R2.items():
            assert rows[basis]["calibration_r2"] == expected, (
                f"ensemble regeneration moved calibration_r2[{basis}]"
            )
    else:
        # The AR(1) identity is real, internally consistent - and DIFFERENT.
        # This difference is what the pre-isolation xdist run published: its
        # last writer had resolved the AR(1) root through engine_default().
        for basis, committed in COMMITTED_PED_CALIBRATION_R2.items():
            assert rows[basis]["calibration_r2"] != committed, (
                f"the AR(1) identity now equals the ensemble value on {basis}; "
                "this test can no longer distinguish the two identities and "
                "must be revisited"
            )


@pytest.mark.parametrize("workers", [0, 2, 4])
def test_isolated_generation_reproduces_the_committed_values(workers, tmp_path):
    """Sequential, two-worker and four-worker generation all agree, exactly.

    Runs the r2 ladder writer module in a nested pytest with the chart-source
    override UNSET, so each worker derives its own scratch destination from
    its worker id and pid (tests/conftest.py). Every destination that received
    a ladder summary must carry the committed ensemble values, and the tracked
    files must remain byte-identical throughout.
    """
    before = _tracked_hashes()
    scratch_root = ROOT / "test-output" / "chart_sources"
    scratch_root.mkdir(parents=True, exist_ok=True)
    pre_existing = {p.name for p in scratch_root.iterdir()}

    env = dict(os.environ)
    # The nested workers must derive their own isolated destinations; an
    # inherited override would collapse them onto one shared directory -
    # which is the incident, not the fixture.
    env.pop("NLTF_CHART_SOURCE_OUTPUT_DIR", None)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/test_r2_ladder.py",
    ]
    if workers:
        command[4:4] = ["-n", str(workers), "--dist", "load"]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    new_dirs = [
        scratch_root / name
        for name in sorted({p.name for p in scratch_root.iterdir()} - pre_existing)
    ]
    try:
        assert completed.returncode == 0, (
            f"nested run failed (workers={workers}):\n{completed.stdout[-3000:]}"
            f"\n{completed.stderr[-2000:]}"
        )
        written = []
        for directory in new_dirs:
            ladder = directory / "r2_ladder_summary.csv"
            if not ladder.exists():
                continue
            written.append(directory.name)
            rows = _ped_rows(ladder)
            for basis, expected in COMMITTED_PED_CALIBRATION_R2.items():
                assert rows[basis]["calibration_r2"] == expected, (
                    f"worker output {directory.name} wrote "
                    f"calibration_r2[{basis}]={rows[basis]['calibration_r2']}, "
                    f"not the committed {expected}"
                )
        minimum = 1 if workers == 0 else 2
        assert len(written) >= minimum, (
            f"only {len(written)} isolated destinations wrote a ladder summary "
            f"({written}); the {workers or 'sequential'}-worker proof is vacuous"
        )
        assert _tracked_hashes() == before, (
            "the nested run mutated the tracked chart sources"
        )
    finally:
        import shutil

        for directory in new_dirs:
            shutil.rmtree(directory, ignore_errors=True)
