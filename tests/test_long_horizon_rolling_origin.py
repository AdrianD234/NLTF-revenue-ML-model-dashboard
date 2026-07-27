"""No-target-leakage invariants for the H13-H20 rolling-origin evidence.

Checking that a target follows its origin proves the indexing is right. It does
not prove the model never saw the answer. These tests prove the stronger claim
directly: corrupt every actual target after the origin, and the forecasts must
not move at all. If any future actual reached a training row, a fitted
coefficient or a lagged feature, the predictions would change.

Declared design: exogenous drivers ARE the observed future values (this is an
explicitly actual-driver experiment). Future *targets* are used only for
scoring, and for the recursive lag members only their own predicted values are
fed forward, exactly as production does.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pipeline.vnext_core as vc
from scripts.evaluate_long_horizon_rolling_origin import (
    _assert_no_future_target_leakage,
    _balanced_origins,
    _light_ruc_rolling_origin,
    _member_specs,
    light_ruc_feature_frame,
)

CORRUPTION_FACTOR = 1.75
MAX_HORIZON = 20


@pytest.fixture(scope="module")
def heavy_ruc_stream_data():
    return vc.load_stream_data(ROOT, "HEAVY_RUC")


def _corrupt_targets_after(stream_data, origin):
    """Multiply every actual target after ``origin``; keep exog untouched."""

    corrupted = vc.StreamData(
        stream=stream_data.stream,
        history=stream_data.history,
        exog=stream_data.exog,
        y_raw=stream_data.y_raw.copy(),
        y_log=stream_data.y_log.copy(),
        feature_sets=stream_data.feature_sets,
        latest_actual=stream_data.latest_actual,
    )
    future = corrupted.y_raw.index > origin
    corrupted.y_raw.loc[future] = corrupted.y_raw.loc[future] * CORRUPTION_FACTOR
    corrupted.y_log.loc[future] = np.log(corrupted.y_raw.loc[future])
    return corrupted


def test_target_lag_member_ignores_future_actuals(heavy_ruc_stream_data):
    """The strongest check: a recursive-lag member must not move at all.

    Heavy RUC M1 carries include_target_lags=True, so it is the member where a
    realized future value could leak into a lagged dependent variable.
    """

    specs, _weights, _finalist = _member_specs("HEAVY_RUC")
    spec = next(spec for spec in specs if spec.include_target_lags)

    original = vc.MAX_HORIZON
    vc.MAX_HORIZON = MAX_HORIZON
    try:
        origins = vc.backtest_origins(heavy_ruc_stream_data)
        assert origins, "no rolling origins available"
        origin = origins[len(origins) // 2]

        clean = vc.backtest(heavy_ruc_stream_data, spec, origins=[origin]).predictions
        corrupted = vc.backtest(
            _corrupt_targets_after(heavy_ruc_stream_data, origin),
            spec,
            origins=[origin],
        ).predictions
    finally:
        vc.MAX_HORIZON = original

    assert not clean.empty
    merged = clean.merge(
        corrupted,
        on=["origin", "target_period", "horizon"],
        suffixes=("_clean", "_corrupt"),
    )
    assert len(merged) == len(clean)

    # The forecasts must be bit-for-bit unchanged ...
    np.testing.assert_array_equal(
        merged["pred_clean"].to_numpy(dtype=float),
        merged["pred_corrupt"].to_numpy(dtype=float),
    )
    # ... while the actuals demonstrably did change, so the corruption was real
    # and the test is not vacuous.
    assert not np.allclose(
        merged["actual_clean"].to_numpy(dtype=float),
        merged["actual_corrupt"].to_numpy(dtype=float),
    )


def test_training_uses_only_rows_at_or_before_the_origin(heavy_ruc_stream_data):
    """Corrupting the future must not move the fitted state itself."""

    specs, _weights, _finalist = _member_specs("HEAVY_RUC")
    spec = specs[0]

    original = vc.MAX_HORIZON
    vc.MAX_HORIZON = MAX_HORIZON
    try:
        origins = vc.backtest_origins(heavy_ruc_stream_data)
        origin = origins[len(origins) // 2]
        clean_state = vc.fit_at_origin(heavy_ruc_stream_data, spec, origin)
        corrupt_state = vc.fit_at_origin(
            _corrupt_targets_after(heavy_ruc_stream_data, origin), spec, origin
        )
    finally:
        vc.MAX_HORIZON = original

    assert clean_state is not None and corrupt_state is not None
    # Same training rows in, so the same predictions out for an identical row.
    probe = {column: 1.0 for column in vc.feature_columns(heavy_ruc_stream_data, spec)}
    base_probe = (
        {column: 1.0 for column in heavy_ruc_stream_data.feature_sets[spec.base_feature_set]}
        if spec.model_kind == "resid_gbr"
        else None
    )
    assert vc.predict_one(clean_state, probe, base_probe) == pytest.approx(
        vc.predict_one(corrupt_state, probe, base_probe), rel=0.0, abs=0.0
    )


def test_light_ruc_recipe_ignores_future_actuals():
    """Light RUC has no target lags; prove it, rather than asserting it."""

    from model_dashboard.forecast_runner import LIGHT_RUC_WINDOW

    frame = light_ruc_feature_frame()
    # The first origin sits at position LIGHT_RUC_WINDOW - 1, so corrupt from
    # the row immediately after it. That origin's whole training window is then
    # clean while every one of its forecast targets has been corrupted.
    split = LIGHT_RUC_WINDOW
    assert len(frame) > split + 1, "history too short to exercise this invariant"
    first_origin = str(frame.iloc[split - 1]["period"])

    corrupted = frame.copy()
    corrupted.loc[corrupted.index[split:], "target"] = (
        pd.to_numeric(corrupted.loc[corrupted.index[split:], "target"], errors="coerce")
        * CORRUPTION_FACTOR
    )

    clean_out = _light_ruc_rolling_origin(MAX_HORIZON, frame=frame)
    corrupt_out = _light_ruc_rolling_origin(MAX_HORIZON, frame=corrupted)

    merged = clean_out.merge(
        corrupt_out,
        on=["origin", "target_period", "horizon"],
        suffixes=("_clean", "_corrupt"),
    )
    assert not merged.empty

    early = merged[merged["origin"].astype(str).eq(first_origin)]
    assert not early.empty, f"no rows for the clean-window origin {first_origin}"
    np.testing.assert_allclose(
        early["pred_clean"].to_numpy(dtype=float),
        early["pred_corrupt"].to_numpy(dtype=float),
        rtol=0.0,
        atol=0.0,
    )
    # The corruption did reach that origin's scored actuals, so this is not
    # a vacuous comparison of two identical inputs.
    assert not np.allclose(
        early["actual_clean"].to_numpy(dtype=float),
        early["actual_corrupt"].to_numpy(dtype=float),
    )


def test_ordering_invariant_rejects_a_target_at_or_before_its_origin():
    good = pd.DataFrame(
        {"origin": ["2020Q1"], "target_period": ["2020Q2"], "horizon": [1]}
    )
    _assert_no_future_target_leakage(good)

    same_quarter = pd.DataFrame(
        {"origin": ["2020Q1"], "target_period": ["2020Q1"], "horizon": [0]}
    )
    with pytest.raises(ValueError, match="at or before its origin"):
        _assert_no_future_target_leakage(same_quarter)

    wrong_horizon = pd.DataFrame(
        {"origin": ["2020Q1"], "target_period": ["2020Q3"], "horizon": [1]}
    )
    with pytest.raises(ValueError, match="target-minus-origin"):
        _assert_no_future_target_leakage(wrong_horizon)


def test_balanced_cohort_uses_identical_origins_at_every_horizon():
    """The balanced comparison is only meaningful if the origins really match."""

    predictions = pd.DataFrame(
        {
            "stream": ["A"] * 5 + ["A"] * 3,
            "origin": ["o1"] * 5 + ["o2"] * 3,
            "target_period": [f"t{i}" for i in range(5)] + [f"t{i}" for i in range(3)],
            "horizon": list(range(1, 6)) + list(range(1, 4)),
            "actual": [1.0] * 8,
            "pred": [1.0] * 8,
        }
    )
    balanced = _balanced_origins(predictions, 5)
    assert set(balanced["origin"]) == {"o1"}
    assert sorted(balanced["horizon"]) == [1, 2, 3, 4, 5]


def test_committed_evidence_declares_its_leakage_and_driver_basis():
    """The report must state the basis, not leave the reader to infer it."""

    report = (
        ROOT / "artifacts" / "long_horizon_validation" / "long_horizon_report.md"
    ).read_text(encoding="utf-8")
    assert "actual-driver" in report.lower()
    assert "recursive predicted target lags" in report.lower()
    assert "_assert_no_future_target_leakage" in report

    provenance = pd.read_csv(
        ROOT / "artifacts" / "long_horizon_validation" / "long_horizon_provenance.csv"
    )
    assert set(provenance["driver_basis"].astype(str)) == {"actual_observed_drivers"}
    assert set(provenance["target_lag_basis"].astype(str)) == {
        "recursive_predicted_target_lags",
        "no_target_lags_in_recipe",
    }
    assert provenance["fitted_model_manifest_sha256"].astype(str).str.len().eq(64).all()
    assert provenance["input_history_sha256"].astype(str).str.len().eq(64).all()
