"""Quarterly emission and annual availability are independent contracts.

The defect these tests close: the runtime rebuild reads its quarterly inventory
from the pack it is about to overwrite, so a quarter dropped by one build is
gone from the lineage permanently. An earlier June-year cut removed 2030Q3/H19
and 2030Q4/H20 along with the correctly withheld FY2031 annual, and no
downstream filter could restore them because the rows no longer existed.

FY2031 straddles H19-H22. Its annual result is genuinely unavailable, but two
of its quarters sit inside the supported horizon and must publish. These tests
pin both halves of that: the supported quarters exist, and their existence does
not resurrect the FY2031 annual or any total that depends on Light RUC.

Do not relax these by extending the cutoff or by restoring the annual.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.light_fleet_allocation import (
    EXTENDED_EVIDENCE_MAX_HORIZON,
    LAST_DECISION_GRADE_ANNUAL_FY,
    quarter_horizon,
)
from model_dashboard.revenue_outlook import (
    RAW_AUDIT_BEYOND_DECISION_HORIZON,
    RAW_AUDIT_WITHIN_DECISION_HORIZON,
)

ROOT = Path(__file__).resolve().parents[1]
PACKS = {
    "incumbent": ROOT / "data" / "current_revenue_outlook",
    "ar1": ROOT / "data" / "engine_ar1" / "current_revenue_outlook",
}
CURRENT_ROLES = {"basecase", "comparison"}
# Every annual row that reads Light RUC, directly or through a rollup.
LIGHT_RUC_DEPENDENT_ANNUAL_SERIES = {
    "light_ruc_net_km",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_km",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_km",
    "phev_ruc_net_revenue",
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
    "total_gross_revenue",
    "total_revenue_net_admin",
}


def _pack_ids() -> list[str]:
    return [name for name, path in PACKS.items() if (path / "revenue_chart_rows.csv").exists()]


@pytest.fixture(scope="module", params=_pack_ids())
def chart_rows(request: pytest.FixtureRequest) -> pd.DataFrame:
    return pd.read_csv(PACKS[request.param] / "revenue_chart_rows.csv", low_memory=False)


@pytest.fixture(scope="module", params=_pack_ids())
def pack_dir(request: pytest.FixtureRequest) -> Path:
    return PACKS[request.param]


def _decision_facing_quarters(chart_rows: pd.DataFrame) -> pd.DataFrame:
    return chart_rows[
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("future_forecast")
    ].copy()


def _current_annual(chart_rows: pd.DataFrame) -> pd.DataFrame:
    out = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & chart_rows["scenario_role"].astype(str).isin(CURRENT_ROLES)
    ].copy()
    out["june_year_numeric"] = pd.to_numeric(out["june_year"], errors="coerce")
    return out


@pytest.mark.parametrize(
    ("period", "expected_horizon"),
    [("2030Q3", 19), ("2030Q4", 20)],
)
def test_supported_h19_h20_quarters_publish(
    chart_rows: pd.DataFrame, period: str, expected_horizon: int
) -> None:
    """1 and 2. Both supported FY2031 quarters exist at the stated horizon."""
    assert quarter_horizon(period) == expected_horizon
    quarters = _decision_facing_quarters(chart_rows)
    rows = quarters[quarters["period"].astype(str).eq(period)]
    assert not rows.empty, f"{period} (H{expected_horizon}) is inside the supported horizon but absent"

    # Present for every scenario/series that publishes the adjacent quarter, so
    # a partial restore cannot pass.
    published = {
        (str(row.scenario_name), str(row.series_id))
        for row in quarters[quarters["period"].astype(str).eq("2030Q2")].itertuples(index=False)
    }
    restored = {
        (str(row.scenario_name), str(row.series_id)) for row in rows.itertuples(index=False)
    }
    assert published <= restored, f"{period} missing for {sorted(published - restored)}"

    horizons = rows["horizon"].astype(float)
    assert (horizons == float(expected_horizon)).all()
    assert pd.to_numeric(rows["value"], errors="coerce").notna().all()


@pytest.mark.parametrize("period", ["2031Q1", "2031Q2"])
def test_h21_plus_quarters_are_not_decision_facing(chart_rows: pd.DataFrame, period: str) -> None:
    """3 and 4. H21/H22 stay withheld; restoring H19/H20 must not leak past H20."""
    assert quarter_horizon(period) > EXTENDED_EVIDENCE_MAX_HORIZON
    quarters = _decision_facing_quarters(chart_rows)
    assert quarters[quarters["period"].astype(str).eq(period)].empty


def test_no_decision_facing_quarter_beyond_h20(chart_rows: pd.DataFrame) -> None:
    """The cutoff is a horizon rule, not a hand-listed pair of exceptions."""
    quarters = _decision_facing_quarters(chart_rows)
    horizons = quarters["period"].astype(str).map(quarter_horizon)
    assert int(horizons.max()) == EXTENDED_EVIDENCE_MAX_HORIZON
    assert horizons.min() >= 1


def test_fy2031_annual_light_ruc_is_unavailable(chart_rows: pd.DataFrame) -> None:
    """5. Two supported quarters do not make a publishable June year."""
    annual = _current_annual(chart_rows)
    fy2031 = annual[annual["june_year_numeric"].eq(2031)]
    light = fy2031[fy2031["series_id"].astype(str).eq("light_ruc_net_km")]
    assert light.empty, "FY2031 needs all four quarters; 2031Q1/Q2 are H21/H22"


def test_fy2031_light_ruc_dependent_totals_are_unavailable(chart_rows: pd.DataFrame) -> None:
    """6. No total that reads Light RUC may exist past the annual cutoff."""
    annual = _current_annual(chart_rows)
    beyond = annual[annual["june_year_numeric"].gt(LAST_DECISION_GRADE_ANNUAL_FY)]
    leaked = sorted(
        set(beyond["series_id"].astype(str)) & LIGHT_RUC_DEPENDENT_ANNUAL_SERIES
    )
    assert not leaked, f"Light RUC-dependent annual rows past FY{LAST_DECISION_GRADE_ANNUAL_FY}: {leaked}"
    assert int(annual["june_year_numeric"].max()) == LAST_DECISION_GRADE_ANNUAL_FY


def test_official_comparator_fy2031_remains_available(chart_rows: pd.DataFrame) -> None:
    """7. The current-model cutoff must not touch the official comparator."""
    official = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & chart_rows["scenario_role"].astype(str).eq("official_comparator")
    ].copy()
    years = pd.to_numeric(official["june_year"], errors="coerce")
    fy2031 = official[years.eq(2031)]
    assert not fy2031.empty, "Official FY2031 is source-backed and must publish"
    assert pd.to_numeric(fy2031["value"], errors="coerce").notna().any()
    assert int(years.max()) > LAST_DECISION_GRADE_ANNUAL_FY


def test_raw_audit_rows_exist_but_are_not_decision_facing(pack_dir: Path) -> None:
    """8. Raw evidence keeps its full horizon without becoming publishable.

    This is what stops the Light RUC cutoff destroying standalone PED and Heavy
    RUC model evidence as collateral damage.
    """
    path = pack_dir / "raw_quarterly_forecast_audit.csv"
    assert path.exists(), "raw quarterly replay evidence must survive the H20 cutoff"
    raw = pd.read_csv(path, low_memory=False)
    assert not raw.empty

    assert not raw["decision_facing"].astype(bool).any()
    assert raw["horizon"].astype(float).max() > EXTENDED_EVIDENCE_MAX_HORIZON

    beyond = raw[raw["horizon"].astype(float) > EXTENDED_EVIDENCE_MAX_HORIZON]
    assert not beyond.empty
    assert set(beyond["stream"].astype(str)) >= {"PED", "HEAVY_RUC", "LIGHT_RUC"}
    assert beyond["availability_status"].astype(str).eq(RAW_AUDIT_BEYOND_DECISION_HORIZON).all()
    assert beyond["unavailable_reason"].astype(str).str.len().gt(0).all()

    # The withheld reason must be about the horizon, not the Light RUC bridge:
    # PED and Heavy RUC are withheld here for their own horizon, not Light's.
    assert not beyond["unavailable_reason"].astype(str).str.contains("light_ruc").any()

    within = raw[raw["horizon"].astype(float) <= EXTENDED_EVIDENCE_MAX_HORIZON]
    assert within["availability_status"].astype(str).eq(RAW_AUDIT_WITHIN_DECISION_HORIZON).all()

    # The audit frame is a sibling file, never a chart row: nothing here can be
    # plotted, annualized or summed into a total.
    chart_rows = pd.read_csv(pack_dir / "revenue_chart_rows.csv", low_memory=False)
    assert "decision_facing" not in chart_rows.columns
    quarters = _decision_facing_quarters(chart_rows)
    assert quarters["period"].astype(str).map(quarter_horizon).max() == EXTENDED_EVIDENCE_MAX_HORIZON


def test_restored_quarters_are_traceable_to_their_source(pack_dir: Path) -> None:
    """A restored value must be attributable, not silently materialized."""
    path = pack_dir / "quarterly_reconstitution_audit.csv"
    if not path.exists():
        pytest.skip("no quarters needed restoring in this pack build")
    audit = pd.read_csv(path, low_memory=False)
    if audit.empty:
        return
    horizons = audit["horizon"].astype(float)
    assert horizons.between(1, EXTENDED_EVIDENCE_MAX_HORIZON).all()
    assert audit["source"].astype(str).str.len().gt(0).all()
    assert audit["action"].astype(str).eq("restored_from_committed_scenario_input_replay").all()
