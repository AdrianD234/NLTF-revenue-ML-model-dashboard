"""The official comparator's policy schedule and horizon.

Two independent contracts are pinned here.

**Scope.** The current-model policy replay is bounded by the supported
current-model horizon (H20 / FY2030). The MBU26 official comparator has no
behavioural replay, receives a rate-only counterfactual with official volumes
held fixed, and publishes over its own horizon. Sharing one factor map would
let the current-model cutoff silently truncate the official comparator.

**Wedge shape.** The 12c uplift lands in January 2027, halfway through FY2027,
so the governed annual planned rate for FY2027 carries only about half of it.
Every directly governed June year must use its own source-derived wedge; only
years past the source schedule carry the terminal wedge forward. Applying the
full 12c in FY2027 doubles the intended effect.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.light_fleet_allocation import LAST_DECISION_GRADE_ANNUAL_FY
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    OFFICIAL_FACTOR_COLUMNS,
    OFFICIAL_SCOPE,
    fed_uplift_off_factors,
    governed_no_uplift_wedge_schedule,
    official_comparator_factor_map,
    official_comparator_policy_factors,
)

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_HORIZON_END_FY = 2050
FIRST_UPLIFT_FY = 2027
# The official effective rate is revenue over volume, so it differs from the
# governed schedule rate by source rounding. Two policies that both exclude the
# January 2027 step must agree to within that, not exactly.
SOURCE_ROUNDING_TOL = 5e-4
TOL = 1e-9


@pytest.fixture(scope="module")
def no_uplift() -> pd.DataFrame:
    return official_comparator_policy_factors(ROOT, FED_POLICY_STATE_NO_UPLIFT)


@pytest.fixture(scope="module")
def delayed() -> pd.DataFrame:
    return official_comparator_policy_factors(ROOT, FED_POLICY_STATE_DELAYED_6M)


@pytest.fixture(scope="module")
def wedges() -> tuple[dict[int, float], float, int, int]:
    return governed_no_uplift_wedge_schedule(ROOT)


# ------------------------------------------------------------- wedge shape


def test_pre_uplift_official_factors_are_identity(no_uplift, wedges) -> None:
    """Gate 1: no counterfactual before the uplift exists."""
    wedge_by_fy, _, _, first_uplift_fy = wedges
    assert first_uplift_fy == FIRST_UPLIFT_FY
    for fy in (2025, 2026):
        assert wedge_by_fy[fy] == pytest.approx(0.0, abs=TOL)
    assert int(no_uplift["june_year"].min()) == FIRST_UPLIFT_FY


def test_the_fy2027_direct_source_wedge_is_six_cents(wedges) -> None:
    """Gate 2: FY2027 straddles the January 2027 step, so it carries half."""
    wedge_by_fy, _, _, _ = wedges
    assert wedge_by_fy[2027] == pytest.approx(0.06, abs=1e-9)


def test_the_fy2028_direct_source_wedge_is_twelve_cents(wedges) -> None:
    """Gate 3: the full uplift is inside FY2028 for all four quarters."""
    wedge_by_fy, _, _, _ = wedges
    assert wedge_by_fy[2028] == pytest.approx(0.12, abs=1e-9)


def test_every_directly_governed_year_uses_its_own_source_wedge(no_uplift, wedges) -> None:
    """Gate 4: no year may borrow another year's wedge."""
    wedge_by_fy, _, last_source_fy, _ = wedges
    frame = no_uplift.set_index("june_year")
    for fy, expected in wedge_by_fy.items():
        if fy < FIRST_UPLIFT_FY or fy > last_source_fy:
            continue
        assert float(frame.loc[fy, "nominal_wedge_nzd_per_litre"]) == pytest.approx(
            expected, abs=1e-9
        ), f"FY{fy} used a borrowed wedge"
        assert frame.loc[fy, "wedge_basis"] == "direct_source"


def test_only_years_beyond_the_source_schedule_carry_the_terminal_wedge(no_uplift, wedges) -> None:
    """Gate 5: carrying forward is confined to the unsourced tail."""
    _, terminal_wedge, last_source_fy, _ = wedges
    frame = no_uplift.set_index("june_year")
    carried = frame[frame["wedge_basis"].eq("carried_terminal")]
    assert not carried.empty
    assert int(carried.index.min()) == last_source_fy + 1
    assert (carried["nominal_wedge_nzd_per_litre"] - terminal_wedge).abs().max() <= TOL


def test_the_fy2027_no_uplift_factor_is_not_the_full_wedge(no_uplift) -> None:
    """The specific regression: applying 12c in FY2027 doubles the effect."""
    row = no_uplift.set_index("june_year").loc[2027]
    assert float(row["factor"]) == pytest.approx(0.9210, abs=5e-4)
    assert float(row["factor"]) > 0.90, "FY2027 is carrying the full 12c wedge"


