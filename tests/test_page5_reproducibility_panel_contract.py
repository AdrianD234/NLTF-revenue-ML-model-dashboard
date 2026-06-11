from __future__ import annotations

import pytest

from app import (
    PAGE5_UI_CONTRACT_ROOT,
    page5_component_contribution_figure,
    page5_contract_panel_state,
    page5_missing_panel_html,
    page5_missing_panel_message,
    page5_panel_contract_frame,
    page5_panel_title,
    page5_ped_inner_status_rows,
    page5_repro_card_html,
)
from model_dashboard.light_ruc_reproducibility import load_ped_inner_hpo_audit_pack, load_reproducibility_pack


def test_page5_panel_contract_pack_is_loaded() -> None:
    contract_path = PAGE5_UI_CONTRACT_ROOT / "reproducibility_panel_contract.csv"
    assert contract_path.exists()

    contract = page5_panel_contract_frame()
    assert len(contract) == 18
    assert {"available", "component_weight_only", "unavailable"}.issubset(set(contract["status"]))


def test_page5_panel_titles_do_not_label_component_weights_as_feature_importance() -> None:
    contract = page5_panel_contract_frame()

    ped_feature = page5_contract_panel_state(contract, "PED VKT per capita", "feature_importance")
    heavy_feature = page5_contract_panel_state(contract, "Heavy RUC volume", "feature_importance")
    light_feature = page5_contract_panel_state(contract, "Light RUC volume", "feature_importance")

    assert ped_feature["status"] == "component_weight_only"
    assert page5_panel_title(ped_feature, "PED VKT per capita") == "Component contribution (PED)"
    assert heavy_feature["status"] == "component_weight_only"
    assert page5_panel_title(heavy_feature, "Heavy RUC volume") == "Ensemble component contribution (Heavy RUC)"
    assert light_feature["status"] == "available"
    assert page5_panel_title(light_feature, "Light RUC volume") == "Feature importance (Light RUC)"


def test_page5_unavailable_panel_messages_are_governance_caveats() -> None:
    contract = page5_panel_contract_frame()
    ped_coefficients = page5_contract_panel_state(contract, "PED VKT per capita", "coefficients")
    heavy_sensitivities = page5_contract_panel_state(contract, "Heavy RUC volume", "scenario_sensitivities")

    assert ped_coefficients["status"] == "unavailable"
    assert (
        page5_missing_panel_message("PED VKT per capita", "coefficients", ped_coefficients)
        == "Feature-level refit not attempted; inner HPO/static-solver audit remains partial."
    )
    assert heavy_sensitivities["status"] == "unavailable"
    assert (
        page5_missing_panel_message("Heavy RUC volume", "scenario_sensitivities", heavy_sensitivities)
        == "Not emitted by parent component runs; future component-level replay required."
    )

    html = page5_missing_panel_html("Model coefficients (PED)", page5_missing_panel_message("PED VKT per capita", "coefficients", ped_coefficients))
    assert "Governance caveat" in html
    assert "empty chart" not in html.lower()


def test_page5_component_contribution_figure_uses_pack_weights() -> None:
    ped_pack = load_reproducibility_pack("PED VKT per capita")
    heavy_pack = load_reproducibility_pack("Heavy RUC volume")

    ped_fig = page5_component_contribution_figure(ped_pack, "PED VKT per capita")
    heavy_fig = page5_component_contribution_figure(heavy_pack, "Heavy RUC volume")

    assert "Feature" not in str(ped_fig.layout.xaxis.title.text)
    assert "Feature" not in str(heavy_fig.layout.xaxis.title.text)
    assert ped_fig.layout.xaxis.title.text == "Component contribution (%)"
    assert heavy_fig.layout.xaxis.title.text == "Component contribution (%)"
    # vNext finalists: PED is a two-component, Heavy a three-component
    # convex ensemble; weights always sum to 100%.
    assert sorted(ped_fig.data[0].y) == ["C1", "C2"]
    assert sum(float(value) for value in ped_fig.data[0].x) == pytest.approx(100.0)
    assert len(heavy_fig.data[0].x) == 3
    assert sum(float(value) for value in heavy_fig.data[0].x) == pytest.approx(100.0)


def test_page5_ped_status_card_labels_inner_audit_partial() -> None:
    ped_pack = load_reproducibility_pack("PED VKT per capita")
    inner_pack = load_ped_inner_hpo_audit_pack()

    html = page5_repro_card_html("PED VKT per capita", ped_pack, inner_pack)

    assert "Exact weighted-ensemble replay" in html
    assert "convex vNext ensemble with saved fitted state" in html
    # The legacy inner HPO audit remains visible as archived lineage only.
    assert "Inner HPO/static-solver audit: partial" in html


def test_page5_ped_inner_missing_pack_status_is_clear() -> None:
    missing_pack = load_ped_inner_hpo_audit_pack("data/dashboard_evidence_pack_reproducibility/not_a_pack")

    rows = dict(page5_ped_inner_status_rows(missing_pack))

    assert rows["Inner audit status"] == "Missing PED inner HPO/static-solver audit pack"
    assert "model_registry.parquet" in rows["Inner audit evidence"]
