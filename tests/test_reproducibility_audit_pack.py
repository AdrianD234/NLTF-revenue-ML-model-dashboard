from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.validate_reproducibility_audit_pack import validate


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "dashboard_evidence_pack"
DATA_DIR = DATA_ROOT / "data"


def test_reproducibility_audit_tables_exist_with_expected_columns() -> None:
    findings, _ = validate(DATA_ROOT)
    assert all(item["status"] == "PASS" for item in findings)


def test_model_registry_covers_finalists_benchmarks_and_components() -> None:
    registry = pd.read_parquet(DATA_DIR / "model_registry.parquet")
    finalists = pd.read_parquet(DATA_DIR / "finalists.parquet")
    schiff = pd.read_parquet(DATA_DIR / "schiff_benchmark.parquet")
    components = pd.read_parquet(DATA_DIR / "ensemble_components.parquet")

    assert set(finalists["model"].astype(str)).issubset(set(registry["model"].astype(str)))
    assert set(schiff["model"].astype(str)).issubset(set(registry["component_model"].astype(str)))
    assert set(components["component_model"].astype(str)).issubset(set(registry["component_model"].astype(str)))
    assert {"PED Inputs", "Light RUC Inputs", "Heavy RUC Inputs"}.issubset(set(registry["source_sheet"].astype(str)))


def test_heavy_component_registry_matches_vnext_manifest() -> None:
    import json

    registry = pd.read_parquet(DATA_DIR / "model_registry.parquet")
    heavy_components = registry[
        registry["stream"].astype(str).eq("HEAVY_RUC")
        & registry["model_role"].astype(str).eq("ensemble_component")
    ]
    manifest = json.loads(
        (DATA_DIR.parents[1] / "dashboard_evidence_pack_reproducibility" / "heavy_ruc_vnext"
         / "fitted_model_manifest.json").read_text(encoding="utf-8")
    )
    expected = {m["component_model"]: m for m in manifest["members"]}

    assert len(heavy_components) == len(expected)
    assert set(heavy_components["component_model"].astype(str)) == set(expected)
    assert heavy_components["source_file"].astype(str).str.contains("fitted_model_manifest.json", regex=False).all()
    assert heavy_components["random_state"].astype(str).eq("42").all()
    for _, row in heavy_components.iterrows():
        member = expected[str(row["component_model"])]
        assert str(row["hyperparameters_json"]) == str(member["params_json"])
        assert float(row["component_weight"]) == member["component_weight"]


def test_single_component_predictions_equal_final_predictions() -> None:
    components = pd.read_parquet(DATA_DIR / "ensemble_components.parquet")
    component_predictions = pd.read_parquet(DATA_DIR / "component_predictions.parquet")
    single_components = set(
        components.loc[pd.to_numeric(components["weight"], errors="coerce").round(10).eq(1.0), "component_model"].astype(str)
    )
    rows = component_predictions[component_predictions["component_model"].astype(str).isin(single_components)]
    delta = (pd.to_numeric(rows["component_pred"], errors="coerce") - pd.to_numeric(rows["final_pred"], errors="coerce")).abs()

    assert not rows.empty
    assert delta.max() <= 1e-12
    assert rows["component_traceability_status"].eq("single_component_equals_final_prediction").all()


def test_heavy_ruc_ensemble_component_forecasts_reconcile_to_weighted_sum() -> None:
    component_predictions = pd.read_parquet(DATA_DIR / "component_predictions.parquet")
    heavy = component_predictions[component_predictions["stream"].astype(str).eq("HEAVY_RUC")]
    keys = ["stream", "finalist_model", "score_basis", "origin", "target_period", "horizon"]
    heavy = heavy.copy()
    heavy["weighted_component_pred"] = pd.to_numeric(heavy["weighted_component_pred"], errors="coerce")
    weighted = (
        heavy.groupby(keys, as_index=False)
        .agg(
            weighted_sum=("weighted_component_pred", "sum"),
            component_count=("component_model", "nunique"),
            final_pred=("final_pred", "first"),
        )
        .copy()
    )
    delta = (weighted["weighted_sum"] - pd.to_numeric(weighted["final_pred"], errors="coerce")).abs()

    assert heavy["component_model"].nunique() == 3
    assert pd.to_numeric(heavy["component_pred"], errors="coerce").notna().all()
    assert weighted["component_count"].eq(3).all()
    assert delta.max() <= 1e-5
    assert heavy["component_traceability_status"].eq("vnext_saved_state_parity_verified").all()


def test_reproducibility_report_does_not_claim_full_rebuild() -> None:
    report = (DATA_ROOT / "docs" / "reproducibility_report.md").read_text(encoding="utf-8")

    assert "Status: **INCOMPLETE**" in report
    assert "Do not claim full finalist reproducibility" in report
    assert "Heavy RUC weighted-sum status: `verified`" in report
    assert "fitted component objects are not yet rebuilt" in report


def test_explainability_incomplete_rows_are_deduplicated_and_explained() -> None:
    feature_importance = pd.read_parquet(DATA_DIR / "feature_importance.parquet")
    shap_summary = pd.read_parquet(DATA_DIR / "shap_summary.parquet")
    coefficients = pd.read_parquet(DATA_DIR / "model_coefficients.parquet")
    sensitivities = pd.read_parquet(DATA_DIR / "scenario_sensitivities.parquet")

    assert not feature_importance.duplicated(
        ["stream", "model", "origin_or_global", "feature", "importance_type"], keep=False
    ).any()
    assert not shap_summary.duplicated(["stream", "model", "feature"], keep=False).any()

    for frame in [feature_importance, shap_summary, coefficients, sensitivities]:
        incomplete = frame[frame["reproducibility_status"].astype(str).eq("incomplete")]
        assert not incomplete.empty
        assert incomplete["notes"].fillna("").astype(str).str.strip().ne("").all()
        assert incomplete["artifact_search_status"].astype(str).eq("not_found").all()
        assert incomplete["artifact_search_basis"].fillna("").astype(str).str.strip().ne("").all()


def test_reproducibility_artifact_search_report_exists() -> None:
    report_path = DATA_ROOT / "docs" / "reproducibility_artifact_search.md"
    report = report_path.read_text(encoding="utf-8")

    assert report_path.exists()
    assert "all_quarterly_predictions.csv" in report
    assert "Fitted model objects" in report
    assert "artifact_search_status = not_found" in report