# ------------------------------------------------------------ delayed policy


def test_official_delayed_policy_differs_only_in_fy2027(delayed) -> None:
    """Gates 6 and 7: delayed is identity from FY2028 onward."""
    years = sorted(int(value) for value in delayed["june_year"])
    assert years == [FIRST_UPLIFT_FY]
    factor = float(delayed.loc[delayed["june_year"].eq(2027), "factor"].iloc[0])
    assert 0.0 < factor < 1.0
    assert set(official_comparator_factor_map(ROOT, FED_POLICY_STATE_DELAYED_6M)) == {2027}


def test_fy2027_delayed_and_no_uplift_target_rates_agree(no_uplift, delayed) -> None:
    """Neither policy has the January 2027 step inside FY2027."""
    a = float(no_uplift.set_index("june_year").loc[2027, "target_rate_nzd_per_litre"])
    b = float(delayed.set_index("june_year").loc[2027, "target_rate_nzd_per_litre"])
    assert a == pytest.approx(b, abs=SOURCE_ROUNDING_TOL)


# --------------------------------------------------------------- the horizon


def test_official_no_uplift_factors_cover_the_full_displayed_horizon(no_uplift) -> None:
    years = {int(value) for value in no_uplift["june_year"]}
    for fy in range(FIRST_UPLIFT_FY, OFFICIAL_HORIZON_END_FY + 1):
        assert fy in years, f"official no-uplift factor missing for FY{fy}"
    assert max(years) >= OFFICIAL_HORIZON_END_FY


def test_no_uplift_stays_below_published_across_the_whole_horizon(no_uplift) -> None:
    """Gates 8 and 9: strictly below published, and always positive."""
    assert (no_uplift["target_rate_nzd_per_litre"] > 0).all()
    assert (
        no_uplift["target_rate_nzd_per_litre"] < no_uplift["source_rate_nzd_per_litre"]
    ).all()
    assert (no_uplift["factor"] > 0).all()
    assert (no_uplift["factor"] < 1.0).all()


def test_official_factors_are_not_derived_from_current_model_chart_rows() -> None:
    """The two scopes must not share a factor map."""
    pack_rows = pd.read_csv(
        ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "revenue_chart_rows.csv"
    )
    current = fed_uplift_off_factors(ROOT, pack_rows)
    official = official_comparator_factor_map(ROOT, FED_POLICY_STATE_NO_UPLIFT)
    assert max(current) <= LAST_DECISION_GRADE_ANNUAL_FY + 1
    assert max(official) >= OFFICIAL_HORIZON_END_FY
    assert max(official) > max(current)


def test_the_official_horizon_extends_past_the_current_model_cutoff(no_uplift) -> None:
    beyond = {int(v) for v in no_uplift["june_year"] if int(v) > LAST_DECISION_GRADE_ANNUAL_FY}
    assert len(beyond) >= 20, "official factors were truncated by the current-model horizon"


# ------------------------------------------------------------- provenance


def test_every_official_factor_row_records_full_provenance(no_uplift, delayed) -> None:
    """Gate 10: including whether the wedge is direct or carried."""
    for frame in (no_uplift, delayed):
        assert list(frame.columns) == list(OFFICIAL_FACTOR_COLUMNS)
        assert frame["scenario_scope"].eq(OFFICIAL_SCOPE).all()
        assert frame["wedge_basis"].isin({"direct_source", "carried_terminal"}).all()
        assert frame["source_schedule_fy"].notna().all()
        assert frame["source_file"].str.contains("mbu26_annual_spine").all()
        assert frame["source_sha256"].str.len().eq(64).all()
        assert frame["transformation_basis"].str.len().gt(0).all()
        assert frame["first_supported_fy"].notna().all()
        assert frame["last_supported_fy"].notna().all()


def test_the_official_rate_ratio_reconstructs_the_target_rate(no_uplift) -> None:
    for record in no_uplift.itertuples():
        source = float(record.source_rate_nzd_per_litre)
        target = float(record.target_rate_nzd_per_litre)
        assert float(record.factor) == pytest.approx(target / source, abs=1e-12)
        assert source - target == pytest.approx(float(record.nominal_wedge_nzd_per_litre), abs=1e-12)


def test_official_factors_fail_closed_when_the_spine_is_missing(tmp_path) -> None:
    """A missing official input must raise, never silently return published."""
    empty = tmp_path / "repo"
    (empty / "data" / "revenue_model_source_pack" / "mbu26_annual_spine").mkdir(parents=True)
    with pytest.raises((FileNotFoundError, ValueError)):
        official_comparator_policy_factors(empty, FED_POLICY_STATE_NO_UPLIFT)
