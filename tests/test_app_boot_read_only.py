"""Normal app execution must never publish governed chart-source evidence.

Issue #31. Starting the Streamlit app used to call ``load_evidence_pack``, which
called ``write_chart_source_tables`` unconditionally. The app boots on the AR(1)
default engine while the committed tables carry the ensemble identity, so simply
opening the dashboard rewrote a governed PED calibration R-squared:

    operational pooled   0.5591936636031876 -> 0.5803595524485978
    paper horizon mean   0.9230110422702978 -> 0.9448430187011027

Both pairs are valid engine identities. The defect was that an incidental code
path got to decide which one was published.

The AppTest below is necessary but not sufficient: pytest's conftest redirects
chart-source output, which is exactly why this path went unnoticed. The
authoritative proof is the real host process check in
``scripts/check_app_boot_read_only.py``.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from model_dashboard.data.chart_sources import (
    CANONICAL_CHART_SOURCE_ENGINE,
    CHART_SOURCE_WRITE_PROMOTE,
    CHART_SOURCE_WRITE_READ_ONLY,
    CHART_SOURCE_WRITE_SCRATCH,
    ChartSourceWriteRefused,
    canonical_chart_source_dir,
    engine_diagnostic_chart_source_dir,
    resolve_chart_source_output_dir,
    write_chart_source_tables,
)
from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT
from model_dashboard.evidence_pack import load_evidence_pack

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(ROOT / "app.py")
CHART_SOURCE_ENV = "NLTF_CHART_SOURCE_OUTPUT_DIR"

# The authoritative committed ensemble identity.
ENSEMBLE_OPERATIONAL_POOLED_R2 = "0.5591936636031876"
ENSEMBLE_PAPER_HORIZON_MEAN_R2 = "0.9230110422702978"
# The AR(1) engine identity, which must never occupy the canonical filenames.
AR1_OPERATIONAL_POOLED_R2 = "0.5803595524485978"
AR1_PAPER_HORIZON_MEAN_R2 = "0.9448430187011027"

LADDER = "r2_ladder_summary.csv"


def governed_files() -> list[Path]:
    """Every tracked file under artifacts/chart_sources, not just the ladder."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "artifacts/chart_sources"],
        capture_output=True,
        text=True,
        check=False,
    )
    tracked = [ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [path for path in tracked if path.exists()]


def hash_tree(paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


@pytest.fixture(scope="module")
def governed_snapshot() -> dict[str, str]:
    paths = governed_files()
    assert paths, "Expected tracked files under artifacts/chart_sources."
    return hash_tree(paths)


# --------------------------------------------------------------------------- #
# A. Unit-level write contract
# --------------------------------------------------------------------------- #


def test_read_only_loading_produces_evidence_without_writing(tmp_path: Path) -> None:
    """The default load computes the evidence and publishes nothing."""
    before = hash_tree(governed_files())
    empty_root = tmp_path / "repo"
    (empty_root / "artifacts").mkdir(parents=True)

    pack = load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, empty_root)

    assert not pack.data["recommended"].empty, "Read-only loading must still return the evidence."
    assert not (empty_root / "artifacts" / "chart_sources").exists(), (
        "Loading an evidence pack created a chart-source directory. Loading must be read-only; "
        "use scripts/promote_chart_sources.py to publish."
    )
    assert hash_tree(governed_files()) == before


def test_scratch_mode_writes_only_under_the_supplied_directory(tmp_path: Path) -> None:
    before = hash_tree(governed_files())
    scratch = tmp_path / "scratch"

    load_evidence_pack(
        DEFAULT_EVIDENCE_PACK_ROOT,
        ROOT,
        materialize_chart_sources=True,
        chart_source_output_dir=scratch,
    )

    assert (scratch / LADDER).exists(), "Scratch materialisation did not write the ladder."
    assert hash_tree(governed_files()) == before, "Scratch materialisation touched governed evidence."


def test_canonical_writes_are_refused_without_promotion_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard fires before any table is built, so no data argument is needed."""
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    before = hash_tree(governed_files())

    for mode in (CHART_SOURCE_WRITE_SCRATCH, CHART_SOURCE_WRITE_READ_ONLY):
        with pytest.raises(ChartSourceWriteRefused):
            write_chart_source_tables(ROOT, {}, mode=mode)

    with pytest.raises(ChartSourceWriteRefused):
        write_chart_source_tables(ROOT, {}, canonical_chart_source_dir(ROOT), mode=CHART_SOURCE_WRITE_SCRATCH)

    assert hash_tree(governed_files()) == before


def test_loading_can_never_reach_the_canonical_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Materialisation via the loader is SCRATCH-only, by construction."""
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    before = hash_tree(governed_files())

    with pytest.raises(ChartSourceWriteRefused):
        load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, ROOT, materialize_chart_sources=True)

    assert hash_tree(governed_files()) == before


