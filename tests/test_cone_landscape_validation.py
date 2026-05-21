from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"
ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STREAMS = {"PED", "LIGHT_RUC", "HEAVY_RUC"}


def _landscape() -> pd.DataFrame:
    return pd.read_csv(CURATED_DIR / "candidate_landscape_sample.csv")


def test_candidate_landscape_has_finalists() -> None:
    landscape = _landscape()
    finalist_rows = landscape[landscape["is_recommended_finalist"].astype(bool)]
    assert EXPECTED_STREAMS.issubset(set(finalist_rows["stream"]))


def test_candidate_landscape_has_schiff_benchmarks() -> None:
    landscape = _landscape()
    schiff_rows = landscape[landscape["is_pure_schiff"].astype(bool)]
    assert EXPECTED_STREAMS.issubset(set(schiff_rows["stream"]))
    assert (schiff_rows["candidate_role"] == "Pure Schiff benchmark").all()


def test_candidate_landscape_has_distribution_sample() -> None:
    landscape = _landscape()
    distribution = landscape[landscape["is_distribution_sample"].astype(bool)]
    assert EXPECTED_STREAMS.issubset(set(distribution["stream"]))
    assert len(distribution) >= 90


def test_candidate_landscape_has_frontier_and_top_cluster_by_stream() -> None:
    landscape = _landscape()
    for stream in EXPECTED_STREAMS:
        subset = landscape[landscape["stream"] == stream]
        assert subset["is_frontier"].astype(bool).any(), f"{stream} has no frontier candidate evidence"
        assert (subset["candidate_role"] == "Top candidate").any(), f"{stream} has no top-candidate cluster evidence"
        assert subset["is_distribution_sample"].astype(bool).sum() >= 25, (
            f"{stream} has too few distribution/cone sample rows"
        )


def test_candidate_landscape_is_capped() -> None:
    landscape = _landscape()
    assert len(landscape) <= 400


def test_candidate_landscape_roles_are_populated() -> None:
    landscape = _landscape()
    assert landscape["candidate_role"].notna().all()
    assert not (landscape["candidate_role"].astype(str).str.strip() == "").any()
    assert {"Recommended finalist", "Pure Schiff benchmark", "Distribution sample", "Top candidate"}.issubset(
        set(landscape["candidate_role"])
    )


def test_candidate_landscape_default_mode_is_not_full_raw() -> None:
    landscape = _landscape()
    assert len(landscape) == 293
    assert landscape["include_reason"].astype(str).str.contains("Distribution", case=False).any()
    assert landscape["include_reason"].astype(str).str.contains("Top", case=False).any()


def test_candidate_landscape_lock_files_protect_cone_contract() -> None:
    sampling_spec = (ROOT / "CANDIDATE_LANDSCAPE_SAMPLING_SPEC.lock.md").read_text(encoding="utf-8")
    validation_spec = (ROOT / "CONE_LANDSCAPE_VALIDATION.lock.md").read_text(encoding="utf-8")
    combined = sampling_spec + "\n" + validation_spec
    for phrase in [
        "Hard cap: `<= 400`",
        "Curated cone sample",
        "Competitive frontier",
        "Recommended finalist: star marker",
        "Pure Schiff benchmark: open triangle",
        "Distribution sample: small",
        "candidate-landscape validation gate",
    ]:
        assert phrase in combined
