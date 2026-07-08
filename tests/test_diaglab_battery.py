"""Milestone 0: the Diagnostics Lab battery must reproduce governance exactly.

The battery is only useful if a 'Pass' from it means the same thing as a
'Pass' in the governed Diagnostic Pass Matrix. These tests recompute the
battery from the shipped finalist horizon-1 residuals and pin every statistic
and status against ``diagnostic_test_detail.parquet`` /
``diagnostic_pass_matrix.parquet`` values.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.diaglab_battery import (
    ADVISORY_TESTS,
    CORE_TESTS,
    BatteryResult,
    battery_from_predictions,
    finalist_h1_pairs,
    run_battery,
)

ROOT = Path(__file__).resolve().parents[1]
FINALISTS = {"PED": "PED__VNEXT_SOLVED_CONVEX_TOP2", "LIGHT_RUC": "dynamic_RESID_GBR_n150_d1_lr0.05_w36"}


@pytest.fixture(scope="module")
def governed_detail() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/dashboard_evidence_pack/data/diagnostic_test_detail.parquet")


def _battery(stream: str) -> BatteryResult:
    pairs = finalist_h1_pairs(ROOT, stream, FINALISTS[stream])
    return run_battery(pairs["actual"].to_numpy(float), pairs["pred"].to_numpy(float), stream=stream)


@pytest.mark.parametrize("stream", ["PED", "LIGHT_RUC"])
def test_battery_reproduces_governed_statistics(stream: str, governed_detail: pd.DataFrame) -> None:
    result = _battery(stream)
    detail = governed_detail[governed_detail["stream"].astype(str).eq(stream)].set_index("diagnostic_test")

    assert result.n == int(detail.loc["Durbin-Watson", "n_rows"])
    checks = {
        "Durbin-Watson": ("durbin_watson", "statistic"),
        "ADF": ("adf_stat", "statistic"),
        "KPSS": ("kpss_stat", "statistic"),
        "Breusch-Pagan": ("breusch_pagan_stat", "statistic"),
        "White": ("white_stat", "statistic"),
        "Jarque-Bera": ("jarque_bera_stat", "statistic"),
        "Cointegration": ("coint_stat", "statistic"),
        "Calibration R2": ("mz_r2", "statistic"),
    }
    for test_name, (stat_key, col) in checks.items():
        governed = float(detail.loc[test_name, col])
        assert result.stats[stat_key] == pytest.approx(governed, rel=1e-9), test_name

    assert result.stats["white_p"] == pytest.approx(float(detail.loc["White", "p_value"]), rel=1e-9)
    assert result.stats["jarque_bera_p"] == pytest.approx(float(detail.loc["Jarque-Bera", "p_value"]), rel=1e-9)
    assert result.stats["coint_p_actual_pred"] == pytest.approx(float(detail.loc["Cointegration", "p_value"]), rel=1e-9)
    # DW's governed companion p-value is Ljung-Box at lag 8.
    assert result.stats["ljungbox_p_lag8"] == pytest.approx(float(detail.loc["Durbin-Watson", "p_value"]), rel=1e-9)


@pytest.mark.parametrize("stream", ["PED", "LIGHT_RUC", "HEAVY_RUC"])
def test_battery_statuses_match_the_governed_pass_matrix(stream: str) -> None:
    matrix = pd.read_parquet(ROOT / "data/dashboard_evidence_pack/data/diagnostic_pass_matrix.parquet")
    tests = pd.read_parquet(ROOT / "data/dashboard_evidence_pack/data/diagnostic_tests.parquet")
    finalist_model = tests[tests["stream"].astype(str).eq(stream) & tests["role"].astype(str).eq("Our finalist")]["model"].iloc[0]
    pairs = finalist_h1_pairs(ROOT, stream, str(finalist_model))
    result = run_battery(pairs["actual"].to_numpy(float), pairs["pred"].to_numpy(float), stream=stream)

    governed = matrix[matrix["stream"].astype(str).eq(stream)].set_index("diagnostic_test")["pass_status"]
    for test_name in [*CORE_TESTS, *ADVISORY_TESTS, "Calibration R2", "Overall"]:
        assert result.status[test_name] == str(governed.loc[test_name]), test_name


def test_battery_from_predictions_matches_direct_pairs() -> None:
    pairs = finalist_h1_pairs(ROOT, "PED", FINALISTS["PED"])
    frame = pairs.assign(horizon=1)
    via_frame = battery_from_predictions(frame, "PED")
    direct = _battery("PED")
    assert via_frame.stats["durbin_watson"] == pytest.approx(direct.stats["durbin_watson"], rel=1e-12)
    assert via_frame.status == direct.status


def test_battery_overall_logic() -> None:
    rng = np.random.default_rng(42)
    n = 60
    actual = 100.0 + np.cumsum(rng.normal(0, 1, n))
    # Well-behaved residuals: pred = actual + white noise -> everything passes.
    pred = actual + rng.normal(0, 0.5, n)
    good = run_battery(actual, pred, stream="PED")
    assert good.status["Durbin-Watson"] == "Pass"
    assert good.overall in {"Pass", "Watch"}
    # Strongly autocorrelated errors -> DW fails -> Overall fails.
    ar_noise = np.zeros(n)
    for i in range(1, n):
        ar_noise[i] = 0.9 * ar_noise[i - 1] + rng.normal(0, 0.3)
    bad = run_battery(actual, actual + ar_noise, stream="PED")
    assert bad.status["Durbin-Watson"] == "Fail"
    assert bad.overall == "Fail"


def test_battery_small_sample_is_unavailable() -> None:
    result = run_battery(np.ones(5) * 10, np.ones(5) * 11, stream="PED")
    assert result.overall == "Unavailable"
