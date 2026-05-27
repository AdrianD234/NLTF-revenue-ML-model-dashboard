from __future__ import annotations

import pandas as pd

from model_dashboard.diagnostic_matrix import (
    DIAGNOSTIC_TEST_ORDER,
    DIAGNOSTIC_TOOLTIP_COPY,
    diagnostic_pass_matrix_frame,
    diagnostic_pass_matrix_html,
    diagnostic_tooltip,
)


def test_diagnostic_tooltip_copy_is_plain_english_and_complete() -> None:
    expected = {
        "ADF": "Augmented Dickey-Fuller test",
        "KPSS": "Kwiatkowski-Phillips-Schmidt-Shin test",
        "White": "White test",
        "Jarque-Bera": "Jarque-Bera test",
        "Cointegration": "Cointegration test",
        "Calibration R2": "Calibration R-squared",
        "Overall": "Overall diagnostic status",
    }
    assert set(DIAGNOSTIC_TEST_ORDER).issubset(DIAGNOSTIC_TOOLTIP_COPY)
    for label, phrase in expected.items():
        assert phrase in diagnostic_tooltip(label)


def test_diagnostic_pass_matrix_html_has_accessible_hover_and_focus_tooltips() -> None:
    diagnostics = pd.DataFrame(
        [
            {
                "stream_label": "PED VKT per capita",
                "role": "Our finalist",
                "adj_r2": 0.85,
                "durbin_watson": 2.0,
                "adf_pvalue": 0.01,
                "kpss_pvalue": 0.20,
                "breusch_pagan_pvalue": 0.20,
                "white_pvalue": 0.20,
                "jarque_bera_pvalue": 0.001,
                "cointegration_pvalue": 0.01,
            }
        ]
    )

    markup = diagnostic_pass_matrix_html(diagnostics)

    assert "diagnostic-tooltip-matrix" in markup
    assert "diagnostic-pass-matrix" in markup
    assert "tabindex='0'" in markup
    assert "role='tooltip'" in markup
    assert "aria-describedby='diag-tooltip-header-" in markup
    assert "aria-label='ADF:" in markup
    assert "ⓘ" in markup
    assert "Augmented Dickey-Fuller test" in markup
    assert "Kwiatkowski-Phillips-Schmidt-Shin test" in markup
    assert "Jarque-Bera test" in markup


def test_diagnostic_pass_matrix_preserves_status_logic_and_watch_overall() -> None:
    diagnostics = pd.DataFrame(
        [
            {
                "stream_label": "PED VKT per capita",
                "role": "Our finalist",
                "adj_r2": 0.85,
                "durbin_watson": 2.0,
                "adf_pvalue": 0.01,
                "kpss_pvalue": 0.20,
                "breusch_pagan_pvalue": 0.20,
                "white_pvalue": 0.20,
                "jarque_bera_pvalue": 0.001,
                "cointegration_pvalue": 0.01,
            }
        ]
    )

    matrix = diagnostic_pass_matrix_frame(diagnostics)

    assert matrix.loc[0, "Jarque-Bera"] == "Caution"
    assert matrix.loc[0, "Overall"] == "Watch"
    assert matrix.columns.tolist() == ["Stream"] + DIAGNOSTIC_TEST_ORDER


def test_diagnostic_pass_matrix_long_format_keeps_pass_watch_fail_values() -> None:
    diagnostics = pd.DataFrame(
        [
            {"stream_label": "PED VKT per capita", "diagnostic_test": "ADF", "pass_status": "Pass"},
            {"stream_label": "PED VKT per capita", "diagnostic_test": "KPSS", "pass_status": "Watch"},
            {"stream_label": "PED VKT per capita", "diagnostic_test": "White", "pass_status": "Fail"},
        ]
    )

    matrix = diagnostic_pass_matrix_frame(diagnostics)

    assert matrix.loc[0, "ADF"] == "Pass"
    assert matrix.loc[0, "KPSS"] == "Watch"
    assert matrix.loc[0, "White"] == "Fail"
    assert matrix.loc[0, "Durbin-Watson"] == "Unavailable"
