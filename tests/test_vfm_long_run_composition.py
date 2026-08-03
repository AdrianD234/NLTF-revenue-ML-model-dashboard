"""VFM Base/Fast/Slow composition genuinely reaching FY2031-FY2050.

The composition overlay used to derive its June years from the econometric
drift/rate table, which stops at FY2030, so FY2031-FY2050 rows were never
visited and all three bases produced identical long-run class values. The pool
is shared; only the conventional/BEV/PHEV allocation may differ.

Every expected class value here is computed independently as

    frozen common pool  x  canonical source share

read straight from the governed CSV - never by calling the allocation helper
under test.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app
from model_dashboard.ev_uptake_levers import (
    DEFAULT_EV_UPTAKE_MODE,
    exact_vfm_share_coverage,
)
from model_dashboard.light_fleet_allocation import VFM_SCENARIO_BY_UPTAKE_BASIS
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey

@pytest.fixture(scope="module", autouse=True)
def _vfm_analyst_layers_enabled(vfm_analyst_layers_enabled):
    """This module protects the retained Fast/Slow composition backend, so it
    runs with the paused analyst surface deliberately switched on."""


ROOT = Path(__file__).resolve().parents[1]
AR1_DIR = Path("data") / "engine_ar1" / "current_revenue_outlook"
SHARE_SOURCE = ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv"
BASES = (DEFAULT_EV_UPTAKE_MODE, "MoT VFM fast", "MoT VFM slow")
LONG_RUN_FYS = (2031, 2035, 2040, 2045, 2050)
CLASS_KM = {
    "conventional": "light_ruc_net_km",
    "bev": "light_bev_ruc_net_km",
    "phev": "phev_ruc_net_km",
}
CLASS_REVENUE = {
    "conventional": "light_ruc_net_revenue",
    "bev": "light_bev_ruc_net_revenue",
    "phev": "phev_ruc_net_revenue",
}
UNTOUCHED = (
    "ped_vkt_per_capita", "ped_volume", "gross_ped_revenue", "net_fed_revenue",
    "heavy_ruc_net_km", "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_km", "heavy_bev_ruc_net_revenue",
    "net_mvr_revenue", "tuc_net_revenue",
)
TOLERANCE = 1e-6


def production_key(pack) -> RevenueScenarioComputationKey:
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
    return RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id=str(block.get("default_comparator_vintage_id") or "BEFU26"),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )


def values_for(pack, signature, key, scenario_name: str = "current_basecase") -> pd.Series:
    rows, *_ = app.cached_scenario_overlay_rows(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        key,
        pack,
    )
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_name"].astype(str).eq(scenario_name)
    ].copy()
    selected["FY"] = pd.to_numeric(selected["june_year"], errors="coerce")
    selected["numeric"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "numeric"])
    return selected.groupby(["series_id", "FY"])["numeric"].first()


@pytest.fixture(scope="module")
def ensemble():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


@pytest.fixture(scope="module")
def ar1():
    directory = ROOT / AR1_DIR
    if not directory.exists():
        pytest.skip("the AR(1) engine pack is not present")
    return load_revenue_outlook_pack(directory, repo_root=ROOT), revenue_outlook_signature(directory, ROOT)


@pytest.fixture(scope="module")
def by_basis(ensemble):
    pack, signature = ensemble
    key = production_key(pack)
    return {basis: values_for(pack, signature, key.replace(uptake_basis=basis)) for basis in BASES}


@pytest.fixture(scope="module")
def source_shares() -> pd.DataFrame:
    frame = pd.read_csv(SHARE_SOURCE).rename(
        columns={
            "light_ruc_conventional_share": "conventional",
            "light_ruc_bev_share": "bev",
            "light_ruc_phev_share": "phev",
        }
    )
    return frame[["scenario", "june_year", "conventional", "bev", "phev"]]


def canonical_share(source_shares: pd.DataFrame, basis: str, fy: int, component: str) -> float:
    scenario = VFM_SCENARIO_BY_UPTAKE_BASIS[basis]
    row = source_shares[
        source_shares["scenario"].astype(str).eq(scenario)
        & source_shares["june_year"].astype(int).eq(fy)
    ]
    assert not row.empty, f"{scenario} has no FY{fy} share"
    raw = {name: float(row[name].iloc[0]) for name in CLASS_KM}
    return raw[component] / sum(raw.values())


# ------------------------------------------------------------------- source
@pytest.mark.parametrize("basis", BASES)
def test_every_scenario_covers_fy2030_to_fy2050(source_shares, basis) -> None:
    scenario = VFM_SCENARIO_BY_UPTAKE_BASIS[basis]
    covered = set(
        source_shares[source_shares["scenario"].astype(str).eq(scenario)]["june_year"].astype(int)
    )
    assert set(range(2030, 2051)).issubset(covered), sorted(set(range(2030, 2051)) - covered)


def test_shares_are_finite_non_negative_and_sum_to_one(source_shares) -> None:
    values = source_shares[["conventional", "bev", "phev"]]
    assert np.isfinite(values.to_numpy()).all()
    assert (values >= 0).all().all()
    assert (values.sum(axis=1) - 1.0).abs().max() < 1e-5


def test_scenario_ids_come_from_the_governed_catalogue() -> None:
    for basis in BASES:
        assert basis in VFM_SCENARIO_BY_UPTAKE_BASIS
    assert set(VFM_SCENARIO_BY_UPTAKE_BASIS[b] for b in BASES) == {
        "Base_EV", "Fast_EV", "Slow_EV",
    }


def test_the_extension_is_bounded_by_the_source_coverage() -> None:
    """Past the table's last year there is no governed share to use."""
    covered = exact_vfm_share_coverage(DEFAULT_EV_UPTAKE_MODE, repo_root=ROOT)
    assert max(covered) == 2050
    assert 2051 not in covered


