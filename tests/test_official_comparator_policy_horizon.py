"""The official comparator's policy horizon is independent of the current model.

The current-model policy replay is bounded by the supported current-model
horizon (H20 / FY2030). The MBU26 official comparator is a different scope: no
behavioural replay, a rate-only counterfactual with official volumes held
fixed, published over its own horizon. Sharing one factor map would let the
current-model cutoff silently truncate the official comparator, which is the
regression these tests exist to prevent.
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
    governed_no_uplift_wedge,
    official_comparator_factor_map,
    official_comparator_policy_factors,
)

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_HORIZON_END_FY = 2050
TOL = 1e-9


@pytest.fixture(scope="module")
def no_uplift() -> pd.DataFrame:
    return official_comparator_policy_factors(ROOT, FED_POLICY_STATE_NO_UPLIFT)


@pytest.fixture(scope="module")
def delayed() -> pd.DataFrame:
    return official_comparator_policy_factors(ROOT, FED_POLICY_STATE_DELAYED_6M)


def test_official_no_uplift_factors_cover_the_full_displayed_horizon(no_uplift) -> None:
    """Gate 3: the official comparator must not stop where the current model does."""
    years = set(int(value) for value in no_uplift["june_year"])
    for fy in range(2027, OFFICIAL_HORIZON_END_FY + 1):
        assert fy in years, f"official no-uplift factor missing for FY{fy}"
    assert max(years) >= OFFICIAL_HORIZON_END_FY


def test_the_official_horizon_extends_past_the_current_model_cutoff(no_uplift) -> None:
    beyond = {int(v) for v in no_uplift["june_year"] if int(v) > LAST_DECISION_GRADE_ANNUAL_FY}
    assert len(beyond) >= 20, "official factors were truncated by the current-model horizon"


def test_the_nominal_wedge_is_derived_not_hard_coded(no_uplift) -> None:
    wedge, wedge_fy, first_fy = governed_no_uplift_wedge(ROOT)
    assert wedge == pytest.approx(0.12, abs=1e-9)
    assert first_fy == 2027
    carried = no_uplift["nominal_wedge_nzd_per_litre"].astype(float)
    assert (carried - wedge).abs().max() <= TOL, "the wedge is not carried forward in nominal terms"
    del wedge_fy


def test_the_wedge_does_not_apply_before_the_uplift_exists(no_uplift) -> None:
    assert int(no_uplift["june_year"].min()) == 2027


def test_official_delayed_policy_differs_only_in_fy2027(delayed) -> None:
    """Gate 2: from FY2028 the delayed path is identical to published."""
    years = sorted(int(value) for value in delayed["june_year"])
    assert years == [2027]
    factor = float(delayed.loc[delayed["june_year"].eq(2027), "factor"].iloc[0])
    assert 0.0 < factor < 1.0
    identity = official_comparator_factor_map(ROOT, FED_POLICY_STATE_DELAYED_6M)
    assert set(identity) == {2027}


def test_official_factors_are_not_derived_from_current_model_chart_rows() -> None:
    """Gate: the two scopes must not share a factor map.

    The current-model map is bounded by the pack; the official map is not.
    """
    pack_rows = pd.read_csv(
        ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "revenue_chart_rows.csv"
    )
    current = fed_uplift_off_factors(ROOT, pack_rows)
    official = official_comparator_factor_map(ROOT, FED_POLICY_STATE_NO_UPLIFT)
    assert max(current) <= LAST_DECISION_GRADE_ANNUAL_FY + 1
    assert max(official) >= OFFICIAL_HORIZON_END_FY
    assert max(official) > max(current)


def test_every_official_factor_row_records_full_provenance(no_uplift, delayed) -> None:
    for frame in (no_uplift, delayed):
        assert list(frame.columns) == list(OFFICIAL_FACTOR_COLUMNS)
        assert frame["scenario_scope"].eq(OFFICIAL_SCOPE).all()
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