def test_ar1_cannot_replace_the_ensemble_canonical_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Promotion is engine-aware: AR(1) is refused at the governed filenames.

    tmp_path stands in as the repo root, so 'canonical' here is
    tmp_path/artifacts/chart_sources and the real tree is never at risk.
    """
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    canonical = canonical_chart_source_dir(tmp_path)

    with pytest.raises(ChartSourceWriteRefused) as excinfo:
        write_chart_source_tables(tmp_path, {}, canonical, mode=CHART_SOURCE_WRITE_PROMOTE, engine="ar1")

    message = str(excinfo.value)
    assert "ar1" in message and CANONICAL_CHART_SOURCE_ENGINE in message
    assert not canonical.exists(), "A refused promotion still created the governed directory."


def test_promotion_mode_writes_to_the_governed_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PROMOTE + the governed engine is the one combination that publishes.

    The table build is stubbed: this test is about the write contract, not the
    contents, and it keeps tmp_path standing in for the repo root.
    """
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    frames = {LADDER: pd.DataFrame([{"page": "Diagnostics", "calibration_r2": 0.5}])}
    monkeypatch.setattr(
        "model_dashboard.data.chart_sources.build_chart_source_tables",
        lambda data, repo_root=None: frames,
    )
    canonical = canonical_chart_source_dir(tmp_path)

    write_chart_source_tables(
        tmp_path,
        {},
        canonical,
        mode=CHART_SOURCE_WRITE_PROMOTE,
        engine=CANONICAL_CHART_SOURCE_ENGINE,
    )

    assert (canonical / LADDER).exists()
    # Atomic writes must not leave shared .tmp residue behind.
    assert not list(canonical.glob("*.tmp.*")), "Promotion left temporary files behind."

    # Idempotent: a second promotion reproduces the same bytes.
    first = (canonical / LADDER).read_bytes()
    write_chart_source_tables(
        tmp_path,
        {},
        canonical,
        mode=CHART_SOURCE_WRITE_PROMOTE,
        engine=CANONICAL_CHART_SOURCE_ENGINE,
    )
    assert (canonical / LADDER).read_bytes() == first
    assert not list(canonical.glob("*.tmp.*"))


def test_engine_outputs_cannot_collide(tmp_path: Path) -> None:
    """Two engine identities never share one destination."""
    ar1 = engine_diagnostic_chart_source_dir(tmp_path, "ar1")
    ensemble = engine_diagnostic_chart_source_dir(tmp_path, CANONICAL_CHART_SOURCE_ENGINE)

    assert ar1 != ensemble
    assert ar1 != canonical_chart_source_dir(tmp_path)
    assert ensemble != canonical_chart_source_dir(tmp_path)


def test_unknown_write_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        write_chart_source_tables(ROOT, {}, mode="publish-please")


def test_resolver_precedence_is_explicit_then_env_then_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    assert resolve_chart_source_output_dir(tmp_path) == canonical_chart_source_dir(tmp_path)
    monkeypatch.setenv(CHART_SOURCE_ENV, str(tmp_path / "from-env"))
    assert resolve_chart_source_output_dir(tmp_path) == tmp_path / "from-env"
    assert resolve_chart_source_output_dir(tmp_path, tmp_path / "explicit") == tmp_path / "explicit"


# --------------------------------------------------------------------------- #
# D. Authoritative committed values
# --------------------------------------------------------------------------- #


