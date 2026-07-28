"""The corrected Workstream A artifacts stay closed, separate and honest.

These gates run against the COMMITTED artifacts, so a regeneration that stops
closing, conflates the two policy comparisons, or starts absorbing the
published-source residual fails in CI rather than in review.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "mbu26_reconciliation_corrected"
TOL = 1e-6
FYS = {2026, 2027, 2028, 2029, 2030}


@pytest.fixture(scope="module")
def decomposition() -> pd.DataFrame:
    return pd.read_csv(OUT / "financial_decomposition.csv")


def test_every_expected_artifact_is_committed() -> None:
    expected = {
        "gap_by_stream_fy.csv",
        "financial_decomposition.csv",
        "activity_bridge.csv",
        "policy_state_comparison.csv",
        "driver_availability_matrix.csv",
        "formula_reconciliation.csv",
        "corrected_reconciliation_report.md",
        "superseded_artifact_register.csv",
    }
    assert expected <= {path.name for path in OUT.iterdir()}


COMPARISONS = ("policy_normalised", "actual_default_ui", "policy_aligned_delayed")


def test_all_three_comparisons_present_and_complete(decomposition) -> None:
    assert set(decomposition["comparison"]) == set(COMPARISONS)
    for comparison in COMPARISONS:
        subset = decomposition[decomposition["comparison"].eq(comparison)]
        assert set(subset["fy"].astype(int)) == FYS, comparison
    # "default_ui" alone was the old mislabel for delayed-vs-delayed; it must
    # not reappear.
    assert "default_ui" not in set(decomposition["comparison"])


def test_decomposition_closes_and_residual_is_numerical_only(decomposition) -> None:
    assert decomposition["numerical_residual"].abs().max() <= TOL
    assert decomposition["ruc_internal_residual"].abs().max() <= TOL
    # The NLTF gap must equal its named components exactly.
    recomputed = (
        decomposition["net_fed_gap"]
        + decomposition["total_ruc_gap"]
        + decomposition["net_mvr_gap"]
        + decomposition["tuc_other_fixed_gap"]
    )
    assert (decomposition["total_nltf_gap"] - recomputed).abs().max() <= TOL


def test_published_source_residual_is_reported_not_absorbed(decomposition) -> None:
    """FY2027's ~0.627 spine inconsistency must stay visible as its own column."""
    fy2027 = decomposition[decomposition["fy"].eq(2027)]
    assert (
        fy2027["official_published_source_residual"].abs() > 0.6
    ).all(), "the known FY2027 published-source residual disappeared - was it absorbed?"
    formulas = pd.read_csv(OUT / "formula_reconciliation.csv")
    official_ruc = formulas[
        formulas["state"].str.startswith("official")
        & formulas["formula"].str.startswith("total_ruc")
        & formulas["fy"].eq(2027)
    ]
    assert official_ruc["status"].eq("published_source_residual_reported").all()
    # Current states have no such exemption: everything must close.
    current = formulas[formulas["state"].str.startswith("current")]
    assert current["residual"].abs().max() <= TOL
    assert current["status"].eq("closes").all()


def test_policy_states_are_not_conflated(decomposition) -> None:
    """The displayed policy-basis mismatch must never read as a model gap."""
    merged = decomposition.pivot_table(index="fy", columns="comparison", values="total_nltf_gap")
    # FY2027 is the policy year: all three comparisons MUST differ there...
    assert abs(merged.at[2027, "policy_normalised"] - merged.at[2027, "policy_aligned_delayed"]) > 1.0
    assert abs(merged.at[2027, "actual_default_ui"] - merged.at[2027, "policy_aligned_delayed"]) > 100.0
    # ...and agree everywhere else, where no policy state moves anything.
    for fy in sorted(FYS - {2027}):
        for comparison in COMPARISONS[1:]:
            assert merged.at[fy, "policy_normalised"] == pytest.approx(
                merged.at[fy, comparison], abs=1e-6
            ), (fy, comparison)

    policy = pd.read_csv(OUT / "policy_state_comparison.csv")
    nltf = policy[policy["stream"].eq("total_nltf")].set_index("fy")
    moved = nltf[nltf["current_delay_effect"].abs() > TOL].index.astype(int).tolist()
    assert moved == [2027], f"current delayed policy moved {moved}, expected [2027]"

    # Exact policy identities, every FY and stream.
    assert policy["identity_default_ui_residual"].abs().max() <= TOL
    assert policy["identity_aligned_residual"].abs().max() <= TOL
    recomputed_default = policy["policy_normalised_gap"] + policy["current_delay_effect"]
    assert (policy["actual_default_ui_gap"] - recomputed_default).abs().max() <= TOL
    recomputed_aligned = recomputed_default - policy["official_delay_effect"]
    assert (policy["policy_aligned_delayed_gap"] - recomputed_aligned).abs().max() <= TOL

    # The FY2027 displayed gap is dominated by the policy-basis mismatch:
    # roughly -$402m displayed, of which ~-$343m is the current delay effect.
    assert nltf.at[2027, "actual_default_ui_gap"] < -350.0
    assert abs(nltf.at[2027, "default_ui_policy_basis_mismatch"]) > 300.0
    assert abs(nltf.at[2027, "policy_normalised_gap"]) < 100.0


