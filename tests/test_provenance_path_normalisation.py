"""Stored provenance paths must classify identically on Windows and Linux.

The committed reproducibility packs record absolute source paths from the
machine that produced them, which for this repository means Windows paths with
backslashes. ``Path(r"a\\b.csv").name`` returns the whole string on POSIX,
because a backslash is a legal filename character there - so any role or
lineage decision built on it silently changes meaning between platforms.

This surfaced as a real clean-environment CI failure: every PED inner-HPO
weight classified as "Other source" on Linux while classifying correctly on
Windows.
"""

from __future__ import annotations

import pytest

from model_dashboard.light_ruc_reproducibility import (
    _ped_inner_source_role,
    _ped_source_stage_hint,
    provenance_basename,
)

WINDOWS_HPO = (
    r"C:\Users\Someone\Downloads\stage1_hpo_refinement_core_outputs"
    r"\hpo_refined_ensemble_weights.csv"
)
POSIX_HPO = (
    "/home/runner/stage1_hpo_refinement_core_outputs/hpo_refined_ensemble_weights.csv"
)
WINDOWS_ARBITRATION = (
    r"C:\Users\Someone\OneDrive\stage1_finalist_arbitration_outputs"
    r"\run_20260520_002339\ensemble_weights.csv"
)
POSIX_ARBITRATION = (
    "/home/runner/stage1_finalist_arbitration_outputs/run_20260520_002339/"
    "ensemble_weights.csv"
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (r"a\b\c.csv", "c.csv"),
        ("a/b/c.csv", "c.csv"),
        (r"C:\Users\x\file.csv", "file.csv"),
        ("/home/runner/file.csv", "file.csv"),
        (r"mixed/separators\file.csv", "file.csv"),
        ("file.csv", "file.csv"),
        ("", ""),
        (None, ""),
    ],
)
def test_provenance_basename_is_platform_independent(value, expected):
    assert provenance_basename(value) == expected


def test_source_role_is_the_same_for_both_separators():
    assert _ped_inner_source_role(WINDOWS_HPO) == "HPO refinement source"
    assert _ped_inner_source_role(POSIX_HPO) == "HPO refinement source"
    assert _ped_inner_source_role(WINDOWS_HPO) == _ped_inner_source_role(POSIX_HPO)

    assert _ped_inner_source_role(WINDOWS_ARBITRATION) == "Arbitration lineage/context"
    assert _ped_inner_source_role(POSIX_ARBITRATION) == "Arbitration lineage/context"
    assert _ped_inner_source_role(WINDOWS_ARBITRATION) == _ped_inner_source_role(
        POSIX_ARBITRATION
    )


def test_unknown_source_still_classifies_as_other_on_both_separators():
    assert _ped_inner_source_role(r"C:\Users\x\something_else.csv") == "Other source"
    assert _ped_inner_source_role("/home/runner/something_else.csv") == "Other source"


def test_stage_hint_is_the_same_for_both_separators():
    assert _ped_source_stage_hint(WINDOWS_HPO) == "hpo_refinement"
    assert _ped_source_stage_hint(POSIX_HPO) == "hpo_refinement"
    assert _ped_source_stage_hint(WINDOWS_ARBITRATION) == "finalist_arbitration"
    assert _ped_source_stage_hint(POSIX_ARBITRATION) == "finalist_arbitration"


def test_committed_pack_source_roles_are_recognised():
    """The real committed values must classify, not fall through to Other."""

    import pandas as pd
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "dashboard_evidence_pack_reproducibility"
        / "ped_inner_hpo"
        / "inner_hpo_weights.parquet"
    )
    if not path.exists():
        pytest.skip("PED inner HPO pack not present")
    frame = pd.read_parquet(path)
    if "source_file" not in frame.columns:
        pytest.skip("pack carries no source_file column")
    roles = {
        _ped_inner_source_role(value)
        for value in frame["source_file"].dropna().astype(str).unique()
    }
    assert roles == {"HPO refinement source", "Arbitration lineage/context"}
    assert "Other source" not in roles