# --------------------------------------------------------- pool and classes
@pytest.mark.parametrize("fy", LONG_RUN_FYS)
def test_all_three_bases_share_one_light_pool(by_basis, fy) -> None:
    pools = [
        sum(float(values.get((series, fy), np.nan)) for series in CLASS_KM.values())
        for values in by_basis.values()
    ]
    assert all(np.isfinite(pool) for pool in pools)
    assert max(pools) - min(pools) <= TOLERANCE, (fy, pools)


@pytest.mark.parametrize("fy", LONG_RUN_FYS)
@pytest.mark.parametrize("basis", BASES)
def test_each_class_equals_common_pool_times_canonical_share(
    by_basis, source_shares, basis, fy
) -> None:
    pool = sum(
        float(by_basis[DEFAULT_EV_UPTAKE_MODE].get((series, fy), np.nan))
        for series in CLASS_KM.values()
    )
    for component, series in CLASS_KM.items():
        expected = pool * canonical_share(source_shares, basis, fy, component)
        observed = float(by_basis[basis].get((series, fy), np.nan))
        assert observed == pytest.approx(expected, abs=max(TOLERANCE, abs(expected) * 1e-9)), (
            basis, fy, component,
        )


@pytest.mark.parametrize("fy", LONG_RUN_FYS)
@pytest.mark.parametrize("basis", BASES)
def test_classes_sum_exactly_to_the_pool(by_basis, fy, basis) -> None:
    values = by_basis[basis]
    classes = [float(values.get((series, fy), np.nan)) for series in CLASS_KM.values()]
    pool = sum(
        float(by_basis[DEFAULT_EV_UPTAKE_MODE].get((series, fy), np.nan))
        for series in CLASS_KM.values()
    )
    assert sum(classes) == pytest.approx(pool, abs=TOLERANCE)


