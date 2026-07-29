"""P1.2: every governed scenario uses its own Treasury replay.

The retired behaviour transferred Base-derived macro factors onto the
comparison in output space - exact only for models linear in the changed
inputs, and the current comparison differs in BOTH population and GDP paths
while PED is recursive and Heavy RUC is a GBM ensemble. These gates prove the
per-scenario construction, the fail-closed contour, determinism, and that
nothing outside the current-model layer is touched.

Module-scoped fixtures: the direct replay is expensive, so it runs once here.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.fuel_price_scenario import (
    DirectTreasuryScenarioReplayResult,
    apply_treasury_macro_to_chart_rows,
    direct_shadow_scenario_name,
    run_direct_treasury_scenario_replay,
    run_treasury_baseline_macro_replay,
)
from model_dashboard.treasury_macro_paths import (
    apply_treasury_baseline_macro_path,
    apply_treasury_macro_path_to_scenarios,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "scenario_inputs" / "scenario_input_wide.parquet"
CHART_PATH = ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "revenue_chart_rows.parquet"
BASE = "current_basecase"
COMPARISON = "current_comparison_1"


@pytest.fixture(scope="module")
def wide() -> pd.DataFrame:
    return pd.read_parquet(INPUT_PATH)


@pytest.fixture(scope="module")
def direct(wide) -> DirectTreasuryScenarioReplayResult:
    return run_direct_treasury_scenario_replay(wide, ROOT, engine="ar1")


@pytest.fixture(scope="module")
def legacy(wide):
    return run_treasury_baseline_macro_replay(wide, ROOT, engine="ar1")


# ------------------------------------------------- input-space adjustment
def test_base_transform_is_reproduced_bit_for_bit(wide) -> None:
    old = apply_treasury_baseline_macro_path(wide, ROOT)
    new = apply_treasury_macro_path_to_scenarios(wide, ROOT)
    base_mask = new["scenario_name"].astype(str).eq(BASE)
    for column in (
        "real_gdp_sa_nzd", "population", "real_gdp_per_capita_nzd",
        "log_population", "diff_log_real_gdp", "gdp_petrol_interaction",
        "log_real_gdp", "gdp_light_ruc_price_interaction",
    ):
        assert old.loc[base_mask, column].astype(str).equals(
            new.loc[base_mask, column].astype(str)
        ), column


def test_every_scenario_input_differential_is_preserved_exactly(wide) -> None:
    """The comparison's population AND GDP differentials survive unchanged."""
    new = apply_treasury_macro_path_to_scenarios(wide, ROOT)

    def path(frame, scenario, stream, column):
        scoped = frame[
            frame["scenario_name"].astype(str).eq(scenario)
            & frame["stream"].astype(str).eq(stream)
        ]
        return scoped.set_index("canonical_period")[column].astype(float)

    for stream, column in (("PED", "population"), ("LIGHT_RUC", "real_gdp_sa_nzd")):
        legacy_ratio = path(wide, COMPARISON, stream, column) / path(wide, BASE, stream, column)
        adjusted_ratio = path(new, COMPARISON, stream, column) / path(new, BASE, stream, column)
        np.testing.assert_allclose(
            adjusted_ratio.to_numpy(), legacy_ratio.to_numpy(), rtol=1e-12, atol=1e-12
        )
    # And the adjustment genuinely moved the comparison (non-vacuity).
    shift = (
        path(new, COMPARISON, "PED", "population")
        / path(wide, COMPARISON, "PED", "population")
    )
    assert (shift - 1.0).abs().max() > 1e-3


def test_prices_are_never_touched_for_any_scenario(wide) -> None:
    """Price INPUTS are inviolate; GDP-price interaction FEATURES legitimately
    move because their GDP half moved. The library's own predicate defines
    the boundary, so this test cannot drift from the enforced postcondition."""
    from model_dashboard.treasury_macro_paths import _is_price_input_column

    new = apply_treasury_macro_path_to_scenarios(wide, ROOT)
    price_columns = [c for c in wide.columns if _is_price_input_column(c)]
    assert "real_petrol_price_cents_per_litre" in price_columns
    assert "gdp_petrol_interaction" not in price_columns
    for column in price_columns:
        assert new[column].equals(wide[column]), column


