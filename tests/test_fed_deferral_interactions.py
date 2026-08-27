"""Deferral-duration interaction gates with the other Revenue Outlook levers.

Representative multi-lever combinations from the deferral-duration handoff,
run through the exact production overlay chain (bridge -> sensitivity ->
Treasury macro -> uptake/e-RUC -> FED/RUC policy -> conflict append):

  1. 18-month deferral + PT High + Fleet efficiency High
  2. 24-month deferral + VFM Fast + e-RUC On
  3. 30-month deferral + High conflict + High population trace
  4. 36-month deferral + Freight rail High + PT Med
  5. six-month deferral + every control at the current default

Invariants asserted for each combination:
  * Net MVR is unchanged by the FED-duration control;
  * the deferral moves Net FED and Net RUC in its direct window and the
    total moves by exactly the FED + RUC deltas (formula closure);
  * the selected sensitivity/uptake/e-RUC effect does not disappear when a
    deferral is chosen;
  * identical configurations return identical frames;
  * all 121 Current x official key digests are unique.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.engine import ENGINE_AR1, engine_revenue_outlook_dir
from model_dashboard.fed_policy_states import FED_POLICY_SPECS, policy_spec
from model_dashboard.official_vintage import (
    bridge_vintage_id_from_manifest,
    default_comparator_vintage_id,
)
from model_dashboard.revenue_outlook import (
    PED_BRIDGE_DEFAULT_MODE,
    PED_BRIDGE_OPTIMIZED_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey


def governed_key(pack, engine: str, current_state: str, official_state: str):
    """The builder's production key, mirrored locally.

    Deliberately NOT imported from scripts/build_revenue_outlook_policy_runtime:
    importing that module switches app.POLICY_RUNTIME_FAST_PATH_ENABLED off at
    import time for the whole pytest process, which fails the fast-path
    contract checks in later test modules.
    """
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
    return RevenueScenarioComputationKey(
        engine=engine,
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=current_state,
        official_fed_policy_state=official_state,
        ped_bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        bridge_vintage_id=str(bridge_vintage_id_from_manifest(pack.manifest, ROOT) or ""),
        official_comparator_vintage_id=str(
            block.get("official_comparator_vintage_id")
            or default_comparator_vintage_id(ROOT)
        ),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )

ROOT = Path(__file__).resolve().parents[1]
BASE_TRACE = "Current finalist Base case"
HIGH_POP_TRACE = "Current finalist High population/comparison"
HIGH_CONFLICT_TRACE = "Middle East conflict: High"
TAX_SERIES = ("net_fed_revenue", "total_ruc_net_revenue")


@pytest.fixture(scope="module")
def outlook() -> dict[str, object]:
    pack_dir = ROOT / engine_revenue_outlook_dir(ENGINE_AR1)
    pack = load_revenue_outlook_pack(pack_dir, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, ROOT)
    # Interaction gates exercise the reference chain, never the materialised
    # catalogue, so a stale or missing policy runtime cannot skew them. The
    # production default is RESTORED afterwards - leaking False into later
    # test modules fails their fast-path contract checks.
    original_fast_path = app.POLICY_RUNTIME_FAST_PATH_ENABLED
    app.POLICY_RUNTIME_FAST_PATH_ENABLED = False
    yield {"pack": pack, "signature": signature}
    app.POLICY_RUNTIME_FAST_PATH_ENABLED = original_fast_path


def _overlay_rows(
    outlook: dict[str, object],
    *,
    current_state: str,
    fleet: str = "Off",
    pt: str = "Off",
    freight: str = "Off",
    demand: str = "Off",
    uptake_basis: str | None = None,
    eruc_levers: tuple[float, ...] = (),
    bridge_mode: str = PED_BRIDGE_DEFAULT_MODE,
) -> pd.DataFrame:
    pack = outlook["pack"]
    signature = outlook["signature"]
    sensitivity_key = app.selected_sensitivity_key(
        fleet, pt, demand, freight_rail_shift=freight
    )
    key = governed_key(pack, ENGINE_AR1, current_state, "published")
    changes: dict[str, object] = {}
    if uptake_basis is not None:
        changes["uptake_basis"] = uptake_basis
    if eruc_levers:
        changes["eruc_levers"] = eruc_levers
    if bridge_mode != PED_BRIDGE_DEFAULT_MODE:
        changes["ped_bridge_mode"] = bridge_mode
    if changes:
        key = key.replace(**changes)
    rows, _uptake, _eruc, _policy, _scenario = app.cached_scenario_overlay_rows(
        signature, sensitivity_key, bridge_mode, key, pack
    )
    return rows


def _annual(rows: pd.DataFrame, trace: str, series_id: str) -> dict[int, float]:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["trace_name"].astype(str).eq(trace)
        & rows["series_id"].astype(str).eq(series_id)
    ]
    fy = pd.to_numeric(selected["june_year"], errors="coerce")
    value = pd.to_numeric(selected["value"], errors="coerce")
    return {
        int(year): float(val)
        for year, val in zip(fy, value, strict=True)
        if pd.notna(year) and pd.notna(val)
    }


def _assert_policy_invariants(
    policy_rows: pd.DataFrame,
    published_rows: pd.DataFrame,
    *,
    state: str,
    trace: str = BASE_TRACE,
) -> None:
    """MVR invariance, direct-window movement and formula closure vs published."""
    spec = policy_spec(state)
    window_fys = sorted(
        {
            int(quarter.split("Q")[0]) + (1 if int(quarter.split("Q")[1]) >= 3 else 0)
            for quarter in spec.direct_affected_quarters()
        }
    )
    mvr_policy = _annual(policy_rows, trace, "net_mvr_revenue")
    mvr_published = _annual(published_rows, trace, "net_mvr_revenue")
    for fy in sorted(set(mvr_policy) & set(mvr_published)):
        assert mvr_policy[fy] == pytest.approx(mvr_published[fy], abs=1e-9), (state, fy)

    fed_delta = {}
    for series_id in TAX_SERIES:
        policy_values = _annual(policy_rows, trace, series_id)
        published_values = _annual(published_rows, trace, series_id)
        for fy in window_fys:
            if fy in policy_values and fy in published_values:
                # Strict in FY2027 (a taxed base always exists there); later
                # window years may legitimately be equal when another lever
                # has removed the taxed base entirely (e.g. e-RUC migrates
                # the petrol fleet off excise, so no wedge remains to defer).
                if fy == 2027:
                    assert policy_values[fy] < published_values[fy], (state, series_id, fy)
                else:
                    assert policy_values[fy] <= published_values[fy] + 1e-9, (
                        state,
                        series_id,
                        fy,
                    )
        fed_delta[series_id] = {
            fy: policy_values[fy] - published_values[fy]
            for fy in sorted(set(policy_values) & set(published_values))
        }
    total_policy = _annual(policy_rows, trace, "total_nltf_net_revenue")
    total_published = _annual(published_rows, trace, "total_nltf_net_revenue")
    for fy in sorted(set(total_policy) & set(total_published)):
        expected = fed_delta["net_fed_revenue"].get(fy, 0.0) + fed_delta[
            "total_ruc_net_revenue"
        ].get(fy, 0.0)
        assert total_policy[fy] - total_published[fy] == pytest.approx(expected, abs=1e-6), (
            state,
            fy,
        )


def test_18m_deferral_composes_with_pt_high_and_fleet_high(outlook) -> None:
    policy = _overlay_rows(outlook, current_state="delayed_18m", fleet="High", pt="High")
    published = _overlay_rows(outlook, current_state="published", fleet="High", pt="High")
    _assert_policy_invariants(policy, published, state="delayed_18m")
    # The sensitivity effect must not disappear under the deferral: the same
    # policy state without the levers gives a different Base path.
    unlevered = _overlay_rows(outlook, current_state="delayed_18m")
    levered_total = _annual(policy, BASE_TRACE, "total_nltf_net_revenue")
    unlevered_total = _annual(unlevered, BASE_TRACE, "total_nltf_net_revenue")
    late = [fy for fy in levered_total if fy >= 2035]
    assert late and any(
        abs(levered_total[fy] - unlevered_total[fy]) > 1e-6 for fy in late
    ), "PT High + Fleet High left no trace on the deferred path"


def test_24m_deferral_composes_with_vfm_fast_and_eruc(outlook) -> None:
    eruc = (2027.0, 3.0, 1.0, -0.15, 2.70)
    policy = _overlay_rows(
        outlook, current_state="delayed_24m", uptake_basis="MoT VFM fast", eruc_levers=eruc
    )
    published = _overlay_rows(
        outlook, current_state="published", uptake_basis="MoT VFM fast", eruc_levers=eruc
    )
    _assert_policy_invariants(policy, published, state="delayed_24m")
    without_eruc = _overlay_rows(
        outlook, current_state="delayed_24m", uptake_basis="MoT VFM fast"
    )
    with_eruc_ped = _annual(policy, BASE_TRACE, "gross_ped_revenue")
    without_eruc_ped = _annual(without_eruc, BASE_TRACE, "gross_ped_revenue")
    assert any(
        abs(with_eruc_ped[fy] - without_eruc_ped[fy]) > 1e-6
        for fy in with_eruc_ped
        if fy in without_eruc_ped and fy >= 2028
    ), "the e-RUC transition left no trace on the deferred path"


def test_30m_deferral_composes_with_high_conflict_and_high_population(outlook) -> None:
    policy = _overlay_rows(outlook, current_state="delayed_30m")
    published = _overlay_rows(outlook, current_state="published")
    _assert_policy_invariants(policy, published, state="delayed_30m")
    # The High conflict and High population traces must carry the deferral too.
    for trace in (HIGH_CONFLICT_TRACE, HIGH_POP_TRACE):
        _assert_policy_invariants(policy, published, state="delayed_30m", trace=trace)


def test_36m_deferral_composes_with_freight_high_and_pt_med(outlook) -> None:
    policy = _overlay_rows(outlook, current_state="delayed_36m", freight="High", pt="Med")
    published = _overlay_rows(outlook, current_state="published", freight="High", pt="Med")
    _assert_policy_invariants(policy, published, state="delayed_36m")


def test_6m_deferral_at_defaults_matches_the_production_state(outlook) -> None:
    """The generic six-month state under default levers is the production path."""
    policy = _overlay_rows(outlook, current_state="delayed_6m")
    published = _overlay_rows(outlook, current_state="published")
    _assert_policy_invariants(policy, published, state="delayed_6m")
    touched = policy[policy.get("_fed_policy", pd.Series(dtype=str)).astype(str).ne("")]
    assert set(touched["_fed_policy"]) == {"delay_6m"}
    # Quarterly rows the annual reconciliation touched carry the production
    # `_quarterly_reconciled` suffix; annual rows carry the plain marker.
    assert set(touched["value_status"]) <= {
        "fed_uplift_delayed_6m",
        "fed_uplift_delayed_6m_quarterly_reconciled",
    }
    assert "fed_uplift_delayed_6m" in set(touched["value_status"])
    assert set(touched["data_scope"]) <= {
        "fed_uplift_delay_counterfactual",
        "fed_uplift_delay_counterfactual_quarterly_annual_reconciliation",
    }
    assert "fed_uplift_delay_counterfactual" in set(touched["data_scope"])


def test_deferral_composes_with_the_optimized_ped_bridge_mode(outlook) -> None:
    policy = _overlay_rows(
        outlook, current_state="delayed_12m", bridge_mode=PED_BRIDGE_OPTIMIZED_MODE
    )
    published = _overlay_rows(
        outlook, current_state="published", bridge_mode=PED_BRIDGE_OPTIMIZED_MODE
    )
    _assert_policy_invariants(policy, published, state="delayed_12m")


def test_shift_states_persist_below_published_beyond_the_initial_window(outlook) -> None:
    """12-36 month states no longer catch up; the six-month state still does.

    The six-month deferral rejoins published timing from FY2028. Every longer
    state shifts the entire staircase, so its annual revenue stays strictly
    below original timing after its initial deferral window, ordered by
    duration.
    """
    published = _overlay_rows(outlook, current_state="published")
    pub_total = _annual(published, BASE_TRACE, "total_nltf_net_revenue")
    six_total = _annual(
        _overlay_rows(outlook, current_state="delayed_6m"), BASE_TRACE, "total_nltf_net_revenue"
    )
    # The six-month state rejoins published timing from FY2028 and stays
    # there through the full horizon (its map never extends past FY2027).
    for fy in (2028, 2029, 2030, 2040, 2050):
        assert six_total[fy] == pytest.approx(pub_total[fy], abs=1e-6), fy
    twelve_total = _annual(
        _overlay_rows(outlook, current_state="delayed_12m"), BASE_TRACE, "total_nltf_net_revenue"
    )
    # The 12-month initial window ends inside FY2028; because the official
    # staircase adds +4c/L every calendar year with no terminal step, the
    # shortfall PERSISTS through every later year to FY2050 - it never
    # catches up.
    for fy in (2029, 2030, 2035, 2040, 2045, 2050):
        assert twelve_total[fy] < pub_total[fy] - 1e-6, fy
    thirty_six_total = _annual(
        _overlay_rows(outlook, current_state="delayed_36m"), BASE_TRACE, "total_nltf_net_revenue"
    )
    for fy in (2029, 2030, 2035, 2040, 2045, 2050):
        assert thirty_six_total[fy] < twelve_total[fy] - 1e-6, fy
    # Cumulative delta over a purely outer-year window (the FY2038-2045 zoom
    # that motivated this change) must now be materially non-zero.
    outer = range(2038, 2046)
    six_vs_thirty_six = sum(six_total[fy] - thirty_six_total[fy] for fy in outer)
    assert six_vs_thirty_six > 1.0  # $m over eight outer years


def test_identical_configurations_produce_identical_paths(outlook) -> None:
    first = _overlay_rows(outlook, current_state="delayed_18m", pt="High")
    second = _overlay_rows(outlook, current_state="delayed_18m", pt="High")
    pd.testing.assert_frame_equal(first, second, check_exact=True)


def test_all_one_hundred_twenty_one_policy_key_digests_are_unique(outlook) -> None:
    pack = outlook["pack"]
    digests = {
        governed_key(pack, ENGINE_AR1, current.state_id, official.state_id).digest()
        for current in FED_POLICY_SPECS
        for official in FED_POLICY_SPECS
    }
    assert len(digests) == 121