@pytest.mark.parametrize("fy", LONG_RUN_FYS)
def test_fast_and_slow_are_distinct_wherever_the_source_shares_differ(
    by_basis, source_shares, fy
) -> None:
    """The headline requirement: no FY2031+ collapse."""
    for component, series in CLASS_KM.items():
        fast_share = canonical_share(source_shares, "MoT VFM fast", fy, component)
        slow_share = canonical_share(source_shares, "MoT VFM slow", fy, component)
        fast = float(by_basis["MoT VFM fast"].get((series, fy), np.nan))
        slow = float(by_basis["MoT VFM slow"].get((series, fy), np.nan))
        if abs(fast_share - slow_share) <= 1e-9:
            continue
        assert fast != pytest.approx(slow, abs=TOLERANCE), (fy, component)


def test_vfm_base_reproduces_the_current_base_composition(by_basis) -> None:
    """Base must be a no-op: the pack's post-model mix already IS VFM Base."""
    pre = pd.read_csv(
        ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
        / "pre_vfm_long_run_extension_baseline.csv"
    )
    pre = pre[
        pre["engine"].eq("ensemble")
        & pre["uptake_basis"].eq(DEFAULT_EV_UPTAKE_MODE)
        & pre["scenario_name"].eq("current_basecase")
    ]
    assert not pre.empty
    compared = 0
    for _index, row in pre.iterrows():
        observed = by_basis[DEFAULT_EV_UPTAKE_MODE].get((row["series_id"], int(row["FY"])))
        if observed is None:
            continue
        compared += 1
        assert float(observed) == pytest.approx(float(row["value"]), abs=TOLERANCE), (
            row["series_id"], row["FY"],
        )
    assert compared > 100, "the preservation join is vacuous"


# ------------------------------------------------------------- stream scope
@pytest.mark.parametrize("series", UNTOUCHED)
def test_streams_outside_the_light_fleet_do_not_move(by_basis, series) -> None:
    for fy in LONG_RUN_FYS:
        base = by_basis[DEFAULT_EV_UPTAKE_MODE].get((series, fy))
        if base is None:
            continue
        for basis in BASES:
            assert float(by_basis[basis].get((series, fy), base)) == pytest.approx(
                float(base), abs=TOLERANCE
            ), (series, fy, basis)


def test_heavy_bev_stays_off_by_default(ensemble) -> None:
    pack, _signature = ensemble
    assert app._heavy_bev_transition_enabled(production_key(pack)) is False


def test_no_lambda_or_share_division_is_used() -> None:
    source = (ROOT / "model_dashboard" / "ev_uptake_levers.py").read_text(encoding="utf-8")
    composition = source[source.index("def apply_uptake_levers_to_chart_rows"):]
    assert "lambda_value" not in composition
    assert "migration_deduction" not in composition
    # Classes are pool x share, never conventional / share.
    assert "/ share" not in composition and "/share" not in composition


# --------------------------------------------------------- revenue and formulas
@pytest.mark.parametrize("fy", LONG_RUN_FYS)
@pytest.mark.parametrize("basis", BASES)
def test_class_revenue_equals_class_km_times_its_governed_rate(by_basis, basis, fy) -> None:
    """The rate is the one already embedded in the governed post-model rows."""
    base_values = by_basis[DEFAULT_EV_UPTAKE_MODE]
    for component, km_series in CLASS_KM.items():
        revenue_series = CLASS_REVENUE[component]
        base_km = float(base_values.get((km_series, fy), np.nan))
        base_revenue = float(base_values.get((revenue_series, fy), np.nan))
        if not np.isfinite(base_km) or base_km <= 0:
            continue
        rate = base_revenue / base_km
        km = float(by_basis[basis].get((km_series, fy), np.nan))
        revenue = float(by_basis[basis].get((revenue_series, fy), np.nan))
        assert revenue == pytest.approx(km * rate, rel=1e-9), (basis, fy, component)