def test_a_scenario_missing_a_stream_fails_closed(wide) -> None:
    damaged = wide[
        ~(
            wide["scenario_name"].astype(str).eq(COMPARISON)
            & wide["stream"].astype(str).eq("PED")
        )
    ]
    with pytest.raises(ValueError, match="missing streams"):
        apply_treasury_macro_path_to_scenarios(damaged, ROOT)


# --------------------------------------------------------- direct replay
def test_each_governed_scenario_replays_against_its_own_shadow(direct) -> None:
    assert set(direct.scenario_names) == {BASE, COMPARISON}
    replayed = set(direct.replay.future_forecasts["scenario_name"].astype(str))
    for scenario in direct.scenario_names:
        assert scenario in replayed
        assert direct_shadow_scenario_name(scenario) in replayed


def test_factors_are_keyed_by_scenario_and_differ_where_models_are_nonlinear(direct) -> None:
    """Under the AR1 engine only Heavy RUC responds nonlinearly.

    The AR1 PED and Light RUC models are multiplicative in the changed
    inputs, so their factor transfer was accidentally exact - asserted below
    as a documented fact, not tolerated silently. The ensemble engine's PED
    is convex-nonlinear (0.287% transfer error) and that claim is gated on
    the committed evidence in test_p1_direct_macro_replay_artifacts.py.
    """
    quarterly = direct.baseline_macro_quarterly_factors
    assert set(quarterly["scenario_name"].astype(str)) == set(direct.scenario_names)
    pivot = quarterly.pivot_table(
        index=["series_id", "period"], columns="scenario_name", values="factor"
    ).dropna()
    deviation = (pivot[COMPARISON] - pivot[BASE]).abs()
    by_series = deviation.groupby(level=0).max()
    # Nonlinear under AR1: the per-scenario replay must genuinely differ from
    # Base's. If this collapses to equality the "per-scenario" replay has
    # silently degenerated into a copy of Base.
    assert by_series["heavy_ruc_net_km"] > 1e-6
    # Linear under AR1: transfer-exact, recorded so a future engine change
    # that breaks this shows up as a signal rather than noise.
    assert by_series["ped_vkt_per_capita"] < 1e-9
    assert by_series["light_ruc_net_km"] < 1e-9


def test_base_factors_match_the_legacy_pair_exactly(direct, legacy) -> None:
    """The refactor is value-neutral for Base by construction, not accident."""
    merged = direct.baseline_macro_quarterly_factors[
        direct.baseline_macro_quarterly_factors["scenario_name"].eq(BASE)
    ].merge(
        legacy.baseline_macro_quarterly_factors,
        on=["series_id", "period"],
        suffixes=("_direct", "_legacy"),
    )
    assert len(merged) == len(legacy.baseline_macro_quarterly_factors)
    assert (merged["factor_direct"] == merged["factor_legacy"]).all()


def test_direct_replay_is_deterministic(direct, wide) -> None:
    rerun = run_direct_treasury_scenario_replay(wide, ROOT, engine="ar1")
    key = ["scenario_name", "series_id", "time_grain", "period"]
    first = direct.baseline_macro_quarterly_factors.sort_values(key).reset_index(drop=True)
    second = rerun.baseline_macro_quarterly_factors.sort_values(key).reset_index(drop=True)
    assert first["factor"].equals(second["factor"])
    annual_first = direct.baseline_macro_annual_factors.sort_values(key).reset_index(drop=True)
    annual_second = rerun.baseline_macro_annual_factors.sort_values(key).reset_index(drop=True)
    assert annual_first["factor"].equals(annual_second["factor"])


def test_a_scenario_with_no_input_rows_fails_closed(wide) -> None:
    damaged = wide[~wide["scenario_name"].astype(str).eq(COMPARISON)].copy()
    # Re-add the scenario name with zero rows via the role column is not
    # possible; instead prove the runner never invents a scenario: only the
    # scenarios present in the inputs are replayed.
    result = run_direct_treasury_scenario_replay(damaged, ROOT, engine="ar1")
    assert result.scenario_names == (BASE,)


