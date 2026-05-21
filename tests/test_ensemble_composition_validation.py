from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"
EXPECTED_STREAMS = {"PED", "LIGHT_RUC", "HEAVY_RUC"}


def _ensemble() -> pd.DataFrame:
    return pd.read_csv(CURATED_DIR / "ensemble_composition.csv")


def test_ensemble_composition_has_all_streams() -> None:
    assert EXPECTED_STREAMS.issubset(set(_ensemble()["stream"]))


def test_ensemble_weights_are_positive() -> None:
    weights = pd.to_numeric(_ensemble()["weight"], errors="coerce")
    assert weights.notna().all()
    assert (weights > 0).all()


def test_ensemble_component_labels_short() -> None:
    labels = _ensemble()["component_short"].astype(str)
    assert labels.str.len().max() <= 40
    assert not labels.str.contains("__", regex=False).any()


def test_component_lookup_contains_full_names() -> None:
    ensemble = _ensemble()
    assert ensemble["component_model"].astype(str).str.contains("__", regex=False).any()
    assert ensemble["component_rank"].notna().all()


def test_ensemble_hover_is_readable() -> None:
    ensemble = _ensemble()
    assert ensemble["weight_label"].astype(str).str.match(r"^\d+\.\d%$").all()
    assert not ensemble["stream_label"].astype(str).str.contains("_", regex=False).any()