def line_values_for(pack, signature, key) -> pd.Series:
    """Line-reconciliation values: the frame that carries every formula leaf.

    Chart rows expose only the plotted series, so they can close exactly one
    governed identity. Formula closure has to be checked against the spine.
    """
    line, _residuals, _stack, _bridge = app.cached_aligned_scenario_detail_frames(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        key,
        pack,
    )
    selected = line[line["scenario_name"].astype(str).eq("current_basecase")].copy()
    selected["FY"] = pd.to_numeric(selected["FY"], errors="coerce")
    selected["numeric"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "numeric"])
    return selected.groupby(["series_id", "FY"])["numeric"].first()


@pytest.fixture(scope="module")
def line_by_basis(ensemble):
    pack, signature = ensemble
    key = production_key(pack)
    return {
        basis: line_values_for(pack, signature, key.replace(uptake_basis=basis))
        for basis in BASES
    }


@pytest.mark.parametrize("fy", LONG_RUN_FYS)
@pytest.mark.parametrize("basis", BASES)
def test_aggregates_close_through_formula_definitions(line_by_basis, basis, fy) -> None:
    values = line_by_basis[basis]
    checked = 0
    for definition in FORMULA_DEFINITIONS:
        output = str(definition["output_series_id"])
        observed = values.get((output, fy))
        if observed is None:
            continue
        total = 0.0
        complete = True
        for term, sign in definition["terms"]:
            component = values.get((str(term), fy))
            if component is None:
                complete = False
                break
            total += float(sign) * float(component)
        if not complete:
            continue
        checked += 1
        assert float(observed) == pytest.approx(total, abs=TOLERANCE), (basis, fy, output)
    assert checked >= 3, "formula closure check is vacuous"


# ----------------------------------------------------------------- envelope
def test_the_structural_envelope_now_carries_through_fy2050(ensemble) -> None:
    pack, signature = ensemble
    key = production_key(pack)
    view = app.cached_revenue_outlook_view(
        signature, "Light RUC revenue", "june_year", "Current planned path",
        ("Actual", "Current finalist Base case"),
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE, key, pack,
    )
    band = view["cone_band"]
    assert not band.empty
    last = int(str(band["period"].iloc[-1]).replace("FY", ""))
    assert last == 2050, f"the envelope still stops at FY{last}"
    assert (band["upper"] >= band["lower"]).all()


def test_the_envelope_is_min_and_max_of_fast_and_slow(ensemble, by_basis) -> None:
    pack, signature = ensemble
    key = production_key(pack)
    view = app.cached_revenue_outlook_view(
        signature, "Light RUC revenue", "june_year", "Current planned path",
        ("Actual", "Current finalist Base case"),
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE, key, pack,
    )
    band = view["cone_band"].set_index("period")
    checked = 0
    for fy in LONG_RUN_FYS:
        label = f"FY{fy}"
        if label not in band.index:
            continue
        fast = float(by_basis["MoT VFM fast"].get(("light_ruc_net_revenue", fy), np.nan))
        slow = float(by_basis["MoT VFM slow"].get(("light_ruc_net_revenue", fy), np.nan))
        assert float(band.loc[label, "lower"]) == pytest.approx(min(fast, slow), abs=TOLERANCE)
        assert float(band.loc[label, "upper"]) == pytest.approx(max(fast, slow), abs=TOLERANCE)
        checked += 1
    assert checked >= 3, "the envelope parity check is vacuous"


# ------------------------------------------------------------------- caches
def test_switching_basis_and_returning_restores_identical_values(ensemble) -> None:
    pack, signature = ensemble
    key = production_key(pack)
    first = values_for(pack, signature, key)
    for basis in ("MoT VFM fast", "MoT VFM slow"):
        values_for(pack, signature, key.replace(uptake_basis=basis))
    returned = values_for(pack, signature, key)
    pd.testing.assert_series_equal(first, returned)


