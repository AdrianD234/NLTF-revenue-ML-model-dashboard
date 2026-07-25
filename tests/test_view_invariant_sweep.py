"""Permutation invariant sweep over the Revenue Outlook view pipeline.

Rather than eyeballing individual charts, this sweep walks the grid of
(series x time grain x sensitivity axis) under the default uptake basis and
asserts structural invariants that must hold in EVERY configuration:

1. actual immutability   - overlays never change historical actual values
2. forecast handover     - forecast rows never appear inside the actuals era
3. continuity            - no trace jumps more than CONTINUITY_FACTOR between
                           consecutive forecast quarters (catches annual
                           values leaking into quarterly rows, Denton blowups,
                           unit mix-ups)
4. sensitivity footprint - a single-axis sensitivity may only move the series
                           its config declares (freight -> heavy + RUC/NLTF
                           rollups, PT -> light + rollups, efficiency -> PED
                           family + FED/NLTF rollups)
5. scenario ordering     - high-population activity never crosses below base
                           case at the end of the horizon

Each invariant failure reports the exact (series, grain, sensitivity) cell,
so a regression pinpoints itself instead of surfacing as a odd chart shape.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

ROOT = Path(__file__).resolve().parents[1]
FED_PATH = "Current planned path"
CONTINUITY_FACTOR = 1.8  # max allowed consecutive-quarter ratio in forecasts
UPTAKE_KEY = (app.DEFAULT_EV_UPTAKE_MODE, ())

# series a single-axis sensitivity is allowed to move (footprint contract)
RUC_ROLLUPS = {
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_gross_revenue",
    "total_revenue_net_admin",
    "total_nltf_net_revenue",
}
FED_ROLLUPS = {
    "gross_fed_revenue",
    "net_fed_revenue",
    "total_fed_ruc_net_revenue",
    "total_gross_revenue",
    "total_revenue_net_admin",
    "total_nltf_net_revenue",
}
SENSITIVITY_FOOTPRINT = {
    "fleet_med": {"ped_volume", "gross_ped_revenue"} | FED_ROLLUPS,
    "pt_med": {
        "ped_vkt_per_capita",
        "light_petrol_vkt",
        "ped_volume",
        "gross_ped_revenue",
        "light_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
    }
    | RUC_ROLLUPS
    | FED_ROLLUPS,
    "freight_med": {"heavy_ruc_net_km", "heavy_ruc_net_revenue"} | RUC_ROLLUPS,
}
SENSITIVITY_KEYS = {
    "off": app.selected_sensitivity_key("Off", "Off", "Off"),
    "fleet_med": app.selected_sensitivity_key("Med", "Off", "Off"),
    "pt_med": app.selected_sensitivity_key("Off", "Med", "Off"),
    "freight_med": app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Med"),
}


@pytest.fixture(
    scope="module",
    params=[
        pytest.param(Path("data") / "current_revenue_outlook", id="ensemble"),
        pytest.param(Path("data") / "engine_ar1" / "current_revenue_outlook", id="ar1"),
    ],
)
def sweep_context(request):
    # Every structural invariant must hold on BOTH engines' runtime packs.
    pack_dir = ROOT / request.param
    pack = load_revenue_outlook_pack(pack_dir, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, ROOT)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    selectors = app.cached_revenue_outlook_selectors(signature, pack)
    series_labels = list(selectors["stream_options"])
    views: dict[tuple[str, str, str], pd.DataFrame] = {}
    for series in series_labels:
        for grain in ("june_year", "quarterly"):
            for sens_name, sens_key in SENSITIVITY_KEYS.items():
                view = app.cached_revenue_outlook_view(
                    signature, series, grain, FED_PATH, traces, sens_key,
                    PED_BRIDGE_DEFAULT_MODE, UPTAKE_KEY, pack,
                )
                rows = view["filtered_rows"]
                if rows is None or rows.empty:
                    frame = pd.DataFrame(columns=["trace_name", "period", "value", "row_type", "series_id"])
                else:
                    frame = rows[["trace_name", "period", "value", "row_type", "series_id"]].copy()
                    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
                    frame["period"] = frame["period"].astype(str)
                    frame = frame.sort_values(["trace_name", "period"], kind="stable").reset_index(drop=True)
                views[(series, grain, sens_name)] = frame
    return {"series_labels": series_labels, "views": views}


def _actual_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["row_type"].astype(str).eq("historical_actual")].reset_index(drop=True)


def _forecast_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[~frame["row_type"].astype(str).eq("historical_actual")].reset_index(drop=True)


def test_actuals_are_immutable_under_every_sensitivity(sweep_context) -> None:
    failures = []
    for series in sweep_context["series_labels"]:
        for grain in ("june_year", "quarterly"):
            base = _actual_rows(sweep_context["views"][(series, grain, "off")])
            for sens_name in ("fleet_med", "pt_med", "freight_med"):
                other = _actual_rows(sweep_context["views"][(series, grain, sens_name)])
                if len(base) != len(other) or not np.allclose(
                    base["value"].to_numpy(dtype=float),
                    other["value"].to_numpy(dtype=float),
                    rtol=0,
                    atol=1e-9,
                    equal_nan=True,
                ):
                    failures.append((series, grain, sens_name))
    assert not failures, f"actual rows changed under sensitivities: {failures}"


def test_no_forecast_rows_inside_the_actuals_era(sweep_context) -> None:
    failures = []
    for (series, grain, sens_name), frame in sweep_context["views"].items():
        actual = _actual_rows(frame)
        forecast = _forecast_rows(frame)
        if actual.empty or forecast.empty:
            continue
        last_actual = actual["period"].max()
        overlap = forecast[forecast["period"] <= last_actual]
        # comparator traces may legitimately span history on the annual grain
        if grain == "quarterly" and not overlap.empty:
            failures.append((series, grain, sens_name, sorted(overlap["period"].unique())[:4]))
    assert not failures, f"forecast rows inside actuals era: {failures}"


def test_forecast_traces_are_continuous_quarter_to_quarter(sweep_context) -> None:
    failures = []
    for (series, grain, sens_name), frame in sweep_context["views"].items():
        if grain != "quarterly":
            continue
        for trace_name, group in _forecast_rows(frame).groupby("trace_name"):
            values = group.sort_values("period")["value"].to_numpy(dtype=float)
            values = values[np.isfinite(values)]
            positive = values[values > 0]
            if len(positive) < 2 or len(positive) != len(values):
                continue
            ratios = positive[1:] / positive[:-1]
            worst = float(np.max(np.maximum(ratios, 1.0 / ratios)))
            if worst > CONTINUITY_FACTOR:
                failures.append((series, sens_name, str(trace_name), round(worst, 2)))
    assert not failures, f"discontinuous forecast traces (worst consecutive-quarter ratio): {failures}"


def test_single_axis_sensitivities_only_move_their_declared_series(sweep_context) -> None:
    failures = []
    for series in sweep_context["series_labels"]:
        for grain in ("june_year", "quarterly"):
            base = sweep_context["views"][(series, grain, "off")]
            for sens_name, allowed in SENSITIVITY_FOOTPRINT.items():
                other = sweep_context["views"][(series, grain, sens_name)]
                series_ids = set(base["series_id"].astype(str)) | set(other["series_id"].astype(str))
                if series_ids & allowed:
                    continue
                same_shape = len(base) == len(other)
                if same_shape and np.allclose(
                    base["value"].to_numpy(dtype=float),
                    other["value"].to_numpy(dtype=float),
                    rtol=1e-12,
                    atol=1e-9,
                    equal_nan=True,
                ):
                    continue
                failures.append((series, grain, sens_name))
    assert not failures, f"sensitivity moved series outside its declared footprint: {failures}"


def test_high_population_never_crosses_below_base_at_horizon_end(sweep_context) -> None:
    failures = []
    for series in ["Light RUC net km", "Heavy RUC net km", "PED volume"]:
        if series not in sweep_context["series_labels"]:
            continue
        for sens_name in SENSITIVITY_KEYS:
            frame = sweep_context["views"][(series, "june_year", sens_name)]
            forecast = _forecast_rows(frame)
            base = forecast[forecast["trace_name"].astype(str).eq("Current finalist Base case")]
            high = forecast[forecast["trace_name"].astype(str).str.contains("High population")]
            if base.empty or high.empty:
                continue
            last = base["period"].max()
            base_value = float(pd.to_numeric(base[base["period"].eq(last)]["value"], errors="coerce").iloc[0])
            high_sel = high[high["period"].eq(last)]
            if high_sel.empty:
                continue
            high_value = float(pd.to_numeric(high_sel["value"], errors="coerce").iloc[0])
            if high_value < base_value * (1 - 1e-9):
                failures.append((series, sens_name, round(base_value, 1), round(high_value, 1)))
    assert not failures, f"high-population crossed below base case: {failures}"