def test_actual_default_ui_matches_the_real_gold_path_key(decomposition) -> None:
    """actual_default_ui must equal the app under current=delayed_6m, official=published.

    Same entry point and key shape as scripts/build_gold_path_audit.py, so the
    committed comparison can never drift from what the dashboard displays.
    """
    import os

    os.environ.setdefault("DASHBOARD_ENGINE_DEFAULT", "ar1")
    import app
    from model_dashboard.revenue_outlook import PED_BRIDGE_DEFAULT_MODE, load_revenue_outlook_pack

    pack = load_revenue_outlook_pack(ROOT / "data/engine_ar1/current_revenue_outlook", repo_root=ROOT)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    key = (app.DEFAULT_EV_UPTAKE_MODE, (), (), app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED, False, False)
    rows, *_ = app.cached_scenario_overlay_rows((), sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack)

    def annual(role: str, fy: int) -> float:
        mask = (
            rows["time_grain"].astype(str).eq("june_year")
            & rows["scenario_role"].astype(str).eq(role)
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        )
        return float(pd.to_numeric(rows.loc[mask, "value"], errors="coerce").dropna().iloc[0])

    committed = decomposition[decomposition["comparison"].eq("actual_default_ui")].set_index("fy")
    for fy in sorted(FYS):
        runtime_gap = annual("basecase", fy) - annual("official_comparator", fy)
        assert committed.at[fy, "total_nltf_gap"] == pytest.approx(runtime_gap, abs=TOL), fy


def test_population_semantics_are_honest() -> None:
    bridge = pd.read_csv(OUT / "activity_bridge.csv")
    population = bridge[bridge["measure"].eq("population")]
    assert population["basis"].str.contains("current_population_direct_scenario_input").all()
    assert population["basis"].str.contains("derived_from_official_outputs_not_independently_published").all()
    pack_stage = bridge[bridge["measure"].eq("population_implied_pack_stage")]
    # The gated cross-check: pack-stage implied matches the direct input.
    checked = pack_stage.dropna(subset=["current", "gap"])
    assert len(checked) >= 4
    direct = population.set_index("fy")["current"]
    for row in checked.itertuples():
        assert abs(row.gap) / direct.loc[row.fy] <= 1e-3
    # The post-macro ratio is reported as a P1.2 finding, never gated here.
    post_macro = bridge[bridge["measure"].eq("population_implied_post_macro")]
    assert post_macro["basis"].str.contains("P1.2").all()


def test_unavailable_drivers_receive_no_dollar_attribution() -> None:
    drivers = pd.read_csv(OUT / "driver_availability_matrix.csv")
    unavailable = drivers[drivers["availability"].eq("unavailable_official_input")]
    assert len(unavailable) >= 4
    assert unavailable["source_or_note"].str.contains("NO dollar attribution").all()
    assert not {"gap_nzd", "attribution_nzd", "dollar_value"} & set(drivers.columns)


def test_superseded_register_names_the_old_outputs() -> None:
    register = pd.read_csv(OUT / "superseded_artifact_register.csv")
    assert len(register) >= 13
    assert register["status"].eq("superseded_by_corrected_reconciliation").all()
    assert register["artifact"].str.startswith("outputs/mbu26_reconciliation/").all()


def test_generator_touches_no_production_pack() -> None:
    source = (ROOT / "scripts" / "build_corrected_mbu26_reconciliation.py").read_text(encoding="utf-8")
    for banned in ("to_parquet", "data/current_revenue_outlook", "data/engine_ar1/current_revenue_outlook/revenue_chart_rows"):
        writes = [line for line in source.splitlines() if banned in line and ("write" in line or "to_csv" in line)]
        assert not writes, writes
    assert 'OUT = ROOT / "artifacts" / "mbu26_reconciliation_corrected"' in source
