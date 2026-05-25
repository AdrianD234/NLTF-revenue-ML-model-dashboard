from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.chart_sources import CHART_SOURCE_FILES
from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT
from model_dashboard.evidence_pack import REQUIRED_EVIDENCE_TABLES, load_evidence_pack, resolve_evidence_pack_root
from model_dashboard.labels import SCHIFF_SPEC_BENCHMARK_LABEL
from tests.fixtures.expected_values import EXPECTED_FINALIST_MAPE, EXPECTED_LIGHT_PAIRED_GAIN_PP


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def evidence_pack_root() -> Path:
    return resolve_evidence_pack_root(os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT", str(DEFAULT_EVIDENCE_PACK_ROOT)))


@pytest.fixture(scope="session")
def evidence_pack(evidence_pack_root: Path):
    return load_evidence_pack(evidence_pack_root, ROOT)


def test_evidence_pack_required_files_load(evidence_pack_root: Path, evidence_pack) -> None:
    assert (evidence_pack_root / "manifest.json").exists()
    for filename in REQUIRED_EVIDENCE_TABLES:
        assert (evidence_pack_root / "data" / filename).exists(), filename
    assert evidence_pack.manifest["source_mode"] == "dashboard_evidence_pack"


def test_resolve_evidence_pack_root_finds_explicit_schiff_spec_wrapper(tmp_path: Path) -> None:
    pack = tmp_path / "stage1_dashboard_evidence_pack_schiff_spec_v2" / "dashboard_evidence_pack"
    (pack / "data").mkdir(parents=True)
    (pack / "manifest.json").write_text("{}", encoding="utf-8")

    resolved = resolve_evidence_pack_root(tmp_path)

    assert resolved == pack


def test_default_app_uses_evidence_pack_not_legacy_or_mini(evidence_pack) -> None:
    manifest_text = str(evidence_pack.manifest)
    assert "mini_parquet" not in manifest_text
    assert "legacy_run_folder" not in manifest_text
    assert evidence_pack.run_dir.name == "dashboard_evidence_pack"
    assert set(evidence_pack.data["chart_contract"]["source_table"]).issuperset(
        {
            "candidate_cone.parquet",
            "finalists.parquet",
            "scenario_comparison.parquet",
            "horizon_profiles.parquet",
        }
    )


def test_all_16_panels_use_chart_contract_source_files(evidence_pack) -> None:
    contract = evidence_pack.data["chart_contract"].set_index("chart_id")["source_table"].to_dict()
    aliases = {
        "overview_finalist_forecast_accuracy": "finalist_forecast_accuracy",
        "overview_candidate_search_frontier": "candidate_search_frontier",
        "overview_ensemble_composition": "finalist_ensemble_composition",
        "overview_stress_horizon_checks": "stress_horizon_checks",
        "diagnostics_residual_autocorrelation": "residual_autocorrelation_by_lag",
        "diagnostics_residual_vs_fitted": "residual_vs_fitted",
        "diagnostics_pass_matrix": "diagnostic_pass_matrix",
        "diagnostics_error_distribution_by_horizon": "error_distribution_by_horizon",
        "scenario_stream_comparison": "stream_comparison",
        "scenario_improvement_vs_benchmark": "improvement_vs_benchmark",
        "scenario_horizon_comparison": "horizon_comparison",
        "scenario_decision_summary": "decision_summary",
        "schiff_vs_finalist_mape": "schiff_vs_finalist_mape",
        "schiff_benchmark_horizon_profiles": "benchmark_horizon_profiles",
        "schiff_paired_or_fullsample_gain": "fullsample_gain_vs_schiff",
        "schiff_benchmark_summary": "benchmark_summary",
    }
    for filename, (_, chart_id) in CHART_SOURCE_FILES.items():
        table = pd.read_csv(ROOT / "artifacts" / "chart_sources" / filename)
        assert set(table["source_file"].dropna()) == {contract[aliases[chart_id]]}, filename


def test_finalist_values_and_stale_values(evidence_pack) -> None:
    accuracy = pd.read_csv(ROOT / "artifacts" / "chart_sources" / "overview_finalist_forecast_accuracy.csv")
    indexed = accuracy.set_index(["stream_label", "metric_name"])
    for key, expected in EXPECTED_FINALIST_MAPE.items():
        assert float(indexed.loc[key, "metric_value"]) == pytest.approx(expected, abs=0.001)
    finalist_text = evidence_pack.data["recommended"].to_string()
    assert "5.49" not in finalist_text
    assert "12.38" not in finalist_text
    light = evidence_pack.data["recommended"][evidence_pack.data["recommended"]["stream_label"].eq("Light RUC volume")]
    assert not light["quarterly_mape"].astype(str).str.contains("11.55", regex=False).any()


def test_candidate_frontier_plots_more_than_100_rows(evidence_pack) -> None:
    frontier = pd.read_csv(ROOT / "artifacts" / "chart_sources" / "overview_candidate_search_frontier.csv")
    assert len(frontier) > 100
    assert {"Selected finalist", SCHIFF_SPEC_BENCHMARK_LABEL}.issubset(set(frontier["point_type"]))
    row_text = frontier.fillna("").astype(str).agg(lambda row: " ".join(row.to_list()), axis=1)
    assert not row_text.str.contains("20.50|20.499", regex=True).any()


def test_full_sample_vs_paired_semantics_are_enforced(evidence_pack) -> None:
    gain = pd.read_csv(ROOT / "artifacts" / "chart_sources" / "schiff_paired_or_fullsample_gain.csv")
    assert gain["chart_title"].str.contains("Full-sample", regex=False).all()
    assert not gain["chart_title"].str.contains("Paired Gain vs Schiff", regex=False).any()
    light = gain[gain["stream_label"].eq("Light RUC volume")]
    full_sample = light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"].astype(float).iloc[0]
    paired = light["paired_gain_pp"].dropna().astype(float).iloc[0]
    assert full_sample == pytest.approx(-0.734606, abs=0.001)
    assert paired == pytest.approx(EXPECTED_LIGHT_PAIRED_GAIN_PP, abs=0.001)
    assert full_sample < 0 and paired < 0
