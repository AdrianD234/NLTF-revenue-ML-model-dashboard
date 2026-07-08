"""Orchestrator mechanics: composition targeting, ranking, spec round-trips."""
from __future__ import annotations

import json

import pytest

from pipeline.diaglab_arms import DiagSpec, feature_bundle
from pipeline.diaglab_orchestrator import (
    candidate_sort_key,
    followups_for,
    neighbourhood,
    seed_grid,
    _spec_from_row,
)


def _row_for(spec: DiagSpec, **status) -> dict:
    row = {
        "stream": spec.stream,
        "model": spec.name,
        "arm": spec.arm,
        "kind": spec.kind,
        "window": spec.window if spec.window is not None else "expanding",
        "ylags": ",".join(str(l) for l in spec.ylags),
        "weight_mode": spec.weight_mode or "",
        "pulses": spec.pulses,
        "params_json": spec.params_json,
        "features_json": json.dumps(list(spec.features)),
        "core_passes": 5,
        "paper_horizon_mean_mape": 3.0,
    }
    row.update(status)
    return row


def test_seed_grids_are_unique_and_deterministic() -> None:
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        first = [s.name for s in seed_grid(stream)]
        second = [s.name for s in seed_grid(stream)]
        assert first == second
        assert len(first) == len(set(first)), "duplicate spec names in seed grid"
    assert len(seed_grid("PED")) >= 15


def test_followups_target_the_failing_test() -> None:
    spec = DiagSpec("PED", "A", "arx", feature_bundle("PED", ["levels", "seasonal"]), None, ylags=(1,))
    white_fail = _row_for(spec, **{"status__White": "Fail"})
    remedies = followups_for(white_fail, spec)
    assert any(s.weight_mode == "covid_down" for s in remedies)
    assert any(s.weight_mode == "regime_var" for s in remedies)

    jb_watch = _row_for(spec, **{"status__Jarque-Bera": "Watch"})
    remedies = followups_for(jb_watch, spec)
    assert any(s.pulses for s in remedies)

    dw_fail = _row_for(spec, **{"status__Durbin-Watson": "Fail"})
    remedies = followups_for(dw_fail, spec)
    assert any(s.ylags == (1, 4) for s in remedies)

    glsar = DiagSpec("PED", "B", "glsar", spec.features, None, params_json=json.dumps({"ar": 1}))
    remedies = followups_for(_row_for(glsar, **{"status__Durbin-Watson": "Fail"}), glsar)
    assert any(json.loads(s.params_json).get("ar") == 2 for s in remedies)


def test_candidate_sort_prefers_core_passes_then_mape() -> None:
    better_diag = {"core_passes": 6, "paper_horizon_mean_mape": 4.0, "status__Jarque-Bera": "Watch"}
    better_mape = {"core_passes": 5, "paper_horizon_mean_mape": 2.5, "status__Jarque-Bera": "Pass"}
    assert candidate_sort_key(better_diag) < candidate_sort_key(better_mape)
    jb_pass = {"core_passes": 6, "paper_horizon_mean_mape": 4.0, "status__Jarque-Bera": "Pass"}
    assert candidate_sort_key(jb_pass) < candidate_sort_key(better_diag)


def test_spec_row_round_trip() -> None:
    spec = DiagSpec(
        "PED", "B", "glsar", feature_bundle("PED", ["levels", "trend", "seasonal"]),
        56, params_json=json.dumps({"ar": 2}), weight_mode="covid_down", pulses=True,
    )
    row = _row_for(spec)
    rebuilt = _spec_from_row(row)
    assert rebuilt.kind == spec.kind
    assert rebuilt.window == spec.window
    assert rebuilt.features == spec.features
    assert rebuilt.weight_mode == spec.weight_mode
    assert rebuilt.pulses is True
    assert json.loads(rebuilt.params_json) == {"ar": 2}


def test_neighbourhood_toggles_window() -> None:
    spec = DiagSpec("PED", "A", "arx", feature_bundle("PED", ["levels"]), None, ylags=(1,))
    near = neighbourhood(spec)
    assert any(s.window == 56 for s in near)
    assert any(s.ylags == (1, 2) for s in near)
