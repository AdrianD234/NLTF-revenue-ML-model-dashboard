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
from model_dashboard.series_inventory_contract import LAST_POST_MODEL_FY
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    FED_POLICY_STATE_PUBLISHED,
    OFFICIAL_FACTOR_COLUMNS,
    OFFICIAL_POLICY_AUDIT_COLUMNS,
    OFFICIAL_SCOPE,
    official_comparator_policy_audit_frame,
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
    # The current map now spans the post-model window too (a rate change is
    # permanent, so the lever must reach FY2050). The separation this test
    # exists to prove is unchanged and is asserted below: the official
    # comparator keeps its OWN longer horizon and the two maps are distinct.
    assert max(current) <= LAST_POST_MODEL_FY
    assert max(official) >= OFFICIAL_HORIZON_END_FY
    assert max(official) > max(current)
    assert current != official


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


# ---------------------------------------------------------------------------
# Runtime wiring: the helper is reached by the app, and the two scopes never
# touch the same row.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pack_chart_rows() -> pd.DataFrame:
    return pd.read_csv(
        ROOT / "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv",
        low_memory=False,
    )


def _annual(rows: pd.DataFrame, role: str, fy: int, series: str = "total_nltf_net_revenue") -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])


def test_current_model_helpers_refuse_official_rows() -> None:
    """No row may be processed by both helpers."""
    from model_dashboard.rate_paths import (
        apply_fed_uplift_delay_to_chart_rows,
        apply_fed_uplift_off_to_chart_rows,
    )

    for helper in (apply_fed_uplift_off_to_chart_rows, apply_fed_uplift_delay_to_chart_rows):
        with pytest.raises(ValueError, match="current-model helper"):
            helper(pd.DataFrame(), {2027: 0.9}, scenario_roles={OFFICIAL_SCOPE})
        with pytest.raises(ValueError, match="current-model helper"):
            helper(pd.DataFrame(), {2027: 0.9}, scenario_roles={"basecase", OFFICIAL_SCOPE})


def test_app_routes_the_official_scope_to_the_official_helper(pack_chart_rows) -> None:
    """The helper is wired into the real overlay path, not merely importable."""
    import app

    assert app._MBU26_FED_UPLIFT_ROLES == (OFFICIAL_SCOPE,)
    assert OFFICIAL_SCOPE not in app._CURRENT_FED_UPLIFT_ROLES

    for ui_label, state in app._OFFICIAL_POLICY_STATE_BY_UI_LABEL.items():
        rows, _, _, audit = app._apply_scenario_overlays(
            pack_chart_rows.copy(),
            pd.DataFrame(),
            None,
            None,
            {"mbu26_ruc_class_revenue": {}},
            adjust_ped=False,
            fed_policy_scopes=((ui_label, app._MBU26_FED_UPLIFT_ROLES),),
        )
        published = _annual(pack_chart_rows, OFFICIAL_SCOPE, 2027)
        if state == "published":
            assert _annual(rows, OFFICIAL_SCOPE, 2027) == pytest.approx(published, abs=TOL)
            continue

        # The policy actually reached the official rows.
        assert _annual(rows, OFFICIAL_SCOPE, 2027) != pytest.approx(published, abs=TOL)
        assert not audit.empty
        assert set(audit["scenario_role"].astype(str)) == {OFFICIAL_SCOPE}

        # ...and left every current-model row alone.
        for fy in (2027, LAST_DECISION_GRADE_ANNUAL_FY):
            assert _annual(rows, "basecase", fy) == pytest.approx(
                _annual(pack_chart_rows, "basecase", fy), abs=TOL
            )


def test_official_policy_reaches_beyond_the_current_model_horizon(pack_chart_rows) -> None:
    """The whole point of the split: FY2031+ official rows still get repriced."""
    import app

    rows, _, _, _ = app._apply_scenario_overlays(
        pack_chart_rows.copy(),
        pd.DataFrame(),
        None,
        None,
        {"mbu26_ruc_class_revenue": {}},
        adjust_ped=False,
        fed_policy_scopes=(("off", app._MBU26_FED_UPLIFT_ROLES),),
    )
    for fy in (2031, 2040, 2050):
        assert _annual(rows, OFFICIAL_SCOPE, fy) != pytest.approx(
            _annual(pack_chart_rows, OFFICIAL_SCOPE, fy), abs=TOL
        )


def test_the_two_policy_selectors_stay_independent(pack_chart_rows) -> None:
    """Choosing a current policy must not move official rows, and vice versa."""
    import app

    current_only, _, _, _ = app._apply_scenario_overlays(
        pack_chart_rows.copy(),
        pd.DataFrame(),
        None,
        None,
        {
            "off": {2027: 0.95, 2030: 0.95},
            "mbu26_ruc_class_revenue": {},
        },
        adjust_ped=False,
        fed_policy_scopes=(("off", app._CURRENT_FED_UPLIFT_ROLES),),
    )
    for fy in (2027, 2031, 2050):
        assert _annual(current_only, OFFICIAL_SCOPE, fy) == pytest.approx(
            _annual(pack_chart_rows, OFFICIAL_SCOPE, fy), abs=TOL
        )
    assert _annual(current_only, "basecase", 2030) != pytest.approx(
        _annual(pack_chart_rows, "basecase", 2030), abs=TOL
    )


