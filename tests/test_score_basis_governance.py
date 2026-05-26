from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack
from model_dashboard.score_basis import (
    OPERATIONAL_SCORE_BASIS,
    PAPER_SCORE_BASIS,
    project_scenario_comparison_frame,
    project_score_basis_frame,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def evidence_pack():
    return load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, ROOT)


def test_v3_default_score_basis_is_paper_style(evidence_pack) -> None:
    finalists = evidence_pack.data["recommended"].set_index("stream_label")
    assert set(finalists["score_basis"]) == {PAPER_SCORE_BASIS}
    assert float(finalists.loc["PED VKT per capita", "quarterly_mape"]) == pytest.approx(3.237144, abs=0.001)
    assert float(finalists.loc["Light RUC volume", "quarterly_mape"]) == pytest.approx(6.065145, abs=0.001)
    assert float(finalists.loc["Heavy RUC volume", "quarterly_mape"]) == pytest.approx(2.809473, abs=0.001)
    assert str(finalists.loc["Light RUC volume", "model"]) == "schiff_w36_OLS"


def test_operational_score_basis_projection_uses_operational_fields(evidence_pack) -> None:
    projected = project_score_basis_frame(evidence_pack.data["recommended"], OPERATIONAL_SCORE_BASIS).set_index("stream_label")
    assert set(projected["score_basis"]) == {OPERATIONAL_SCORE_BASIS}
    assert float(projected.loc["PED VKT per capita", "quarterly_mape"]) == pytest.approx(2.473245, abs=0.001)
    assert float(projected.loc["Light RUC volume", "quarterly_mape"]) == pytest.approx(7.743952, abs=0.001)
    assert float(projected.loc["Heavy RUC volume", "quarterly_mape"]) == pytest.approx(3.484368, abs=0.001)
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

    assert float(paper.loc["Light RUC volume", "quarterly_gain_pp"]) == pytest.approx(2.456252, abs=0.001)
    assert float(paper.loc["Light RUC volume", "annual_gain_pp"]) == pytest.approx(-0.723188, abs=0.001)
    assert float(operational.loc["Light RUC volume", "quarterly_gain_pp"]) == pytest.approx(1.783216, abs=0.001)
    assert float(operational.loc["Light RUC volume", "finalist_quarterly_mape"]) == pytest.approx(7.743952, abs=0.001)
    assert float(operational.loc["Light RUC volume", "schiff_quarterly_mape"]) == pytest.approx(9.527168, abs=0.001)


def test_chart_sources_include_score_basis_and_no_old_light_default_values(evidence_pack) -> None:
    chart_dir = ROOT / "artifacts" / "chart_sources"
    source_files = list(chart_dir.glob("*.csv"))
    assert source_files
    for path in source_files:
        frame = pd.read_csv(path)
        assert "score_basis" in frame.columns, path.name
        assert set(frame["score_basis"].dropna().astype(str)) == {PAPER_SCORE_BASIS}, path.name
    text = pd.read_csv(chart_dir / "overview_finalist_forecast_accuracy.csv").to_string()
    assert "9.15%" not in text
    assert "+2.40 pp" not in text
