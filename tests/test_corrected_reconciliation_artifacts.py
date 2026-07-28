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


def test_both_comparisons_present_and_complete(decomposition) -> None:
    for comparison in ("policy_normalised", "default_ui"):
        subset = decomposition[decomposition["comparison"].eq(comparison)]
        assert set(subset["fy"].astype(int)) == FYS, comparison


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
    """Delayed-vs-published mixing would collapse the two comparisons together."""
    merged = decomposition.pivot_table(index="fy", columns="comparison", values="total_nltf_gap")
    # FY2027 is the policy year: the two comparisons MUST differ there...
    assert abs(merged.at[2027, "policy_normalised"] - merged.at[2027, "default_ui"]) > 1.0
    # ...and agree everywhere else, because both sides shift policy together.
    for fy in sorted(FYS - {2027}):
        assert merged.at[fy, "policy_normalised"] == pytest.approx(merged.at[fy, "default_ui"], abs=1e-6)

    policy = pd.read_csv(OUT / "policy_state_comparison.csv")
    nltf = policy[policy["stream"].eq("total_nltf")]
    moved = nltf[nltf["current_policy_effect"].abs() > TOL]["fy"].astype(int).tolist()
    assert moved == [2027], f"current delayed policy moved {moved}, expected [2027]"


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