# ---------------------------------------------------------------------------
# Job 4: the audit must evidence every affected component, not four rows.
# ---------------------------------------------------------------------------

CLOSURE_TOL = 1e-6
_RUC_CLASS_LEAVES = {
    "conventional_light_ruc_revenue",
    "light_bev_revenue",
    "phev_revenue",
    "heavy_ruc_revenue",
    "heavy_bev_revenue",
}
_REQUIRED_AUDIT_COMPONENTS = _RUC_CLASS_LEAVES | {
    "gross_ped_revenue",
    "net_fed_revenue",
    "total_ruc_net_revenue",
    "total_nltf_net_revenue",
}


@pytest.fixture(scope="module")
def no_uplift_audit() -> pd.DataFrame:
    return official_comparator_policy_audit_frame(ROOT, FED_POLICY_STATE_NO_UPLIFT)


@pytest.fixture(scope="module")
def delayed_audit() -> pd.DataFrame:
    return official_comparator_policy_audit_frame(ROOT, FED_POLICY_STATE_DELAYED_6M)


def test_audit_covers_every_affected_component(no_uplift_audit, delayed_audit) -> None:
    """Including Heavy BEV, which is never a visible chart row but moves totals."""
    for frame in (no_uplift_audit, delayed_audit):
        assert _REQUIRED_AUDIT_COMPONENTS <= set(frame["component"].astype(str))
        assert list(frame.columns) == list(OFFICIAL_POLICY_AUDIT_COLUMNS)
    assert "heavy_bev_revenue" in set(no_uplift_audit["component"].astype(str))


def test_every_audit_row_carries_its_full_derivation(no_uplift_audit) -> None:
    for column in (
        "original_value",
        "source_effective_ped_rate",
        "nominal_wedge_nzd_per_litre",
        "target_ped_rate",
        "selected_rate_factor",
        "adjusted_value",
        "delta",
    ):
        assert no_uplift_audit[column].notna().all()
    assert no_uplift_audit["wedge_basis"].isin({"direct_source", "carried_terminal"}).all()
    assert no_uplift_audit["source_sha256"].str.len().eq(64).all()
    assert no_uplift_audit["transformation_basis"].str.len().gt(0).all()
    assert no_uplift_audit["fixed_volume_status"].str.len().gt(0).all()


def test_published_state_leaves_mbu26_untouched() -> None:
    assert official_comparator_policy_audit_frame(ROOT, FED_POLICY_STATE_PUBLISHED).empty


def test_delayed_touches_fy2027_only(delayed_audit) -> None:
    assert sorted(set(delayed_audit["fy"].astype(int))) == [2027]


def test_no_uplift_covers_every_official_fy_without_gaps(no_uplift_audit) -> None:
    years = sorted(set(no_uplift_audit["fy"].astype(int)))
    assert years == list(range(years[0], years[-1] + 1))
    assert years[-1] > LAST_DECISION_GRADE_ANNUAL_FY


def test_administration_and_refunds_never_move(no_uplift_audit, delayed_audit) -> None:
    fixed_ids = {"ruc_admin_revenue", "ruc_refunds", "fed_refunds", "mvr_admin_revenue", "mvr_refunds"}
    for frame in (no_uplift_audit, delayed_audit):
        fixed = frame[frame["component"].isin(fixed_ids)]
        assert not fixed.empty
        assert float(fixed["delta"].abs().max()) == 0.0
        assert fixed["component_kind"].eq("fixed").all()


def test_totals_close_within_tolerance(no_uplift_audit, delayed_audit) -> None:
    """Policy arithmetic must close exactly, net of the source's own residual."""
    for frame in (no_uplift_audit, delayed_audit):
        assert float(frame["closure_residual"].abs().max()) <= CLOSURE_TOL


def test_the_published_source_residual_is_reported_not_corrected(no_uplift_audit) -> None:
    """FY2027 Total RUC is inconsistent in the published spine by about 0.63.

    Published MBU26 must stay unchanged, so the counterfactual reports that
    residual rather than quietly rebasing it away. If this ever reaches zero
    because the source was 'fixed', that is a change to published MBU26 and
    must be reviewed, not absorbed.
    """
    fy2027 = no_uplift_audit[
        no_uplift_audit["fy"].eq(2027) & no_uplift_audit["component"].eq("total_ruc_net_revenue")
    ]
    assert not fy2027.empty
    residual = float(fy2027["published_source_residual"].iloc[0])
    assert abs(residual) == pytest.approx(0.6270120265, abs=1e-6)
    # The reported value still preserves the published trace plus the delta.
    assert float(fy2027["closure_residual"].iloc[0]) == pytest.approx(0.0, abs=CLOSURE_TOL)


def test_the_audit_wedge_matches_the_legislated_shape(no_uplift_audit) -> None:
    for fy, expected in ((2027, 0.06), (2028, 0.12)):
        rows = no_uplift_audit[no_uplift_audit["fy"].eq(fy)]
        assert not rows.empty
        assert float(rows["nominal_wedge_nzd_per_litre"].iloc[0]) == pytest.approx(expected, abs=2e-3)
    terminal = no_uplift_audit[no_uplift_audit["wedge_basis"].eq("carried_terminal")]
    assert not terminal.empty
    assert float(terminal["nominal_wedge_nzd_per_litre"].max()) == pytest.approx(0.12, abs=2e-3)
