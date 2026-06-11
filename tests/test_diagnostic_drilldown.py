"""Glass-box diagnostic drilldown: the detail pack must never drift from the
governed scorecard, and the UI layer must never change any values."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dashboard_evidence_pack" / "data"

TESTS = ["Calibration R2", "Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan",
         "White", "Jarque-Bera", "Cointegration", "Overall"]


@pytest.fixture(scope="module")
def detail() -> pd.DataFrame:
    return pd.read_parquet(DATA / "diagnostic_test_detail.parquet")


@pytest.fixture(scope="module")
def series() -> pd.DataFrame:
    return pd.read_parquet(DATA / "diagnostic_evidence_series.parquet")


def test_detail_covers_every_matrix_cell_with_identical_status(detail: pd.DataFrame) -> None:
    matrix = pd.read_parquet(DATA / "diagnostic_pass_matrix.parquet")
    merged = matrix.merge(
        detail[["stream_label", "diagnostic_test", "pass_status"]],
        on=["stream_label", "diagnostic_test"], suffixes=("_matrix", "_detail"), how="left")
    assert merged["pass_status_detail"].notna().all(), "matrix cell missing from drilldown detail"
    assert (merged["pass_status_matrix"] == merged["pass_status_detail"]).all(), \
        "drilldown status diverged from the governed pass matrix"
    assert len(detail) == len(matrix) == 27


def test_detail_pvalues_match_governed_battery_for_vnext_streams(detail: pd.DataFrame) -> None:
    tests_table = pd.read_parquet(DATA / "diagnostic_tests.parquet").set_index("model")
    mapping = {"ADF": "adf_p_resid", "KPSS": "kpss_p_resid", "Breusch-Pagan": "breusch_pagan_p",
               "White": "white_p", "Jarque-Bera": "jarque_bera_p", "Cointegration": "coint_p_actual_pred"}
    verified = detail[detail["provenance"] == "verified_exact_match_to_governed_battery"]
    assert not verified.empty
    for _, row in verified.iterrows():
        col = mapping.get(row["diagnostic_test"])
        if col is None:
            continue
        stored = float(tests_table.loc[row["model"], col])
        assert abs(float(row["p_value"]) - stored) <= 1e-9 * max(1.0, abs(stored))


def test_archived_provenance_is_flagged_not_silently_recomputed(detail: pd.DataFrame) -> None:
    light = detail[detail["stream"] == "LIGHT_RUC"]
    assert set(light["provenance"]) == {"archived_parent_values_governed"}
    assert light["provenance_note"].str.contains("authoritative").all()


def test_fstatistics_present_for_regression_based_tests(detail: pd.DataFrame) -> None:
    for test in ["Calibration R2", "Breusch-Pagan", "White"]:
        rows = detail[detail["diagnostic_test"] == test]
        assert rows["f_statistic"].notna().all(), f"{test} missing F-statistic"
        assert rows["f_p_value"].notna().all(), f"{test} missing F p-value"
    assert detail[detail["diagnostic_test"] == "Durbin-Watson"]["f_statistic"].isna().all()


def test_every_cell_carries_glassbox_copy(detail: pd.DataFrame) -> None:
    for col in ["null_hypothesis", "threshold_rule", "blocks_approval",
                "statistic_name", "source_dataset", "provenance_note"]:
        assert detail[col].astype(str).str.len().gt(10).all(), col
    # Short canonical names like "LM p-value" (and "n/a" for Overall) are valid.
    assert detail["p_value_name"].astype(str).str.len().gt(2).all()


def test_evidence_series_consistent_with_scorecard_predictions(series: pd.DataFrame) -> None:
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    fin = pd.read_parquet(DATA / "finalists.parquet").set_index("stream")
    for stream, g in series.groupby("stream"):
        model = str(fin.loc[stream, "model"])
        live = sp[(sp["stream"] == stream) & (sp["model"] == model)
                  & (sp["score_basis"] == "current_grid_operational_pooled") & (sp["horizon"] == 1)]
        merged = g.merge(live[["target_period", "actual", "pred"]],
                         on="target_period", suffixes=("_series", "_live"))
        assert len(merged) == len(g)
        assert (merged["actual_series"] - merged["actual_live"]).abs().max() <= 1e-9
        assert (merged["pred_series"] - merged["pred_live"]).abs().max() <= 1e-9
        # residual identity and equilibrium-error definition
        assert (merged["residual"] - (merged["actual_series"] - merged["pred_series"])).abs().max() <= 1e-9
        assert (g["equilibrium_error"] - (g["actual"] - g["mz_fitted"])).abs().max() <= 1e-9


def test_charts_build_for_all_cells(detail: pd.DataFrame, series: pd.DataFrame) -> None:
    from model_dashboard.diagnostic_drilldown import TEST_ORDER, _evidence_chart, _overall_checklist

    acf = pd.read_parquet(DATA / "diagnostic_acf.parquet")
    for stream in ["PED", "LIGHT_RUC", "HEAVY_RUC"]:
        s = series[series["stream"] == stream].sort_values("target_period")
        rows = detail[detail["stream"] == stream].set_index("diagnostic_test")
        for test in TEST_ORDER:
            if test == "Overall":
                checklist = _overall_checklist(detail, stream)
                assert len(checklist) == 8
                assert set(checklist["Role"]) <= {"Core", "Advisory", "Context"}
            else:
                assert _evidence_chart(test, s, acf, rows.loc[test]) is not None


def test_drilldown_is_read_only_against_pack() -> None:
    """The UI module must not import anything that can rewrite pack tables."""
    src = (ROOT / "model_dashboard" / "diagnostic_drilldown.py").read_text(encoding="utf-8")
    assert "to_parquet" not in src
    assert "statsmodels" not in src
