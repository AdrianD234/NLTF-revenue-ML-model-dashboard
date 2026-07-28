"""The default composition stage must be neutral, exact, and Light-only.

Two defects motivated these gates, both of the same class: the decision-facing
default applied a fitted approximation where a governed source exists.

**Light.** "MoT VFM base" resolved to a logistic curve fitted to the vendored
VFM table within ~1.5pp. That moved conventional Light RUC off its post-macro
anchor by -134 to +110 million km at the DEFAULT setting, so the displayed Base
forecast was the corrected model plus an unrequested composition sensitivity.

**Heavy.** The Heavy BEV split ran unconditionally inside the light-fleet
overlay, so choosing any light uptake basis reclassified Heavy RUC kilometres
against the settled ``HEAVY_RUC: not_reclassified`` contract.

The gates are stated against the POST-MACRO anchor, not the pack. Treasury
macro is a legitimate upstream transformation, and requiring equality with the
pre-macro pack would wrongly forbid it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("DASHBOARD_ENGINE_DEFAULT", "ar1")

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import (  # noqa: E402
    DEFAULT_EV_UPTAKE_MODE,
    EXACT_VFM_UPTAKE_BASES,
    PARAMETRIC_VFM_BASE_FIT_OPTION,
    exact_vfm_share_curves,
    lever_share_curves,
)
from model_dashboard.fuel_price_scenario import apply_treasury_macro_to_chart_rows  # noqa: E402
from model_dashboard.light_fleet_allocation import composition_shares  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
FYS = (2026, 2027, 2028, 2030)
ROLES = ("basecase", "comparison")
TOL = 1e-9
SIGNATURE: tuple[tuple[str, int, int], ...] = ()
LIGHT_CLASSES = ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")


@pytest.fixture(scope="module")
def pack():
    return load_revenue_outlook_pack(PACK_DIR, repo_root=ROOT)


@pytest.fixture(scope="module")
def post_macro(pack) -> pd.DataFrame:
    """S1: after Treasury macro replay, before any composition overlay."""
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    _bridge, frames, _fast = app.cached_sensitivity_stage_frames(
        SIGNATURE, PED_BRIDGE_DEFAULT_MODE, sensitivity_key, pack
    )
    macro_replay, error = app._safe_treasury_baseline_macro_replay(SIGNATURE, pack)
    fuel_replay, _ = app._safe_fuel_price_scenario_replay(SIGNATURE, pack)
    if fuel_replay is not None and not fuel_replay.policy_pair_factors.empty:
        macro_replay = fuel_replay
    assert macro_replay is not None, f"Treasury macro replay unavailable ({error})"
    rows, _audit = apply_treasury_macro_to_chart_rows(frames["chart_rows"], macro_replay)
    return rows


def _key(mode: str, *, heavy: bool = False, policy: str | None = None) -> tuple:
    return (
        mode,
        (),
        (),
        policy or app.FED_POLICY_PUBLISHED,
        app.FED_POLICY_PUBLISHED,
        False,
        heavy,
    )


def _compose(rows: pd.DataFrame, pack, key: tuple) -> pd.DataFrame:
    out, *_ = app._apply_scenario_overlays(
        rows.copy(),
        app._pack_table(pack, "ev_phev_ped_light_drift_assumptions"),
        app._resolve_ev_uptake_levers(key),
        app._resolve_eruc_levers(key),
        app.cached_fed_uplift_factors(SIGNATURE, pack),
        adjust_ped=False,
        fed_policy_scopes=(),
        uptake_basis=app._resolve_uptake_basis(key),
        heavy_bev_transition=app._heavy_bev_transition_enabled(key),
    )
    return out


def _value(rows: pd.DataFrame, series: str, fy: int, role: str) -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


def _pool(rows: pd.DataFrame, fy: int, role: str) -> float:
    return sum(_value(rows, series, fy, role) for series in LIGHT_CLASSES)


# 1 ------------------------------------------------------------------------
def test_base_mode_uses_exact_vendored_shares_not_the_fitted_curve() -> None:
    exact = exact_vfm_share_curves(FYS, DEFAULT_EV_UPTAKE_MODE, repo_root=ROOT).set_index("june_year")
    assert exact["share_source"].eq("exact_vendored_vfm_table").all()
    assert exact["vfm_scenario"].eq("Base_EV").all()
    for fy in FYS:
        shares, scenario = composition_shares(fy, repo_root=ROOT, uptake_basis=DEFAULT_EV_UPTAKE_MODE)
        assert scenario == "Base_EV"
        assert float(exact.loc[fy, "conventional"]) == pytest.approx(shares["conventional"], abs=1e-12)
        assert sum(shares.values()) == pytest.approx(1.0, abs=1e-12)

    # The fitted curve must be measurably different, or this gate proves nothing.
    fitted = lever_share_curves(FYS, app.EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]).set_index("june_year")
    assert max(
        abs(float(fitted.loc[fy, "conventional"]) - float(exact.loc[fy, "conventional"])) for fy in FYS
    ) > 1e-4


# 2 ------------------------------------------------------------------------
def test_base_mode_preserves_the_post_macro_conventional_anchor(pack, post_macro) -> None:
    composed = _compose(post_macro, pack, _key(DEFAULT_EV_UPTAKE_MODE))
    for role in ROLES:
        for fy in FYS:
            assert _value(composed, "light_ruc_net_km", fy, role) == pytest.approx(
                _value(post_macro, "light_ruc_net_km", fy, role), abs=1e-6
            ), f"{role} FY{fy} conventional moved off the post-macro anchor"


def test_base_pool_equals_anchor_over_the_exact_base_conventional_share(pack, post_macro) -> None:
    composed = _compose(post_macro, pack, _key(DEFAULT_EV_UPTAKE_MODE))
    for role in ROLES:
        for fy in FYS:
            shares, _ = composition_shares(fy, repo_root=ROOT, uptake_basis=DEFAULT_EV_UPTAKE_MODE)
            anchor = _value(composed, "light_ruc_net_km", fy, role)
            assert _pool(composed, fy, role) == pytest.approx(
                anchor / shares["conventional"], abs=1e-6
            )
            # Classes sum to the pool: no class is invented or dropped.
            assert _value(composed, "light_bev_ruc_net_km", fy, role) == pytest.approx(
                (anchor / shares["conventional"]) * shares["bev"], abs=1e-6
            )
            assert _value(composed, "phev_ruc_net_km", fy, role) == pytest.approx(
                (anchor / shares["conventional"]) * shares["phev"], abs=1e-6
            )


# 3 ------------------------------------------------------------------------
def test_base_mode_is_idempotent(pack, post_macro) -> None:
    once = _compose(post_macro, pack, _key(DEFAULT_EV_UPTAKE_MODE))
    twice = _compose(once, pack, _key(DEFAULT_EV_UPTAKE_MODE))
    for role in ROLES:
        for fy in FYS:
            for series in (*LIGHT_CLASSES, "heavy_ruc_net_km"):
                assert _value(twice, series, fy, role) == pytest.approx(
                    _value(once, series, fy, role), abs=TOL
                )


# 4 ------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["MoT VFM fast", "MoT VFM slow"])
def test_alternative_modes_preserve_the_base_pool_and_change_only_shares(pack, post_macro, mode) -> None:
    base = _compose(post_macro, pack, _key(DEFAULT_EV_UPTAKE_MODE))
    selected = _compose(post_macro, pack, _key(mode))
    moved = False
    for role in ROLES:
        for fy in FYS:
            assert _pool(selected, fy, role) == pytest.approx(_pool(base, fy, role), abs=1e-6), (
                f"{mode} resized the {role} FY{fy} Base pool"
            )
            if abs(_value(selected, "light_ruc_net_km", fy, role) - _value(base, "light_ruc_net_km", fy, role)) > 1e-6:
                moved = True
    assert moved, f"{mode} must actually change composition"


# 5 ------------------------------------------------------------------------
def test_the_fitted_base_curve_is_absent_from_the_default_call_path() -> None:
    default_key = _key(DEFAULT_EV_UPTAKE_MODE)
    assert app._resolve_uptake_basis(default_key) == DEFAULT_EV_UPTAKE_MODE
    assert DEFAULT_EV_UPTAKE_MODE in EXACT_VFM_UPTAKE_BASES
    # The approximation survives only under a name that declares itself.
    assert PARAMETRIC_VFM_BASE_FIT_OPTION in app.EV_UPTAKE_MODE_OPTIONS
    assert app._resolve_uptake_basis(_key(PARAMETRIC_VFM_BASE_FIT_OPTION)) is None
    assert "approximation" in PARAMETRIC_VFM_BASE_FIT_OPTION.lower()
    assert PARAMETRIC_VFM_BASE_FIT_OPTION != DEFAULT_EV_UPTAKE_MODE


# 6 and 8 ------------------------------------------------------------------
def test_default_uptake_causes_zero_heavy_reclassification(pack, post_macro) -> None:
    for mode in EXACT_VFM_UPTAKE_BASES:
        composed = _compose(post_macro, pack, _key(mode))
        for role in ROLES:
            for fy in FYS:
                for series in ("heavy_ruc_net_km", "heavy_ruc_net_revenue"):
                    assert _value(composed, series, fy, role) == pytest.approx(
                        _value(post_macro, series, fy, role), abs=TOL
                    ), f"{mode} reclassified {series} for {role} FY{fy}"


def test_heavy_transition_is_available_but_only_when_explicitly_selected(pack, post_macro) -> None:
    """Off by default, and not coupled to the light selector."""
    assert app._heavy_bev_transition_enabled(_key(DEFAULT_EV_UPTAKE_MODE)) is False
    assert app._heavy_bev_transition_enabled(_key(DEFAULT_EV_UPTAKE_MODE, heavy=True)) is True
    # Legacy shorter keys resolve to the new default rather than the old behaviour.
    assert app._heavy_bev_transition_enabled((DEFAULT_EV_UPTAKE_MODE, (), (), "published", "published", False)) is False

    enabled = _compose(post_macro, pack, _key(DEFAULT_EV_UPTAKE_MODE, heavy=True))
    assert _value(enabled, "heavy_ruc_net_km", 2030, "basecase") != pytest.approx(
        _value(post_macro, "heavy_ruc_net_km", 2030, "basecase"), abs=1.0
    )


# 7 ------------------------------------------------------------------------
def test_policy_changes_conventional_once_and_leaves_bev_phev_fixed(pack, post_macro) -> None:
    pre_policy = _compose(post_macro, pack, _key(DEFAULT_EV_UPTAKE_MODE))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    post_policy, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        _key(DEFAULT_EV_UPTAKE_MODE, policy=app.FED_POLICY_DELAYED_6M),
        pack,
    )
    for role in ROLES:
        for fy in FYS:
            for series in ("light_bev_ruc_net_km", "phev_ruc_net_km"):
                assert _value(post_policy, series, fy, role) == pytest.approx(
                    _value(pre_policy, series, fy, role), abs=1e-6
                ), f"policy moved {series} for {role} FY{fy}"
    # The delayed policy response lands in FY2027 only, and exactly once.
    moved = [
        fy
        for fy in FYS
        if abs(
            _value(post_policy, "light_ruc_net_km", fy, "basecase")
            - _value(pre_policy, "light_ruc_net_km", fy, "basecase")
        )
        > 1e-6
    ]
    assert moved == [2027]


# 9 ------------------------------------------------------------------------
def test_no_lambda_value_enters_any_decision_facing_level(pack) -> None:
    rows = pack.revenue_chart_rows
    decision_facing = rows[~rows["scenario_role"].astype(str).eq("official_comparator")]
    haystack = decision_facing.astype(str)
    for column in ("source_basis", "formula", "value_status", "data_scope"):
        if column in haystack.columns:
            assert not haystack[column].str.contains("lambda", case=False, na=False).any()
            assert not haystack[column].str.contains("migration_total", case=False, na=False).any()


# 10 -----------------------------------------------------------------------
def test_chart_line_and_stack_agree_under_the_canonical_base(pack) -> None:
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    key = _key(DEFAULT_EV_UPTAKE_MODE, policy=app.FED_POLICY_DELAYED_6M)
    rows, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    line, _residuals, stack, _bridge = app.cached_aligned_scenario_detail_frames(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    assert not line.empty and not stack.empty
    for fy in FYS:
        chart_value = _value(rows, "total_nltf_net_revenue", fy, "basecase")
        matched = line[
            line["FY"].astype("Int64").eq(fy)
            & line["series_id"].astype(str).eq("total_nltf_net_revenue")
            & line["source_path"].astype(str).str.contains("Base", case=False, na=False)
        ]
        values = pd.to_numeric(matched["value"], errors="coerce").dropna()
        assert len(values), f"line reconciliation has no FY{fy} Base total"
        assert float(values.iloc[0]) == pytest.approx(chart_value, abs=1e-6)


# ---------------------------------------------------------------------------
# Scenario / policy matrix
# ---------------------------------------------------------------------------

_CONFLICT_SCENARIOS = ("middle_east_low", "middle_east_medium", "middle_east_high")


def _scenario_value(rows: pd.DataFrame, scenario: str, series: str, fy: int) -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_name"].astype(str).eq(scenario)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


@pytest.mark.parametrize("mode", list(EXACT_VFM_UPTAKE_BASES))
def test_every_current_scenario_derives_its_own_base_pool(pack, post_macro, mode) -> None:
    """Each scenario's pool comes from its own post-macro conventional anchor.

    Asserted at the COMPOSITION stage. The pool identity is a property of the
    allocation, not of the final output: the governed policy response then
    changes conventional activity while BEV and PHEV stay fixed, which
    deliberately leaves the identity behind. That policy behaviour is gated
    separately in
    test_policy_changes_conventional_once_and_leaves_bev_phev_fixed.
    """
    composed = _compose(post_macro, pack, _key(mode))
    pools = {}
    for role in ROLES:
        for fy in FYS:
            shares, _ = composition_shares(fy, repo_root=ROOT, uptake_basis=mode)
            conventional = _value(composed, "light_ruc_net_km", fy, role)
            pool = _pool(composed, fy, role)
            assert pool == pytest.approx(conventional / shares["conventional"], abs=1e-6), (
                f"{role} FY{fy} pool identity broke under {mode}"
            )
            pools[(role, fy)] = pool
    # Base and comparison must not collapse onto one pool.
    for fy in FYS:
        assert pools[("basecase", fy)] != pytest.approx(pools[("comparison", fy)], abs=1e-3)


@pytest.mark.parametrize("current_policy", ["published", "delayed_6m", "off"])
def test_policy_states_move_conventional_only(pack, current_policy) -> None:
    """Across every current policy state, only conventional Light RUC moves."""
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    published, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE,
        _key(DEFAULT_EV_UPTAKE_MODE, policy=app.FED_POLICY_PUBLISHED), pack,
    )
    rows, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE,
        _key(DEFAULT_EV_UPTAKE_MODE, policy=current_policy), pack,
    )
    for role in ROLES:
        for fy in FYS:
            for series in ("light_bev_ruc_net_km", "phev_ruc_net_km"):
                assert _value(rows, series, fy, role) == pytest.approx(
                    _value(published, series, fy, role), abs=1e-6
                ), f"{current_policy} moved {series} for {role} FY{fy}"


def test_conflict_paths_move_conventional_only(pack) -> None:
    """The conflict response is an activity response, not a composition one.

    It applies generalized fuel/RUC cost elasticity to CONVENTIONAL Light and
    Heavy activity; electric activity must not inherit a diesel multiplier. It
    therefore deliberately does NOT preserve the Base composition identity, and
    asserting that identity on a conflict path would be wrong. What must hold
    is that BEV and PHEV are untouched.
    """
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    key = _key(DEFAULT_EV_UPTAKE_MODE, policy=app.FED_POLICY_DELAYED_6M)
    rows, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    present = set(rows["scenario_name"].astype(str))
    if not set(_CONFLICT_SCENARIOS) <= present:
        pytest.skip("conflict replay unavailable in this environment")

    moved_somewhere = False
    for scenario in _CONFLICT_SCENARIOS:
        for fy in FYS:
            for series in ("light_bev_ruc_net_km", "phev_ruc_net_km"):
                assert _scenario_value(rows, scenario, series, fy) == pytest.approx(
                    _scenario_value(rows, "current_basecase", series, fy), abs=1e-6
                ), f"{scenario} FY{fy} moved {series}; electric activity must not follow diesel cost"
            conventional = _scenario_value(rows, scenario, "light_ruc_net_km", fy)
            base_conventional = _scenario_value(rows, "current_basecase", "light_ruc_net_km", fy)
            if abs(conventional - base_conventional) > 1e-6:
                moved_somewhere = True
                assert conventional < base_conventional, (
                    f"{scenario} FY{fy} raised conventional activity under a cost shock"
                )
    assert moved_somewhere, "no conflict path moved conventional activity at all"