def test_committed_ladder_carries_the_ensemble_identity() -> None:
    text = (ROOT / "artifacts" / "chart_sources" / LADDER).read_text(encoding="utf-8")

    assert ENSEMBLE_OPERATIONAL_POOLED_R2 in text, (
        f"The committed r2_ladder_summary.csv must carry the ensemble operational pooled "
        f"calibration R2 {ENSEMBLE_OPERATIONAL_POOLED_R2}."
    )
    assert ENSEMBLE_PAPER_HORIZON_MEAN_R2 in text, (
        f"The committed r2_ladder_summary.csv must carry the ensemble paper horizon mean "
        f"calibration R2 {ENSEMBLE_PAPER_HORIZON_MEAN_R2}."
    )
    assert AR1_OPERATIONAL_POOLED_R2 not in text, (
        f"The committed r2_ladder_summary.csv contains the AR(1) operational pooled calibration R2 "
        f"{AR1_OPERATIONAL_POOLED_R2}. That is a valid AR(1) identity but not the governed ensemble "
        f"one; something republished the active engine over the committed evidence (issue #31)."
    )
    assert AR1_PAPER_HORIZON_MEAN_R2 not in text, (
        f"The committed r2_ladder_summary.csv contains the AR(1) paper horizon mean calibration R2 "
        f"{AR1_PAPER_HORIZON_MEAN_R2} instead of the ensemble value {ENSEMBLE_PAPER_HORIZON_MEAN_R2}."
    )


# --------------------------------------------------------------------------- #
# B. AppTest-level boot
# --------------------------------------------------------------------------- #


def test_apptest_boot_leaves_every_governed_file_untouched(
    governed_snapshot: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boot the app with the test redirect deliberately removed.

    conftest points chart-source output at a scratch directory. Leaving that in
    place would make this test pass no matter what the app does, which is how
    the app-boot path stayed hidden. Removing it means that if the startup
    writer is ever reinstated, this test sees it - either as changed bytes or as
    a ChartSourceWriteRefused from the guard.
    """
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    monkeypatch.delenv("DASHBOARD_ENGINE_DEFAULT", raising=False)

    harness = AppTest.from_file(APP_PATH, default_timeout=300)
    harness.run()
    assert not harness.exception, f"App boot raised: {harness.exception}"

    after = hash_tree(governed_files())
    changed = sorted(name for name, digest in after.items() if governed_snapshot.get(name) != digest)
    assert not changed, f"Booting the app modified governed chart-source evidence: {changed}"

    # A normal rerun must not publish either.
    harness.run()
    assert not harness.exception, f"App rerun raised: {harness.exception}"
    after_rerun = hash_tree(governed_files())
    changed = sorted(name for name, digest in after_rerun.items() if governed_snapshot.get(name) != digest)
    assert not changed, f"A Streamlit rerun modified governed chart-source evidence: {changed}"


def test_apptest_boot_under_the_ensemble_engine_also_writes_nothing(
    governed_snapshot: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Engine switching must not publish either, in either direction."""
    monkeypatch.delenv(CHART_SOURCE_ENV, raising=False)
    monkeypatch.setenv("DASHBOARD_ENGINE_DEFAULT", "ensemble")

    harness = AppTest.from_file(APP_PATH, default_timeout=300)
    harness.run()
    assert not harness.exception, f"App boot raised: {harness.exception}"

    after = hash_tree(governed_files())
    changed = sorted(name for name, digest in after.items() if governed_snapshot.get(name) != digest)
    assert not changed, f"Booting under the ensemble engine modified governed evidence: {changed}"


# --------------------------------------------------------------------------- #
# E. The explicit promotion command
# --------------------------------------------------------------------------- #


def test_promotion_command_reproduces_the_ensemble_identity(tmp_path: Path) -> None:
    """Promotion into a scratch destination yields the governed values."""
    before = hash_tree(governed_files())
    destination = tmp_path / "promoted"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "promote_chart_sources.py"),
            "--engine",
            CANONICAL_CHART_SOURCE_ENGINE,
            "--repo-root",
            str(ROOT),
            "--output",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )

    assert result.returncode == 0, f"promote_chart_sources.py failed:\n{result.stdout}\n{result.stderr}"
    text = (destination / LADDER).read_text(encoding="utf-8")
    assert ENSEMBLE_OPERATIONAL_POOLED_R2 in text
    assert ENSEMBLE_PAPER_HORIZON_MEAN_R2 in text
    assert AR1_OPERATIONAL_POOLED_R2 not in text
    assert not list(destination.glob("*.tmp.*"))
    assert hash_tree(governed_files()) == before, "The promotion command touched the governed tree."


def test_promotion_command_refuses_ar1_at_the_governed_destination() -> None:
    """--engine ar1 routes to engine-keyed diagnostics, never the canonical names."""
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "promote_chart_sources.py"),
            "--engine",
            "ar1",
            "--repo-root",
            str(ROOT),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "artifacts" in result.stdout
    assert "diagnostics" in result.stdout.replace("\\", "/"), (
        f"AR(1) promotion should target an engine-keyed diagnostic directory. Got:\n{result.stdout}"
    )
