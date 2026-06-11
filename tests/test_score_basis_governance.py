from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack
from model_dashboard.labels import OVERVIEW_STRESS_BUCKET_ORDER, STRESS_BUCKET_ORDER
from model_dashboard.plots import plot_ensemble_composition
from model_dashboard.score_basis import (
    OPERATIONAL_SCORE_BASIS,
    PAPER_SCORE_BASIS,
    project_scenario_comparison_frame,
    project_score_basis_frame,
)
from app import build_candidate_landscape_frame, overview_stress_frame


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
EXPECTED_BALANCED_FRONTIER_COUNTS = {"PED VKT per capita": 132, "Light RUC volume": 136, "Heavy RUC volume": 132}


@pytest.fixture(scope="session")
def evidence_pack():
    return load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, ROOT)


def test_v6_default_score_basis_is_paper_style(evidence_pack) -> None:
    finalists = evidence_pack.data["recommended"].set_index("stream_label")
    assert set(finalists["score_basis"]) == {PAPER_SCORE_BASIS}
    # vNext finalists promoted 2026-06: paper-style horizon-mean MAPE values.
    assert float(finalists.loc["PED VKT per capita", "quarterly_mape"]) == pytest.approx(3.131663, abs=0.001)
    assert float(finalists.loc["Light RUC volume", "quarterly_mape"]) == pytest.approx(5.363207, abs=0.001)
    assert float(finalists.loc["Heavy RUC volume", "quarterly_mape"]) == pytest.approx(2.288749, abs=0.001)
    assert str(finalists.loc["Light RUC volume", "model"]) == "dynamic_RESID_GBR_n150_d1_lr0.05_w36"


def test_operational_score_basis_projection_uses_operational_fields(evidence_pack) -> None:
    projected = project_score_basis_frame(evidence_pack.data["recommended"], OPERATIONAL_SCORE_BASIS).set_index("stream_label")
    assert set(projected["score_basis"]) == {OPERATIONAL_SCORE_BASIS}
    assert float(projected.loc["PED VKT per capita", "quarterly_mape"]) == pytest.approx(2.664135, abs=0.001)
    assert float(projected.loc["Light RUC volume", "quarterly_mape"]) == pytest.approx(8.272972, abs=0.001)
    assert float(projected.loc["Light RUC volume", "annual_mape"]) == pytest.approx(6.774906, abs=0.001)
    assert float(projected.loc["Heavy RUC volume", "quarterly_mape"]) == pytest.approx(3.011938, abs=0.001)
    assert projected.loc["Light RUC volume", "quarterly_mape_source_column"] == "operational_pooled_mape"


def test_scenario_comparison_basis_projection_keeps_paper_and_operational_separate(evidence_pack) -> None:
    comparison = evidence_pack.data["scenario_comparison"]
    paper = project_scenario_comparison_frame(
        comparison,
        PAPER_SCORE_BASIS,
        evidence_pack.data["recommended"],
        evidence_pack.data["schiff_df"],
    ).set_index("stream_label")
    operational = project_scenario_comparison_frame(
        comparison,
        OPERATIONAL_SCORE_BASIS,
        evidence_pack.data["recommended"],
        evidence_pack.data["schiff_df"],
    ).set_index("stream_label")

    assert float(paper.loc["Light RUC volume", "quarterly_gain_pp"]) == pytest.approx(3.158190, abs=0.001)
    assert float(paper.loc["Light RUC volume", "annual_gain_pp"]) == pytest.approx(1.428227, abs=0.001)
    assert float(operational.loc["Light RUC volume", "quarterly_gain_pp"]) == pytest.approx(1.254195, abs=0.001)
    assert float(operational.loc["Light RUC volume", "annual_gain_pp"]) == pytest.approx(-1.227428, abs=0.001)
    assert float(operational.loc["Light RUC volume", "finalist_quarterly_mape"]) == pytest.approx(8.272972, abs=0.001)
    assert float(operational.loc["Light RUC volume", "schiff_quarterly_mape"]) == pytest.approx(9.527168, abs=0.001)


