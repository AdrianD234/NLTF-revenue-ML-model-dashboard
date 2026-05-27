from __future__ import annotations

import re

import pandas as pd

from app import benchmark_summary_table_html, decision_summary_table_html


def test_benchmark_summary_exposes_clean_metric_tooltips() -> None:
    html = benchmark_summary_table_html(
        pd.DataFrame(
            [
                {
                    "stream_label": "Light RUC volume",
                    "schiff_quarterly_mape": 8.52,
                    "finalist_quarterly_mape": 5.36,
                    "quarterly_gain_pp": 3.16,
                    "schiff_annual_mape": 2.70,
                    "finalist_annual_mape": 1.27,
                    "annual_gain_pp": 1.43,
                    "win_rate": 62.70,
                }
            ]
        )
    )

    required = [
        "Schiff benchmark quarterly MAPE minus finalist quarterly MAPE",
        "Schiff benchmark annual MAPE minus finalist annual MAPE",
        "matched forecast comparisons",
        "Schiff specification benchmark under the active score basis",
    ]
    for text in required:
        assert text in html

    assert "Full-sample Qtr Gain" in html
    assert "Full-sample Annual Gain" in html
    assert "Paired Win Rate" in html
    assert "paired_win_rate" not in html
    assert "quarterly_gain_pp" not in html
    assert not re.search(r"\d+\.\d{4,}", html)


def test_decision_summary_recommendation_badges_have_hover_copy() -> None:
    html = decision_summary_table_html(
        pd.DataFrame(
            [
                {
                    "Stream": "PED VKT per capita",
                    "Full-sample Qtr Gain": 1.44,
                    "Full-sample Annual Gain": 1.55,
                    "Paired Win Rate": 69.05,
                    "Recommendation": "Promote",
                },
                {
                    "Stream": "Light RUC volume",
                    "Full-sample Qtr Gain": 3.16,
                    "Full-sample Annual Gain": -0.42,
                    "Paired Win Rate": 51.20,
                    "Recommendation": "Promote - Annual Watch",
                },
                {
                    "Stream": "Heavy RUC volume",
                    "Full-sample Qtr Gain": 0.12,
                    "Full-sample Annual Gain": 0.08,
                    "Paired Win Rate": 49.50,
                    "Recommendation": "Needs Stage 2",
                },
            ]
        )
    )

    assert "MAPE gain, paired win rate, diagnostics and caveats" in html
    assert "Promoted because the finalist beats the Schiff specification benchmark" in html
    assert "annual aggregation is weaker and should be monitored" in html
    assert "Further model refinement or evidence is needed" in html
    assert "role='tooltip'" in html
    assert "tabindex='0'" in html
    assert "recommendation" in html.lower()
    assert "recommendation_status" not in html
