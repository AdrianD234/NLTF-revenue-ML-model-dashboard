"""The per-stream actuals vintage must be visible, and honest, on the page.

The 2026Q1 refresh gave streams different accepted cutoffs: exact Light and
Heavy RUC actuals for 2026Q1 beside a PED quarter that is still a forecast
(its MBU26 bridge is provisional). A pack that carries that seam but never
surfaces it would leave a reader unable to tell which quarters are observed —
these gates keep the exposure wired up, in both governed packs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app import stream_vintage_caption_text

ROOT = Path(__file__).resolve().parents[1]
PACK_DIRS = {
    "ensemble": ROOT / "data" / "current_revenue_outlook",
    "ar1": ROOT / "data" / "engine_ar1" / "current_revenue_outlook",
}
ENGINES = sorted(PACK_DIRS)


def _manifest(engine: str) -> dict:
    return json.loads((PACK_DIRS[engine] / "manifest.json").read_text(encoding="utf-8"))


def _period_rule(engine: str) -> dict:
    rule = _manifest(engine).get("period_rule")
    assert isinstance(rule, dict), f"{engine}: manifest has no period_rule"
    return rule


# ------------------------------------------------------- pack-side exposure


@pytest.mark.parametrize("engine", ENGINES)
def test_pack_publishes_the_stream_vintage_table(engine: str) -> None:
    for suffix in ("csv", "parquet"):
        path = PACK_DIRS[engine] / f"stream_vintage_status.{suffix}"
        assert path.exists(), f"{engine}: stream_vintage_status.{suffix} is missing"

    frame = pd.read_parquet(PACK_DIRS[engine] / "stream_vintage_status.parquet")
    assert set(frame["stream"]) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    required = {
        "stream",
        "input_history_vintage",
        "latest_accepted_exact_actual",
        "first_forecast_quarter",
        "observation_status",
        "provisional_seed",
        "source_lineage",
        "fy2026_construction",
    }
    assert required.issubset(frame.columns)
    # Lineage must point at the canonical history, never at the source Excel.
    lineage = frame["source_lineage"].astype(str)
    assert lineage.str.contains("data/model_input_history").all()
    assert not lineage.str.contains(".xlsx", regex=False).any()

    by_stream = frame.set_index("stream")
    assert by_stream.loc["LIGHT_RUC", "latest_accepted_exact_actual"] == "2026Q1"
    assert by_stream.loc["HEAVY_RUC", "latest_accepted_exact_actual"] == "2026Q1"
    assert by_stream.loc["LIGHT_RUC", "first_forecast_quarter"] == "2026Q2"
    assert by_stream.loc["HEAVY_RUC", "first_forecast_quarter"] == "2026Q2"
    # PED's exact cutoff stays behind: its 2026Q1 target is a provisional
    # bridge, so 2026Q1 remains a forecast under the production candidate.
    assert by_stream.loc["PED", "latest_accepted_exact_actual"] == "2025Q4"
    assert by_stream.loc["PED", "first_forecast_quarter"] == "2026Q1"


@pytest.mark.parametrize("engine", ENGINES)
def test_manifest_period_rule_carries_the_per_stream_seam(engine: str) -> None:
    rule = _period_rule(engine)
    assert rule["input_history_vintage"] == "2026Q1"
    vintages = rule["stream_vintages"]
    assert vintages["LIGHT_RUC"]["first_forecast_quarter"] == "2026Q2"
    assert vintages["HEAVY_RUC"]["first_forecast_quarter"] == "2026Q2"
    assert vintages["PED"]["first_forecast_quarter"] == "2026Q1"
    assert vintages["PED"]["latest_accepted_exact_actual"] == "2025Q4"
    # The provisional note belongs to PED alone.
    assert "provisional_annual_bridge" in vintages["PED"]["provisional_seed"]
    assert not vintages["LIGHT_RUC"]["provisional_seed"]
    assert not vintages["HEAVY_RUC"]["provisional_seed"]
    # The FY2026 construction note must describe a mixed year per stream.
    assert "2026Q2" in rule["fy2026_nowcast"] and "2025Q4" in rule["fy2026_nowcast"]


# ------------------------------------------------------- page-side exposure


@pytest.mark.parametrize("engine", ENGINES)
def test_page_caption_states_each_streams_seam(engine: str) -> None:
    caption = stream_vintage_caption_text(_period_rule(engine))
    assert "Input-history vintage 2026Q1" in caption
    assert "Light RUC** actual to 2026Q1, forecast from 2026Q2" in caption
    assert "Heavy RUC** actual to 2026Q1, forecast from 2026Q2" in caption
    assert "PED** actual to 2025Q4, forecast from 2026Q1" in caption
    # The provisional bridge is named as provisional, and never as an actual.
    assert "not an observed actual" in caption
    assert "PED** actual to 2026Q1" not in caption


def test_caption_is_silent_for_a_pack_without_the_seam() -> None:
    """An older pack must render exactly as it did before this change."""
    assert stream_vintage_caption_text({}) == ""
    assert stream_vintage_caption_text({"runtime_cutoff_fy": 2030}) == ""
    assert stream_vintage_caption_text({"stream_vintages": {}}) == ""


def test_caption_omits_a_stream_with_incomplete_metadata() -> None:
    caption = stream_vintage_caption_text(
        {
            "input_history_vintage": "2026Q1",
            "stream_vintages": {
                "LIGHT_RUC": {
                    "latest_accepted_exact_actual": "2026Q1",
                    "first_forecast_quarter": "2026Q2",
                    "provisional_seed": "",
                },
                "HEAVY_RUC": {"latest_accepted_exact_actual": "", "first_forecast_quarter": ""},
            },
        }
    )
    assert "Light RUC" in caption
    assert "Heavy RUC" not in caption


# ------------------------------------- FY2026 mixed-year labels on the page


@pytest.mark.parametrize("engine", ENGINES)
def test_fy2026_quarter_mix_labels_match_the_per_stream_seam(engine: str) -> None:
    """FY2026 is a mixed year, and each stream must label its own mix."""
    future = pd.read_parquet(PACK_DIRS[engine] / "future_revenue_forecasts.parquet")
    fy2026 = future[future["period"].astype(str).eq("FY2026")]
    assert not fy2026.empty

    by_stream = fy2026.drop_duplicates("stream").set_index("stream")
    # Light/Heavy consumed the accepted 2026Q1 actual: 3 actual + 1 forecast.
    for stream in ("light_ruc_net_revenue", "heavy_ruc_net_revenue"):
        assert by_stream.loc[stream, "actual_quarters"] == "2025Q3; 2025Q4; 2026Q1"
        assert by_stream.loc[stream, "forecast_quarters"] == "2026Q2"
        assert "3 actual + 1 forecast" in str(by_stream.loc[stream, "value_status"])
    # PED keeps 2 actual + 2 forecast: 2026Q1 is still a forecast for it.
    assert by_stream.loc["gross_ped_revenue", "actual_quarters"] == "2025Q3; 2025Q4"
    assert by_stream.loc["gross_ped_revenue", "forecast_quarters"] == "2026Q1; 2026Q2"
    assert "2 actual + 2 forecast" in str(by_stream.loc["gross_ped_revenue", "value_status"])
    # Every FY2026 row is flagged as a nowcast, never as a completed actual.
    assert fy2026["nowcast_flag"].astype(bool).all()


@pytest.mark.parametrize("engine", ENGINES)
def test_no_quarterly_forecast_row_survives_at_an_accepted_actual(engine: str) -> None:
    """The seam must not leave a stale forecast row where history now exists."""
    chart = pd.read_parquet(PACK_DIRS[engine] / "revenue_chart_rows.parquet")
    quarterly = chart[chart["time_grain"].astype(str).eq("quarterly")]
    for series in ("light_ruc_net_km", "heavy_ruc_net_km"):
        rows = quarterly[quarterly["series_id"].astype(str).eq(series)]
        forecasts = rows[rows["row_type"].astype(str).eq("future_forecast")]
        actuals = rows[rows["row_type"].astype(str).eq("historical_actual")]
        assert "2026Q1" in set(actuals["period"].astype(str)), series
        assert "2026Q1" not in set(forecasts["period"].astype(str)), series
    # PED is the mirror image: 2026Q1 is a forecast, not an actual.
    ped = quarterly[quarterly["series_id"].astype(str).eq("ped_vkt_per_capita")]
    ped_actuals = set(ped[ped["row_type"].astype(str).eq("historical_actual")]["period"].astype(str))
    assert "2026Q1" not in ped_actuals
    assert "2025Q4" in ped_actuals