def test_lineage_records_every_scenario_stream_quarter(direct) -> None:
    lineage = direct.scenario_replay_lineage
    assert set(lineage["scenario_name"].astype(str)) == set(direct.scenario_names)
    assert set(lineage["stream"].astype(str)) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    assert lineage["replay_status"].eq("replayed").all()
    assert lineage["fallback_used"].eq("none").all()
    # The macro adjustment must be visible in the recorded driver deltas.
    assert lineage["drivers_changed"].str.len().gt(0).any()


# ---------------------------------------------------------- overlay gates
@pytest.fixture(scope="module")
def chart() -> pd.DataFrame:
    return pd.read_parquet(CHART_PATH)


def test_base_factors_are_never_silently_reused_for_another_scenario(chart, legacy) -> None:
    with pytest.raises(ValueError, match="cannot be applied to"):
        apply_treasury_macro_to_chart_rows(chart, legacy)


def test_missing_scenario_factor_fails_closed_instead_of_keeping_legacy(chart, direct) -> None:
    damaged_quarterly = direct.baseline_macro_quarterly_factors[
        ~(
            direct.baseline_macro_quarterly_factors["scenario_name"].eq(COMPARISON)
            & direct.baseline_macro_quarterly_factors["series_id"].eq("light_ruc_net_km")
            & direct.baseline_macro_quarterly_factors["period"].eq("2030Q4")
        )
    ]
    damaged = dataclasses.replace(
        direct, baseline_macro_quarterly_factors=damaged_quarterly
    )
    with pytest.raises(ValueError, match="No Treasury macro factor"):
        apply_treasury_macro_to_chart_rows(chart, damaged)


def test_official_and_actual_rows_are_untouched(chart, direct) -> None:
    adjusted, _ = apply_treasury_macro_to_chart_rows(chart, direct)
    protected = chart["scenario_role"].fillna("").astype(str).isin(
        {"actual", "official_comparator"}
    )
    pd.testing.assert_series_equal(
        adjusted.loc[protected, "value"].reset_index(drop=True),
        chart.loc[protected, "value"].reset_index(drop=True),
        check_names=False,
        check_dtype=False,
    )


def test_h20_availability_survives_the_direct_overlay(chart, direct) -> None:
    adjusted, _ = apply_treasury_macro_to_chart_rows(chart, direct)
    for scenario in (BASE, COMPARISON):
        quarters = adjusted[
            adjusted["scenario_name"].astype(str).eq(scenario)
            & adjusted["time_grain"].astype(str).eq("quarterly")
        ]["period"].astype(str)
        assert quarters.max() == "2030Q4"
        assert "2030Q3" in set(quarters)
        assert not quarters.str.startswith("2031").any()


def test_comparison_rows_use_their_own_factors_not_bases(chart, direct) -> None:
    adjusted, audit = apply_treasury_macro_to_chart_rows(chart, direct)
    quarterly = direct.baseline_macro_quarterly_factors
    pivot = quarterly.pivot_table(
        index=["series_id", "period"], columns="scenario_name", values="factor"
    ).dropna()
    # Pick the cell where the scenarios differ most AMONG the H1-H20 quarters
    # the chart actually displays (the factor grid spans the full replay
    # horizon, but the overlay only ever touches displayed rows).
    displayed = set(
        chart[chart["time_grain"].astype(str).eq("quarterly")]["period"].astype(str)
    )
    pivot = pivot[pivot.index.get_level_values("period").isin(displayed)]
    gap = (pivot[COMPARISON] - pivot[BASE]).abs()
    series_id, period = gap.idxmax()
    scoped = audit[
        audit["scenario_name"].eq(COMPARISON)
        & audit["series_id"].eq(series_id)
        & audit["period"].eq(period)
    ]
    assert len(scoped) == 1
    applied = float(scoped["factor"].iloc[0])
    assert applied == pytest.approx(float(pivot.loc[(series_id, period), COMPARISON]))
    assert applied != pytest.approx(float(pivot.loc[(series_id, period), BASE]))