def test_chart_sources_include_score_basis_and_no_old_light_default_values(evidence_pack) -> None:
    chart_dir = ROOT / "artifacts" / "chart_sources"
    source_files = list(chart_dir.glob("*.csv"))
    assert source_files
    multi_basis = {
        "diagnostics_r2_summary.csv",
        "reproducibility_component_r2.csv",
        "r2_ladder_summary.csv",
        "r2_training_fit_detail.csv",
        "r2_reproducibility_gap_register.csv",
    }
    for path in source_files:
        frame = pd.read_csv(path)
        assert "score_basis" in frame.columns, path.name
        score_basis_values = set(frame["score_basis"].dropna().astype(str))
        if path.name in multi_basis:
            assert {PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS}.issubset(score_basis_values), path.name
        else:
            assert score_basis_values == {PAPER_SCORE_BASIS}, path.name
    text = pd.read_csv(chart_dir / "overview_finalist_forecast_accuracy.csv").to_string()
    assert "9.15%" not in text
    assert "+2.40 pp" not in text

    frontier = pd.read_csv(chart_dir / "overview_candidate_search_frontier.csv")
    finalist = frontier[
        frontier["stream_label"].eq("Light RUC volume")
        & frontier["point_type"].astype(str).str.contains("finalist", case=False, na=False)
    ]
    assert not finalist.empty
    assert set(finalist["model"].astype(str)) == {"dynamic_RESID_GBR_n150_d1_lr0.05_w36"}


def test_candidate_frontier_balanced_under_both_score_bases(evidence_pack) -> None:
    controls = {
        "stage": "all",
        "streams": sorted(EXPECTED_STREAMS),
        "source_families": None,
        "variants": None,
        "top_n": 50,
        "show_schiff": True,
        "show_finalists": True,
        "show_screen": True,
        "show_final": True,
        "show_static": True,
        "show_prequential": True,
        "hide_outliers": True,
    }
    for basis in [PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS]:
        frame = build_candidate_landscape_frame(
            evidence_pack,
            {**controls, "score_basis": basis},
            "Balanced all-stream frontier view",
        )
        assert len(frame) == 400
        assert frame["stream_label"].value_counts().to_dict() == EXPECTED_BALANCED_FRONTIER_COUNTS
        assert set(frame["stream_label"]) == EXPECTED_STREAMS
        assert frame[["quarterly_mape", "annual_mape"]].notna().all().all()


def test_ensemble_composition_renders_all_streams_under_both_score_bases(evidence_pack) -> None:
    expected_streams = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
    weights = evidence_pack.data["weights"]
    # Component weights are score-basis invariant. Operational mode must not filter
    # them out just because the component table itself is paper-basis tagged.
    assert weights[weights["score_basis"].astype(str).eq(OPERATIONAL_SCORE_BASIS)].empty

    for _basis in [PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS]:
        fig, mapping = plot_ensemble_composition(weights.copy())
        assert set(mapping["Stream"]) == expected_streams
        assert len(fig.data) == 3


def test_overview_stress_buckets_follow_selected_score_basis(evidence_pack) -> None:
    paper_recommended = project_score_basis_frame(evidence_pack.data["recommended"], PAPER_SCORE_BASIS)
    operational_recommended = project_score_basis_frame(evidence_pack.data["recommended"], OPERATIONAL_SCORE_BASIS)

    paper = overview_stress_frame(evidence_pack, paper_recommended, {"score_basis": PAPER_SCORE_BASIS})
    operational = overview_stress_frame(evidence_pack, operational_recommended, {"score_basis": OPERATIONAL_SCORE_BASIS})

    assert paper["stress_bucket"].drop_duplicates().tolist() == OVERVIEW_STRESS_BUCKET_ORDER
    assert not paper["stress_bucket"].astype(str).isin(["2024+", "2022-23"]).any()
    assert set(STRESS_BUCKET_ORDER).issubset(set(operational["stress_bucket"].astype(str)))


def test_light_operational_annual_watch_is_visible_in_app_text() -> None:
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "Operational annual watch" in app_text
    assert "operational annual MAPE" in app_text
