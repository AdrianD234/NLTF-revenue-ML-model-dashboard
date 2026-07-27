"""Light RUC must load a promoted fitted state, never refit at score time.

Refitting made Light RUC the only stream whose governed forecast depended on the
machine running it: up to 0.48% across platforms, while PED and Heavy RUC - which
load committed state - agreed to machine epsilon. See
docs/REPLAY_PARITY_INVESTIGATION.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from model_dashboard.forecast_runner import (
    LIGHT_RUC_BASE_FEATURES,
    LIGHT_RUC_RESIDUAL_FEATURES,
    LIGHT_RUC_STATE_HYPERPARAMETERS,
    LIGHT_RUC_STATE_PARITY_TOLERANCE,
    LIGHT_RUC_WINDOW,
    load_light_ruc_promoted_state,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def state():
    return load_light_ruc_promoted_state(ROOT)


def test_promoted_state_matches_its_manifest_hash(state):
    manifest = json.loads(
        (
            ROOT
            / "data"
            / "dashboard_evidence_pack_reproducibility"
            / "light_ruc_vnext"
            / "fitted_model_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert state.sha256 == manifest["production_states"]["LIGHT"]["sha256"]


def test_feature_contract_matches_including_order(state):
    assert list(state.base_features) == list(LIGHT_RUC_BASE_FEATURES)
    assert list(state.residual_features) == list(LIGHT_RUC_RESIDUAL_FEATURES)
    assert np.asarray(state.ols_beta).shape == (len(LIGHT_RUC_BASE_FEATURES) + 1,)


def test_hyperparameters_and_window_match_the_governed_recipe(state):
    assert state.window == LIGHT_RUC_WINDOW
    assert state.random_state == 42
    for name, expected in LIGHT_RUC_STATE_HYPERPARAMETERS.items():
        assert getattr(state.residual_model, name) == expected


def test_state_reproduces_the_archived_training_fit(state):
    """The replay gate: this state is the state that produced the archive."""

    assert state.max_training_fit_replay_delta <= LIGHT_RUC_STATE_PARITY_TOLERANCE
    assert state.max_training_fit_replay_delta == pytest.approx(0.0, abs=1e-12)


def test_training_window_is_the_governed_window(state):
    assert state.train_window_start == "2017Q1"
    assert state.train_window_end == "2025Q4"
    assert state.train_rows == LIGHT_RUC_WINDOW


def test_loader_fails_closed_on_a_hash_mismatch(tmp_path, monkeypatch):
    """A tampered or stale state must raise, never silently refit."""

    import shutil

    source = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "light_ruc_vnext"
    target = tmp_path / "data" / "dashboard_evidence_pack_reproducibility" / "light_ruc_vnext"
    shutil.copytree(source, target)
    manifest_path = target / "fitted_model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["production_states"]["LIGHT"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its manifest hash"):
        load_light_ruc_promoted_state(tmp_path)


def test_loader_fails_closed_when_the_state_is_absent(tmp_path):
    with pytest.raises(ValueError, match="promoted fitted state is missing"):
        load_light_ruc_promoted_state(tmp_path)


def test_production_path_does_not_refit():
    """The forward scorer must not construct a regressor of its own."""

    import inspect

    from model_dashboard import forecast_runner

    source = inspect.getsource(forecast_runner._light_ruc_forward_forecast)
    assert "load_light_ruc_promoted_state" in source
    assert "GradientBoostingRegressor(" not in source, (
        "the decision-facing Light RUC path must load the promoted state, not "
        "fit a new model at score time"
    )
    assert "_ols_fit(" not in source, (
        "the decision-facing Light RUC path must not refit the OLS base"
    )
