"""Performance-cache architecture: staged caches must not change results.

The view pipeline (bridge -> sensitivity -> lever overlays -> filter/cone)
is cached at three grains: the sensitivity stage, the series-agnostic
scenario overlay rows, and the full view. These tests pin the equivalences
that make those caches safe and the warmer targets that keep first-touch
interactions warm.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.conflict_fuel_paths import (
    CONFLICT_FUEL_SCENARIO_LEVELS,
    conflict_scenario_name,
    conflict_trace_name,
    load_conflict_fuel_price_paths,
)
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

ROOT = Path(__file__).resolve().parents[1]
FED = "Current planned path"
TRACES = ("Current finalist Base case", "Actual")
CONFLICT_SCENARIO_NAMES = tuple(
    conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)
CONFLICT_TRACE_NAMES = tuple(
    conflict_trace_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)


@pytest.fixture(scope="module")
def context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


def _default_keys():
    sens = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    uptake = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0)
    return sens, uptake


def test_missing_policy_replay_fails_closed_for_current_paths_but_keeps_mbu_rate_only() -> None:
    scopes = (
        ("delayed_6m", ("basecase", "comparison")),
        ("delayed_6m", ("official_comparator",)),
    )
    governed, audit = app._policy_scopes_for_available_replay(
        scopes,
        replay_available=False,
    )
    assert governed == (("delayed_6m", ("official_comparator",)),)
    assert len(audit) == 1
    assert not bool(audit.iloc[0]["applied"])
    assert audit.iloc[0]["transformation_basis"] == "policy_replay_unavailable_not_applied"
    assert "published values" in str(audit.iloc[0]["reason"])
    assert (
        app._effective_fed_policy_state(
            app.FED_POLICY_DELAYED_6M,
            app._CURRENT_FED_UPLIFT_ROLES,
            audit,
        )
        == app.FED_POLICY_PUBLISHED
    )
    assert (
        app._effective_fed_policy_state(
            app.FED_POLICY_DELAYED_6M,
            app._MBU26_FED_UPLIFT_ROLES,
            audit,
        )
        == app.FED_POLICY_DELAYED_6M
    )

    available_scopes, available_audit = app._policy_scopes_for_available_replay(
        scopes,
        replay_available=True,
    )
    assert available_scopes == scopes
    assert available_audit.empty


def test_replay_value_error_is_caught_before_streamlit_view_render(monkeypatch) -> None:
    def broken_replay(*_args, **_kwargs):
        raise ValueError("annual policy bridge unavailable")

    monkeypatch.setattr(app, "cached_fuel_price_scenario_replay", broken_replay)
    replay, error_type = app._safe_fuel_price_scenario_replay((), object())
    assert replay is None
    assert error_type == "ValueError"


def test_treasury_macro_fallback_survives_conflict_replay_failure(
    monkeypatch,
) -> None:
    source = pd.DataFrame(
        [
            {
                "scenario_name": "current_basecase",
                "scenario_role": "basecase",
                "series_id": "ped_vkt_per_capita",
                "time_grain": "quarterly",
                "period": "2027Q1",
                "value": 10.0,
            }
        ]
    )
    macro_replay = object()
    macro_audit = pd.DataFrame(
        [{"audit_type": "treasury_baseline_macro", "factor": 1.1}]
    )

    monkeypatch.setattr(
        app,
        "cached_sensitivity_stage_frames",
        lambda *_args, **_kwargs: ({}, {"chart_rows": source.copy()}, True),
    )
    monkeypatch.setattr(app, "_resolve_ev_uptake_levers", lambda *_args: None)
    monkeypatch.setattr(app, "_resolve_eruc_levers", lambda *_args: None)
    monkeypatch.setattr(app, "cached_fed_uplift_factors", lambda *_args: {})
    monkeypatch.setattr(
        app,
        "_safe_fuel_price_scenario_replay",
        lambda *_args: (None, "ValueError"),
    )
    monkeypatch.setattr(
        app,
        "_safe_treasury_baseline_macro_replay",
        lambda *_args: (macro_replay, ""),
    )

    def apply_macro(rows, replay):
        assert replay is macro_replay
        adjusted = rows.copy()
        adjusted["value"] = pd.to_numeric(adjusted["value"]) * 1.1
        return adjusted, macro_audit

    monkeypatch.setattr(app, "apply_treasury_macro_to_chart_rows", apply_macro)
    monkeypatch.setattr(
        app,
        "_apply_scenario_overlays",
        lambda rows, *_args, **_kwargs: (
            rows.copy(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
        ),
    )

    rows, _, _, policy_audit, conflict_audit = app.cached_scenario_overlay_rows(
        (("macro-fallback", 1, 1),),
        ("Off",),
        PED_BRIDGE_DEFAULT_MODE,
        (app.DEFAULT_EV_UPTAKE_MODE, (), (), app.FED_POLICY_DELAYED_6M),
        object(),
    )
    assert float(rows.iloc[0]["value"]) == pytest.approx(11.0)
    assert not policy_audit.empty
    assert policy_audit.iloc[0]["replay_error_type"] == "ValueError"
    assert conflict_audit.empty


def test_dashboard_refuses_silent_legacy_macro_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        app,
        "cached_sensitivity_stage_frames",
        lambda *_args, **_kwargs: (
            {},
            {"chart_rows": pd.DataFrame([{"value": 1.0}])},
            True,
        ),
    )
    monkeypatch.setattr(app, "_resolve_ev_uptake_levers", lambda *_args: None)
    monkeypatch.setattr(app, "_resolve_eruc_levers", lambda *_args: None)
    monkeypatch.setattr(app, "cached_fed_uplift_factors", lambda *_args: {})
    monkeypatch.setattr(
        app,
        "_safe_fuel_price_scenario_replay",
        lambda *_args: (None, "ValueError"),
    )
    monkeypatch.setattr(
        app,
        "_safe_treasury_baseline_macro_replay",
        lambda *_args: (None, "OSError"),
    )

    with pytest.raises(RuntimeError, match="refusing to silently revert"):
        app.cached_scenario_overlay_rows(
            (("macro-fail-closed", 1, 1),),
            ("Off",),
            PED_BRIDGE_DEFAULT_MODE,
            (app.DEFAULT_EV_UPTAKE_MODE, (), (), app.FED_POLICY_DELAYED_6M),
            object(),
        )


def test_view_returns_fresh_copies_across_calls(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    first = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    # Poison the returned frame; a second retrieval must be unaffected.
    first["filtered_rows"].loc[:, "value"] = -1.0
    second = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    assert not second["filtered_rows"]["value"].eq(-1.0).all()
    assert (pd.to_numeric(second["filtered_rows"]["value"], errors="coerce") > 0).any()


def test_overlay_rows_match_view_chart_rows(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    view = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    rows, _, _, _, _ = app.cached_scenario_overlay_rows(signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack)
    pd.testing.assert_frame_equal(view["chart_rows"].reset_index(drop=True), rows.reset_index(drop=True))


def test_policy_and_fuel_totals_reconcile_across_chart_line_and_stack(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    uptake = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)
    rows, _, _, _, fuel_audit = app.cached_scenario_overlay_rows(
        signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    line, _, stack, _ = app.cached_aligned_scenario_detail_frames(
        signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )

    chart = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2027)
        & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
    ].set_index("scenario_name")["value"].map(float)
    line_total = line[
        pd.to_numeric(line["FY"], errors="coerce").eq(2027)
        & line["series_id"].astype(str).eq("total_nltf_net_revenue")
    ].set_index("scenario_name")["value"].map(float)
    stack_total = stack[
        pd.to_numeric(stack["FY"], errors="coerce").eq(2027)
        & stack["series_id"].astype(str).eq("total_nltf_net_revenue")
        & stack["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
    ].set_index("scenario_name")["value"].map(float)

    expected_scenarios = {
        "current_basecase",
        "current_comparison_1",
        "mbu26_official",
        *CONFLICT_SCENARIO_NAMES,
    }
    assert expected_scenarios <= set(chart.index)
    assert not fuel_audit.empty
    for scenario in expected_scenarios:
        assert line_total.loc[scenario] == pytest.approx(chart.loc[scenario], abs=1e-9)
        assert stack_total.loc[scenario] == pytest.approx(chart.loc[scenario], abs=1e-9)


def test_current_and_mbu_policy_nine_state_matrix_keeps_fuel_on_current_scope(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    policy_states = (
        app.FED_POLICY_PUBLISHED,
        app.FED_POLICY_DELAYED_6M,
        app.FED_POLICY_OFF,
    )
    states: dict[tuple[str, str], pd.DataFrame] = {}
    for current_policy in policy_states:
        for mbu_policy in policy_states:
            rows, _, _, _, _ = app.cached_scenario_overlay_rows(
                signature,
                sens,
                PED_BRIDGE_DEFAULT_MODE,
                (
                    app.DEFAULT_EV_UPTAKE_MODE,
                    (),
                    (),
                    current_policy,
                    mbu_policy,
                ),
                pack,
            )
            states[(current_policy, mbu_policy)] = rows

    base_scenario = "current_basecase"
    current_scenarios = (
        base_scenario,
        "current_comparison_1",
        *CONFLICT_SCENARIO_NAMES,
    )
    mbu_scenario = "mbu26_official"

    def total(state: tuple[str, str], scenario: str, fy: int) -> float:
        rows = states[state]
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["scenario_name"].astype(str).eq(scenario)
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        ]
        assert len(selected) == 1
        return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])

    # Moving only the MBU26 switch cannot alter any Current trace, including
    # any registered conflict severity cloned from the matching Current Base
    # policy replay.
    for current_policy in policy_states:
        for scenario in current_scenarios:
            for fy in (2027, 2028):
                reference = total(
                    (current_policy, app.FED_POLICY_PUBLISHED), scenario, fy
                )
                for mbu_policy in policy_states:
                    assert total((current_policy, mbu_policy), scenario, fy) == pytest.approx(
                        reference, abs=1e-9
                    )

    # Moving only the Current switch cannot alter MBU26.
    for mbu_policy in policy_states:
        for fy in (2027, 2028):
            reference = total(
                (app.FED_POLICY_PUBLISHED, mbu_policy), mbu_scenario, fy
            )
            for current_policy in policy_states:
                assert total((current_policy, mbu_policy), mbu_scenario, fy) == pytest.approx(
                    reference, abs=1e-9
                )

    # Original timing applies in 2027Q1-Q2 (inside FY2027). The six-month
    # deferral starts at FY2028, while OFF never reinstates the step.
    for mbu_policy in policy_states:
        for scenario in current_scenarios:
            published_2027 = total(
                (app.FED_POLICY_PUBLISHED, mbu_policy), scenario, 2027
            )
            delayed_2027 = total(
                (app.FED_POLICY_DELAYED_6M, mbu_policy), scenario, 2027
            )
            off_2027 = total(
                (app.FED_POLICY_OFF, mbu_policy), scenario, 2027
            )
            assert published_2027 > delayed_2027
            assert delayed_2027 == pytest.approx(off_2027, abs=1e-9)
            published_2028 = total(
                (app.FED_POLICY_PUBLISHED, mbu_policy), scenario, 2028
            )
            delayed_2028 = total(
                (app.FED_POLICY_DELAYED_6M, mbu_policy), scenario, 2028
            )
            off_2028 = total(
                (app.FED_POLICY_OFF, mbu_policy), scenario, 2028
            )
            assert published_2028 == pytest.approx(delayed_2028, abs=1e-9)
            assert off_2028 < delayed_2028
    for current_policy in policy_states:
        published_2027 = total(
            (current_policy, app.FED_POLICY_PUBLISHED), mbu_scenario, 2027
        )
        delayed_2027 = total(
            (current_policy, app.FED_POLICY_DELAYED_6M), mbu_scenario, 2027
        )
        off_2027 = total(
            (current_policy, app.FED_POLICY_OFF), mbu_scenario, 2027
        )
        assert published_2027 > delayed_2027
        assert delayed_2027 == pytest.approx(off_2027, abs=1e-9)
        published_2028 = total(
            (current_policy, app.FED_POLICY_PUBLISHED), mbu_scenario, 2028
        )
        delayed_2028 = total(
            (current_policy, app.FED_POLICY_DELAYED_6M), mbu_scenario, 2028
        )
        off_2028 = total(
            (current_policy, app.FED_POLICY_OFF), mbu_scenario, 2028
        )
        assert published_2028 == pytest.approx(delayed_2028, abs=1e-9)
        assert off_2028 < delayed_2028

    # Quarterly scenario timing stays correct under all three Current states:
    # no pre-shock leakage and exact reconciliation back to the selected
    # original/delayed/off annual path.
    for current_policy in policy_states:
        rows = states[(current_policy, app.FED_POLICY_PUBLISHED)]
        reconciled_scenarios = (base_scenario, *CONFLICT_SCENARIO_NAMES)
        annual_pair = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["scenario_name"].astype(str).isin(reconciled_scenarios)
            & pd.to_numeric(rows["june_year"], errors="coerce").isin([2026, 2027, 2028])
        ].copy()
        derived = {
            scenario: app._disaggregate_annual_rows_to_quarterly(
                annual_pair[annual_pair["scenario_name"].astype(str).eq(scenario)], rows
            )
            for scenario in reconciled_scenarios
        }
        base_quarters = derived[base_scenario].set_index("period")["value"].map(float)
        for conflict_scenario in CONFLICT_SCENARIO_NAMES:
            conflict_quarters = derived[conflict_scenario].set_index("period")["value"].map(float)
            for period in ("2025Q3", "2025Q4"):
                assert conflict_quarters.loc[period] == pytest.approx(
                    base_quarters.loc[period], abs=1e-9
                )
        for scenario in reconciled_scenarios:
            annual_values = annual_pair[
                annual_pair["scenario_name"].astype(str).eq(scenario)
            ].set_index("june_year")["value"].map(float)
            quarterly_sums = derived[scenario].groupby("june_year")["value"].sum()
            for fy in (2026, 2027, 2028):
                assert float(quarterly_sums.loc[fy]) == pytest.approx(float(annual_values.loc[fy]), abs=1e-6)


def test_middle_east_paths_reconcile_net_revenue_and_quarter_timing(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    traces = ("Current finalist Base case", *CONFLICT_TRACE_NAMES)
    annual_view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        FED,
        traces,
        sens,
        PED_BRIDGE_DEFAULT_MODE,
        uptake,
        pack,
    )
    quarterly_view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "quarterly",
        FED,
        traces,
        sens,
        PED_BRIDGE_DEFAULT_MODE,
        uptake,
        pack,
    )
    annual = annual_view["filtered_rows"].pivot_table(
        index="june_year", columns="scenario_name", values="value", aggfunc="first"
    )
    expected_years = set(range(2026, 2031))
    expected_scenarios = ("current_basecase", *CONFLICT_SCENARIO_NAMES)
    assert expected_years <= set(pd.to_numeric(annual.index, errors="raise").astype(int))
    assert set(expected_scenarios) <= set(annual.columns)
    assert annual.loc[sorted(expected_years), list(expected_scenarios)].notna().all().all()
    assert (annual.loc[sorted(expected_years), list(expected_scenarios)] > 0).all().all()
    for conflict_scenario in CONFLICT_SCENARIO_NAMES:
        assert annual.at[2026, conflict_scenario] < annual.at[2026, "current_basecase"]
        assert annual.at[2027, conflict_scenario] < annual.at[2027, "current_basecase"]
    # All three paths are identical through FY2026. Future path differences
    # must not leak backwards through the smoothed EV/PHEV migration split.
    assert (
        annual.loc[2026, list(CONFLICT_SCENARIO_NAMES)].max()
        - annual.loc[2026, list(CONFLICT_SCENARIO_NAMES)].min()
    ) <= 1e-9

    # Petrol affects Net FED and diesel affects Net RUC. Those two canonical
    # net deltas must close exactly to each displayed whole-of-NLTF delta for
    # every severity and every requested June year.
    component_rows = annual_view["chart_rows"]
    component_values = component_rows[
        component_rows["time_grain"].astype(str).eq("june_year")
        & component_rows["fed_path"].astype(str).eq(FED)
        & component_rows["scenario_name"].astype(str).isin(
            expected_scenarios
        )
        & component_rows["series_id"].astype(str).isin(
            ["net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"]
        )
        & pd.to_numeric(component_rows["june_year"], errors="coerce").isin(expected_years)
    ].pivot_table(
        index=["june_year", "series_id"],
        columns="scenario_name",
        values="value",
        aggfunc="first",
    )
    for conflict_scenario in CONFLICT_SCENARIO_NAMES:
        for fy in expected_years:
            deltas = {
                series_id: float(
                    component_values.at[(fy, series_id), conflict_scenario]
                    - component_values.at[(fy, series_id), "current_basecase"]
                )
                for series_id in (
                    "net_fed_revenue",
                    "total_ruc_net_revenue",
                    "total_nltf_net_revenue",
                )
            }
            assert deltas["total_nltf_net_revenue"] == pytest.approx(
                deltas["net_fed_revenue"] + deltas["total_ruc_net_revenue"],
                abs=1e-9,
            )

    assert quarterly_view["quarterly_disaggregated"] is True
    quarterly = quarterly_view["filtered_rows"].pivot_table(
        index="period", columns="scenario_name", values="value", aggfunc="first"
    )
    for conflict_scenario in CONFLICT_SCENARIO_NAMES:
        for period in ("2025Q3", "2025Q4", "2026Q1"):
            assert float(quarterly.at[period, conflict_scenario]) == pytest.approx(
                float(quarterly.at[period, "current_basecase"]), abs=1e-9
            )
        for period in ("2026Q2", "2026Q3", "2026Q4"):
            assert float(quarterly.at[period, conflict_scenario]) < float(
                quarterly.at[period, "current_basecase"]
            )

    # All severities share the observed Q2/Q3 fuel-price anchors, so later
    # prospective assumptions must not leak backward through annual-to-quarter
    # reconciliation. Their prospective Q4 then orders Net revenue
    # Low >= Medium >= High as the fuel premium increases.
    configured_paths = load_conflict_fuel_price_paths(ROOT)
    for period in ("2026Q2", "2026Q3"):
        configured_period = configured_paths[
            configured_paths["period"].astype(str).eq(period)
        ]
        assert len(configured_period) == len(CONFLICT_FUEL_SCENARIO_LEVELS)
        assert configured_period["scenario_diesel_cpl"].nunique() == 1
        assert configured_period["scenario_petrol_cpl"].nunique() == 1
        conflict_values = [
            float(quarterly.at[period, conflict_scenario])
            for conflict_scenario in CONFLICT_SCENARIO_NAMES
        ]
        assert max(conflict_values) - min(conflict_values) <= 1e-9
    q4_values = [
        float(quarterly.at["2026Q4", conflict_scenario])
        for conflict_scenario in CONFLICT_SCENARIO_NAMES
    ]
    assert q4_values == sorted(q4_values, reverse=True)

    for scenario_name in expected_scenarios:
        sums = quarterly_view["filtered_rows"][
            quarterly_view["filtered_rows"]["scenario_name"].astype(str).eq(scenario_name)
            & pd.to_numeric(
                quarterly_view["filtered_rows"]["june_year"], errors="coerce"
            ).isin(expected_years)
        ].groupby("june_year")["value"].sum()
        for fy in expected_years:
            assert float(sums.loc[fy]) == pytest.approx(float(annual.at[fy, scenario_name]), abs=1e-6)


def test_cone_band_is_uptake_key_invariant(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    bands = {}
    for mode in ("MoT VFM base", "MoT VFM fast"):
        view = app.cached_revenue_outlook_view(
            signature, "Total NLTF revenue", "june_year", FED, TRACES, sens,
            PED_BRIDGE_DEFAULT_MODE, (mode, (), (), 0), pack,
        )
        bands[mode] = view["cone_band"]
    pd.testing.assert_frame_equal(
        bands["MoT VFM base"].reset_index(drop=True),
        bands["MoT VFM fast"].reset_index(drop=True),
    )
    assert not bands["MoT VFM base"].empty


def test_warm_targets_cover_single_family_sensitivities() -> None:
    keys = app._revenue_outlook_warm_sensitivity_keys()
    assert len(keys) == 9
    assert all(len(key) == 11 for key in keys)
    assert app.selected_sensitivity_key("Med", "Off", "Off", freight_rail_shift="Off") in keys
    assert app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="High") in keys


def test_warmer_respects_disable_flag(monkeypatch) -> None:
    monkeypatch.setenv("REVENUE_OUTLOOK_CACHE_WARMER", "0")
    app._REVENUE_OUTLOOK_WARMER_STARTED.clear()
    app._start_revenue_outlook_cache_warmer()
    assert not app._REVENUE_OUTLOOK_WARMER_STARTED.is_set()
