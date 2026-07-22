from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import (
    _denton_quarterly_split,
    _disaggregate_annual_rows_to_quarterly,
    _filter_series_rows_with_fallback,
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


def test_fed_policy_delta_is_allocated_only_to_affected_quarters() -> None:
    annual = pd.DataFrame(
        [
            {
                "trace_name": "Current finalist Base case",
                "scenario_name": "current_basecase",
                "fed_path": "Current planned path",
                "series_id": "gross_ped_revenue",
                "series_label": "PED revenue",
                "stream": "gross_ped_revenue",
                "stream_label": "PED revenue",
                "row_type": "future_forecast",
                "time_grain": "june_year",
                "period": "FY2027",
                "june_year": 2027,
                "value": 380.0,
                "_fed_baseline_value": 400.0,
                "_fed_annual_delta": -20.0,
                "_fed_policy": "delayed_6m",
                "_fed_affected_quarters": "2027Q1;2027Q2",
                "value_unit": "$m nominal ex GST",
            }
        ]
    )
    derived = _disaggregate_annual_rows_to_quarterly(annual, pd.DataFrame()).set_index("period")
    assert derived.loc["2026Q3", "value"] == pytest.approx(100.0)
    assert derived.loc["2026Q4", "value"] == pytest.approx(100.0)
    assert derived.loc["2027Q1", "value"] == pytest.approx(90.0)
    assert derived.loc["2027Q2", "value"] == pytest.approx(90.0)
    assert derived["value"].sum() == pytest.approx(380.0)
    assert set(derived["value_status"]) == {"interpolated_fed_policy"}


def test_quarterly_fallback_fills_mbu_trace_when_current_native_rows_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = pd.read_parquet(root / "data/current_revenue_outlook/revenue_chart_rows.parquet")
    selected, used_fallback = _filter_series_rows_with_fallback(
        rows,
        "Light RUC net km",
        "quarterly",
        "Current planned path",
        ("Current finalist Base case", "MBU26 official"),
    )
    assert used_fallback
    assert set(selected["trace_name"].astype(str)) == {
        "Current finalist Base case",
        "MBU26 official",
    }
    native_base = selected[selected["trace_name"].astype(str).eq("Current finalist Base case")]
    derived_mbu = selected[selected["trace_name"].astype(str).eq("MBU26 official")]
    assert not native_base.empty and not derived_mbu.empty
    assert set(native_base["data_scope"].astype(str)) == {"quarterly_current_finalist_input"}
    assert set(derived_mbu["data_scope"].astype(str)) == {
        "quarterly_disaggregated_from_annual",
        "quarterly_disaggregated_from_annual_hybrid_actual_handover",
    }
    assert set(derived_mbu["value_status"].astype(str)) == {
        "interpolated",
        "interpolated_hybrid_actual_handover",
    }
    actual = rows[
        rows["series_id"].astype(str).eq("light_ruc_net_km")
        & rows["time_grain"].astype(str).eq("quarterly")
        & rows["row_type"].astype(str).eq("historical_actual")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2026)
    ]
    assert set(actual["period"].astype(str)) == {"2025Q3", "2025Q4"}
    assert not derived_mbu["period"].astype(str).isin(actual["period"].astype(str)).any()
    for fy, group in derived_mbu.groupby(pd.to_numeric(derived_mbu["june_year"], errors="coerce")):
        expected = set(_june_year_quarters(int(fy)))
        if int(fy) == 2026:
            expected -= set(actual["period"].astype(str))
        assert set(group["period"].astype(str)) == expected

    mbu_fy2026 = rows[
        rows["scenario_name"].astype(str).eq("mbu26_official")
        & rows["series_id"].astype(str).eq("light_ruc_net_km")
        & rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2026)
    ]
    derived_fy2026 = derived_mbu[pd.to_numeric(derived_mbu["june_year"], errors="coerce").eq(2026)]
    hybrid_total_million_km = (
        pd.to_numeric(actual["value"], errors="coerce").sum() / 1_000_000.0
        + pd.to_numeric(derived_fy2026["value"], errors="coerce").sum()
    )
    assert hybrid_total_million_km == pytest.approx(float(mbu_fy2026.iloc[0]["value"]), abs=1e-9)