def test_the_official_comparator_alone_does_not_move_the_vfm_paths(ensemble) -> None:
    pack, signature = ensemble
    key = production_key(pack)
    befu = values_for(pack, signature, key.replace(uptake_basis="MoT VFM fast"))
    mbu = values_for(
        pack, signature,
        key.replace(uptake_basis="MoT VFM fast", official_comparator_vintage_id="MBU26"),
    )
    for fy in LONG_RUN_FYS:
        for series in CLASS_KM.values():
            assert float(befu.get((series, fy), np.nan)) == pytest.approx(
                float(mbu.get((series, fy), np.nan)), abs=TOLERANCE
            )


def test_switching_schedule_rebuilds_the_pool_then_applies_the_shares(ensemble) -> None:
    pack, signature = ensemble
    key = production_key(pack)
    unblended = key.replace(
        long_run_transition_schedule_id=app.UNBLENDED_SCHEDULE_ID, long_run_shape_vintage_id=""
    )
    for candidate in (key, unblended):
        fast = values_for(pack, signature, candidate.replace(uptake_basis="MoT VFM fast"))
        slow = values_for(pack, signature, candidate.replace(uptake_basis="MoT VFM slow"))
        pool_fast = sum(float(fast.get((s, 2040), np.nan)) for s in CLASS_KM.values())
        pool_slow = sum(float(slow.get((s, 2040), np.nan)) for s in CLASS_KM.values())
        assert pool_fast == pytest.approx(pool_slow, abs=TOLERANCE)
        assert float(fast.get(("light_ruc_net_km", 2040), np.nan)) != pytest.approx(
            float(slow.get(("light_ruc_net_km", 2040), np.nan)), abs=TOLERANCE
        )


# ------------------------------------------------------------- both engines
def test_the_ar1_engine_satisfies_the_same_contract(ar1, source_shares) -> None:
    pack, signature = ar1
    key = production_key(pack)
    by_engine = {basis: values_for(pack, signature, key.replace(uptake_basis=basis)) for basis in BASES}
    for fy in LONG_RUN_FYS:
        pool = sum(
            float(by_engine[DEFAULT_EV_UPTAKE_MODE].get((series, fy), np.nan))
            for series in CLASS_KM.values()
        )
        for basis in BASES:
            classes = [float(by_engine[basis].get((series, fy), np.nan)) for series in CLASS_KM.values()]
            assert sum(classes) == pytest.approx(pool, abs=TOLERANCE)
            for component, series in CLASS_KM.items():
                expected = pool * canonical_share(source_shares, basis, fy, component)
                assert float(by_engine[basis].get((series, fy), np.nan)) == pytest.approx(
                    expected, abs=max(TOLERANCE, abs(expected) * 1e-9)
                )
        assert float(by_engine["MoT VFM fast"].get(("light_ruc_net_km", fy), np.nan)) != pytest.approx(
            float(by_engine["MoT VFM slow"].get(("light_ruc_net_km", fy), np.nan)), abs=TOLERANCE
        )


# ------------------------------------------- uncertainty pack must not move
def test_the_uncertainty_band_rows_are_numerically_unchanged() -> None:
    """The bands stay centred on the unchanged Current Base path."""
    frozen = pd.read_csv(
        ROOT / "artifacts" / "revenue_outlook_layered_uncertainty" / "uncertainty_band_values.csv"
    )
    live = pd.read_parquet(
        ROOT / "data" / "revenue_outlook_uncertainty" / "uncertainty_band_rows.parquet"
    )
    assert len(frozen) == len(live)
    keys = ["series_id", "FY"]
    frozen_sorted = frozen.sort_values(keys).reset_index(drop=True)
    live_sorted = live.sort_values(keys).reset_index(drop=True)
    for column in ("central", "lower80", "lower50", "upper50", "upper80"):
        pd.testing.assert_series_equal(
            frozen_sorted[column], live_sorted[column], check_names=False, rtol=0, atol=1e-9
        )
