"""The committed P1.2 evidence stays complete, closed and honest.

Gates over artifacts/p1_direct_macro_replay/ so a regeneration that hides a
parity failure, loses a lineage column, or lets the Base case move fails in
CI rather than in review.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "p1_direct_macro_replay"
BASE = "current_basecase"
COMPARISON = "current_comparison_1"


def test_every_expected_artifact_is_committed() -> None:
    expected = {
        "direct_replay_predictions.csv",
        "factor_replay_predictions.csv",
        "replay_parity_audit.csv",
        "missing_input_audit.csv",
        "scenario_replay_lineage.csv",
        "revenue_impact_fy.csv",
        "p1_2_report.md",
    }
    assert expected <= {path.name for path in OUT.iterdir()}


def test_parity_audit_covers_both_scenarios_and_direct_is_authoritative() -> None:
    parity = pd.read_csv(OUT / "replay_parity_audit.csv")
    assert set(parity["scenario_name"]) == {BASE, COMPARISON}
    assert parity["authoritative"].eq("direct_replay").all()
    assert {"quarterly", "june_year"} <= set(parity["time_grain"])


def test_base_parity_is_exact_and_the_comparison_correction_is_real() -> None:
    parity = pd.read_csv(OUT / "replay_parity_audit.csv")
    base = parity[parity["scenario_name"].eq(BASE)]
    assert base["factor_rel_deviation"].abs().max() == 0.0, (
        "the direct Base pair IS the legacy pair; any deviation means the "
        "refactor moved the Base case"
    )
    comparison = parity[parity["scenario_name"].eq(COMPARISON)]
    wrong = comparison[comparison["parity"].eq("transfer_was_wrong")]
    # The correction must exist (the transfer WAS wrong for nonlinear models)
    # and stay bounded (PED quarterly measured at 0.287% worst).
    assert len(wrong) > 0, "no corrected cells - the defect this PR fixes has vanished"
    assert comparison["factor_rel_deviation"].max() < 0.005
    ped = comparison[comparison["series_id"].eq("ped_vkt_per_capita")]
    assert ped["factor_rel_deviation"].max() > 1e-4, (
        "the PED transfer error is the motivating measurement; losing it "
        "means the audit is no longer comparing what it claims"
    )


def test_light_ruc_transfer_was_accidentally_exact_and_is_recorded_as_such() -> None:
    """The one series where factor transfer WAS fine - because that model is
    linear in the changed inputs. Recording this stops the parity audit from
    being read as 'everything was wrong'."""
    parity = pd.read_csv(OUT / "replay_parity_audit.csv")
    light = parity[
        parity["scenario_name"].eq(COMPARISON)
        & parity["series_id"].eq("light_ruc_net_km")
        & parity["time_grain"].eq("quarterly")
    ]
    assert not light.empty
    assert light["factor_rel_deviation"].max() < 1e-9


def test_missing_input_audit_is_complete() -> None:
    missing = pd.read_csv(OUT / "missing_input_audit.csv")
    assert len(missing) == 6  # 2 scenarios x 3 streams
    assert missing["status"].eq("complete").all()
    assert missing["non_numeric_forecasts"].eq(0).all()


def test_lineage_carries_provenance_and_no_fallbacks() -> None:
    lineage = pd.read_csv(OUT / "scenario_replay_lineage.csv")
    for column in (
        "scenario_name", "scenario_role", "stream", "period", "engine",
        "input_workbook_sha256", "drivers_changed", "raw_model_output",
        "post_macro_output", "replay_status", "error_class", "fallback_used",
        "commit_sha", "scenario_input_artifact_sha256",
    ):
        assert column in lineage.columns, column
    assert lineage["replay_status"].eq("replayed").all()
    assert lineage["fallback_used"].eq("none").all()
    assert lineage["scenario_input_artifact_sha256"].str.len().eq(64).all()


def test_revenue_impact_shows_base_unchanged_and_comparison_corrected() -> None:
    impact = pd.read_csv(OUT / "revenue_impact_fy.csv")
    base = impact[impact["scenario_name"].eq(BASE)]
    assert base["correction_millions"].abs().max() <= 1e-9
    comparison = impact[impact["scenario_name"].eq(COMPARISON)]
    total = comparison[comparison["series_id"].eq("total_nltf_net_revenue")]
    assert total["correction_millions"].abs().max() > 0.01, (
        "the correction must be material enough to be the point of the change"
    )
    assert total["correction_millions"].abs().max() < 50.0, (
        "a correction this large would mean the replay itself is wrong"
    )


def test_report_names_the_remaining_policy_layer_exception() -> None:
    report = (OUT / "p1_2_report.md").read_text(encoding="utf-8")
    assert "policy_pair_transfer_on_comparison_pending_followup" in report
    assert "0.000502" in report
    assert "direct replay" in report.lower()
