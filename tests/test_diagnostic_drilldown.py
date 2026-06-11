"""Glass-box diagnostic drilldown: the detail pack must never drift from the
governed scorecard, and the UI layer must never change any values.

Includes the Light RUC provenance-audit guarantees: the archived parent-run
battery is exactly reproducible under its documented recipe, every drilldown
cell carries verified provenance, and the governed battery values themselves
are pinned so no refresh can slip through without an explicit, reviewed
change to this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dashboard_evidence_pack" / "data"

TESTS = ["Calibration R2", "Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan",
         "White", "Jarque-Bera", "Cointegration", "Overall"]

# Pinned governed Light RUC finalist battery values (full stored precision).
# These are the archived parent-run values that govern the dashboard. They
# must never change as a side effect of any build; a deliberate, governed
# diagnostic refresh would update this pin in the same reviewed commit.
LIGHT_GOVERNED_PIN = {
    "durbin_watson": 1.8688711472082513,
    "white_p": 0.12288364588816979,
    "breusch_pagan_p": 0.16348349377405208,
    "jarque_bera_p": 9.291793940203364e-05,
    "skew_resid": 0.902971752531952,
    "arch_lm_p": 0.13373286671920698,
    "adf_p_resid": 0.00562016420599939,
    "ljungbox_p_lag4": 0.020298047465719445,
    "shapiro_p": 0.0004590326457181216,
    "mape_h1": 6.265686406571148,
}


@pytest.fixture(scope="module")
def detail() -> pd.DataFrame:
    return pd.read_parquet(DATA / "diagnostic_test_detail.parquet")


@pytest.fixture(scope="module")
def series() -> pd.DataFrame:
    return pd.read_parquet(DATA / "diagnostic_evidence_series.parquet")


def _light_h1_pairs() -> tuple[np.ndarray, np.ndarray]:
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    fin = pd.read_parquet(DATA / "finalists.parquet").set_index("stream")
    model = str(fin.loc["LIGHT_RUC", "model"])
    g = sp[(sp["stream"] == "LIGHT_RUC") & (sp["model"] == model)
           & (sp["score_basis"] == "current_grid_operational_pooled")
           & (sp["horizon"] == 1)].sort_values("origin")
    return g["actual"].to_numpy(float), g["pred"].to_numpy(float)


def test_detail_covers_every_matrix_cell_with_identical_status(detail: pd.DataFrame) -> None:
    matrix = pd.read_parquet(DATA / "diagnostic_pass_matrix.parquet")
    merged = matrix.merge(
        detail[["stream_label", "diagnostic_test", "pass_status"]],
        on=["stream_label", "diagnostic_test"], suffixes=("_matrix", "_detail"), how="left")
    assert merged["pass_status_detail"].notna().all(), "matrix cell missing from drilldown detail"
    assert (merged["pass_status_matrix"] == merged["pass_status_detail"]).all(), \
        "drilldown status diverged from the governed pass matrix"
    assert len(detail) == len(matrix) == 27


def test_detail_pvalues_match_governed_battery(detail: pd.DataFrame) -> None:
    tests_table = pd.read_parquet(DATA / "diagnostic_tests.parquet").set_index("model")
    mapping = {"ADF": "adf_p_resid", "KPSS": "kpss_p_resid", "Breusch-Pagan": "breusch_pagan_p",
               "White": "white_p", "Jarque-Bera": "jarque_bera_p", "Cointegration": "coint_p_actual_pred"}
    for _, row in detail.iterrows():
        col = mapping.get(row["diagnostic_test"])
        if col is None:
            continue
        stored = float(tests_table.loc[row["model"], col])
        assert abs(float(row["p_value"]) - stored) <= 1e-9 * max(1.0, abs(stored)), \
            f"{row['stream']} {row['diagnostic_test']}"


def test_all_cells_carry_verified_provenance(detail: pd.DataFrame) -> None:
    """Post provenance-audit: every stream reproduces its governed battery
    exactly under its documented convention - no archived-value caveats."""
    assert set(detail["provenance"]) == {"verified_exact_match_to_governed_battery"}
    light = detail[detail["stream"] == "LIGHT_RUC"]
    assert light["provenance_note"].str.contains("parent battery convention").all()
    assert light["residual_scope"].str.contains("percentage-error").all()
    for stream in ("PED", "HEAVY_RUC"):
        rows = detail[detail["stream"] == stream]
        assert rows["residual_scope"].str.contains("native units").all()


def test_light_parent_recipe_reproduces_governed_battery_exactly() -> None:
    """The provenance-audit recipe: percentage-error residuals, hetero exog
    [const, fitted], Ljung-Box raw lags. Must reproduce the governed Light
    RUC row from the live replayed predictions to 1e-9 relative."""
    sm = pytest.importorskip("statsmodels.api")
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch, het_breuschpagan, het_white
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    from statsmodels.tsa.stattools import adfuller

    tests_table = pd.read_parquet(DATA / "diagnostic_tests.parquet")
    stored = tests_table[(tests_table["stream"] == "LIGHT_RUC")
                         & (tests_table["role"] == "Our finalist")].iloc[0]
    a, p = _light_h1_pairs()
    resid = 100.0 * (p - a) / a
    exog = sm.add_constant(np.column_stack([p]))
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        got = {
            "durbin_watson": float(durbin_watson(resid)),
            "white_p": float(het_white(resid, exog)[1]),
            "breusch_pagan_p": float(het_breuschpagan(resid, exog)[1]),
            "jarque_bera_p": float(jarque_bera(resid)[1]),
            "skew_resid": float(jarque_bera(resid)[2]),
            "arch_lm_p": float(het_arch(resid, nlags=4)[1]),
            "adf_p_resid": float(adfuller(resid, autolag="AIC")[1]),
            "ljungbox_p_lag4": float(acorr_ljungbox(resid, lags=[4], return_df=True)["lb_pvalue"].iloc[0]),
            "mape_h1": float(np.mean(np.abs((a - p) / a)) * 100.0),
        }
    for key, val in got.items():
        target = float(stored[key])
        assert abs(val - target) <= 1e-9 * max(1.0, abs(target)), f"{key}: {val} vs {target}"
    # lag-1 autocorrelation convention: Pearson correlation with own lag
    assert abs(float(pd.Series(resid).autocorr(1)) - float(stored["acf1_resid"])) <= 1e-9


def test_governed_light_battery_values_are_unchanged() -> None:
    """Anti-silent-refresh pin: the governed Light RUC battery row must carry
    exactly the archived parent values. A deliberate governed refresh must
    update this pin in the same reviewed commit."""
    tests_table = pd.read_parquet(DATA / "diagnostic_tests.parquet")
    stored = tests_table[(tests_table["stream"] == "LIGHT_RUC")
                         & (tests_table["role"] == "Our finalist")].iloc[0]
    for key, val in LIGHT_GOVERNED_PIN.items():
        assert float(stored[key]) == pytest.approx(val, rel=0, abs=0), key


def test_provenance_audit_artifacts_exist_and_reconcile() -> None:
    rec_path = ROOT / "artifacts" / "diagnostic_drilldown" / "light_ruc_diagnostic_reconciliation.csv"
    md_path = ROOT / "artifacts" / "diagnostic_drilldown" / "light_ruc_diagnostic_provenance_audit.md"
    assert rec_path.exists() and md_path.exists()
    rec = pd.read_csv(rec_path)
    a_rows = rec[rec["section"] == "A_finalist_parent_pct_recipe"]
    assert len(a_rows) >= 20
    assert (a_rows["match_status"] == "exact").all()
    md = md_path.read_text(encoding="utf-8")
    assert "RECONCILED EXACTLY" in md
    assert "No governed value, status, or evidence-pack calculation was changed" in md


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


def test_evidence_series_test_residual_follows_stream_convention(series: pd.DataFrame) -> None:
    for stream, g in series.groupby("stream"):
        if stream == "LIGHT_RUC":
            expected = 100.0 * (g["pred"] - g["actual"]) / g["actual"]
            assert (g["test_residual"] - expected).abs().max() <= 1e-9
            assert set(g["test_residual_units"]) == {"% of actual (forecast - actual)"}
        else:
            assert (g["test_residual"] - g["residual"]).abs().max() <= 1e-9
            assert set(g["test_residual_units"]) == {"native units"}


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
