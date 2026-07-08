from __future__ import annotations

import numpy as np
import pandas as pd

from app import (
    _denton_quarterly_split,
    _disaggregate_annual_rows_to_quarterly,
    _june_year_quarters,
    _quarterly_disaggregation_indicator_id,
)


def test_denton_split_preserves_annual_sums_flat_indicator() -> None:
    annual = np.array([400.0, 480.0, 440.0])
    quarters = _denton_quarterly_split(annual, np.ones(12), average=False)
    sums = quarters.reshape(3, 4).sum(axis=1)
    assert np.allclose(sums, annual, atol=1e-6)
    # Smooth split: quarter-to-quarter movement stays modest relative to level.
    assert np.max(np.abs(np.diff(quarters))) < 30.0


def test_denton_split_follows_indicator_seasonality() -> None:
    annual = np.array([400.0, 400.0])
    indicator = np.tile([0.8, 1.2, 0.9, 1.1], 2)
    quarters = _denton_quarterly_split(annual, indicator, average=False)
    assert np.allclose(quarters.reshape(2, 4).sum(axis=1), annual, atol=1e-6)
    # Q2 (indicator 1.2) must exceed Q1 (indicator 0.8) in both years.
    assert quarters[1] > quarters[0]
    assert quarters[5] > quarters[4]


def test_denton_split_average_preserving_for_per_unit_series() -> None:
    annual = np.array([1500.0, 1520.0])
    quarters = _denton_quarterly_split(annual, np.ones(8), average=True)
    means = quarters.reshape(2, 4).mean(axis=1)
    assert np.allclose(means, annual, atol=1e-6)


def test_june_year_quarter_mapping() -> None:
    assert _june_year_quarters(2025) == ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]


def test_indicator_mapping_uses_stream_activity_paths() -> None:
    assert _quarterly_disaggregation_indicator_id("ped_volume") == "ped_vkt_per_capita"
    assert _quarterly_disaggregation_indicator_id("gross_ped_revenue") == "ped_vkt_per_capita"
    assert _quarterly_disaggregation_indicator_id("light_ruc_revenue") == "light_ruc_net_km"
    assert _quarterly_disaggregation_indicator_id("heavy_ruc_net_revenue") == "heavy_ruc_net_km"
    # Native quarterly series never route through disaggregation.
    assert _quarterly_disaggregation_indicator_id("ped_vkt_per_capita") == ""
    # Aggregates fall back to the smooth split.
    assert _quarterly_disaggregation_indicator_id("total_nltf_net_revenue") == ""


def test_forecast_traces_are_not_disaggregated_into_the_actuals_era() -> None:
    """A finalist nowcast anchor row (FY2025) must not become 2024Q3-2025Q2
    forecast quarters overlapping the actuals; forecast traces start at the
    first forecast June year (FY2026 -> 2025Q3)."""
    rows = []
    for fy, row_type, trace in [
        (2024, "historical_actual", "Actual"),
        (2025, "historical_actual", "Actual"),
        (2025, "future_forecast", "Current finalist Base case"),
        (2026, "future_forecast", "Current finalist Base case"),
    ]:
        rows.append(
            {
                "trace_name": trace,
                "scenario_name": "" if row_type == "historical_actual" else "current_basecase",
                "fed_path": "Current planned path",
                "series_id": "gross_ped_revenue",
                "series_label": "PED revenue",
                "stream": "gross_ped_revenue",
                "stream_label": "PED revenue",
                "row_type": row_type,
                "time_grain": "june_year",
                "period": f"FY{fy}",
                "june_year": fy,
                "value": 2000.0,
                "value_unit": "$m nominal ex GST",
            }
        )
    derived = _disaggregate_annual_rows_to_quarterly(pd.DataFrame(rows), pd.DataFrame())
    forecast = derived[derived["trace_name"].eq("Current finalist Base case")]
    actual = derived[derived["trace_name"].eq("Actual")]
    assert list(forecast["period"]) == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert actual["period"].max() == "2025Q2"
    # no overlap: forecast quarters all come after the last actual quarter
    assert min(forecast["period"]) > actual["period"].max()


def test_disaggregated_rows_are_tagged_and_sum_to_annual() -> None:
    annual_rows = pd.DataFrame(
        [
            {
                "trace_name": "Actual",
                "scenario_name": "",
                "fed_path": "Current planned path",
                "series_id": "total_nltf_net_revenue",
                "series_label": "Total NLTF revenue",
                "stream": "total_nltf_net_revenue",
                "stream_label": "Total NLTF revenue",
                "row_type": "historical_actual",
                "time_grain": "june_year",
                "period": f"FY{fy}",
                "june_year": fy,
                "value": value,
                "value_unit": "$m nominal ex GST",
            }
            for fy, value in [(2023, 4000.0), (2024, 4200.0), (2025, 4400.0)]
        ]
    )
    derived = _disaggregate_annual_rows_to_quarterly(annual_rows, pd.DataFrame())
    assert len(derived) == 12
    assert set(derived["data_scope"]) == {"quarterly_disaggregated_from_annual"}
    assert set(derived["value_status"]) == {"interpolated"}
    assert set(derived["time_grain"]) == {"quarterly"}
    by_fy = derived.groupby("june_year")["value"].sum()
    assert np.allclose(by_fy.loc[[2023, 2024, 2025]], [4000.0, 4200.0, 4400.0], atol=1e-6)
    assert list(derived[derived["june_year"].eq(2023)]["period"]) == ["2022Q3", "2022Q4", "2023Q1", "2023Q2"]
