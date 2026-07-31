"""Gates for the official-vintage reconciliation artifact set.

These tests gate the artifacts produced by
``scripts/build_official_vintage_reconciliation.py`` under
``artifacts/official_vintage_befu26/``. Run the builder first:

    python scripts/build_official_vintage_reconciliation.py \
        --official-vintage BEFU26 --bridge-vintage BEFU26
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "official_vintage_befu26"

ARTIFACT_NAMES = (
    "workbook_inventory.json",
    "workbook_schema.csv",
    "source_lineage.csv",
    "source_workbook_manifest.json",
    "formula_inventory.csv",
    "official_annual.csv",
    "official_annual_changes.csv",
    "row_reconciliation.csv",
    "formula_reconciliation.csv",
    "effective_rate_audit.csv",
    "class_share_audit.csv",
    "befu26_vs_mbu26_by_series_fy.csv",
    "befu26_vs_mbu26_summary.csv",
    "current_bridge_vintage_impact.csv",
    "current_vs_befu26_gap_by_stream_fy.csv",
    "current_vs_befu26_financial_decomposition.csv",
    "policy_basis_comparison.csv",
    "driver_availability_matrix.csv",
    "source_horizon_audit.csv",
    "front_end_selector_audit.csv",
    "validation_report.md",
)
KNOWN_RESIDUAL_FYS = (2027, 2028, 2029, 2030)
FORBIDDEN_PATH_FRAGMENTS = ("c:\\users", "c:/users", "downloads")


def read(name: str) -> pd.DataFrame:
    path = OUT / name
    assert path.exists(), f"missing artifact {name}; run the reconciliation builder first"
    return pd.read_csv(path)


def test_all_artifacts_exist() -> None:
    missing = [name for name in ARTIFACT_NAMES if not (OUT / name).exists()]
    assert not missing, f"missing artifacts: {missing}"


def test_formula_reconciliation_classification_set() -> None:
    frame = read("formula_reconciliation.csv")
    assert "classification" in frame.columns
    assert set(frame["classification"].unique()) == {"reconciled", "published_source_residual"}
    residual = frame[frame["classification"].eq("published_source_residual")]
    keys = {(str(row.output_series_id), int(row.FY)) for row in residual.itertuples()}
    assert keys == {("gross_ruc_revenue", fy) for fy in KNOWN_RESIDUAL_FYS}
    # row_reconciliation carries the identical governed classification.
    rows = read("row_reconciliation.csv")
    assert set(rows["classification"].unique()) == {"reconciled", "published_source_residual"}


def test_fy2027_published_residual_value() -> None:
    frame = read("formula_reconciliation.csv")
    row = frame[
        frame["output_series_id"].eq("gross_ruc_revenue")
        & frame["FY"].eq(2027)
        & frame["classification"].eq("published_source_residual")
    ]
    assert len(row) == 1
    assert abs(float(row["residual"].iloc[0]) - 0.627012) < 5e-6


def test_fy2025_published_actual_revisions_present() -> None:
    frame = read("befu26_vs_mbu26_by_series_fy.csv")
    revised = frame[frame["note"].astype(str).eq("published_actual_revision")]
    keys = {(str(row.series_id), int(row.FY)) for row in revised.itertuples()}
    assert ("light_petrol_vkt", 2025) in keys
    assert ("ped_vkt_per_capita", 2025) in keys
    light = revised[revised["series_id"].eq("light_petrol_vkt") & revised["FY"].eq(2025)]
    vktpc = revised[revised["series_id"].eq("ped_vkt_per_capita") & revised["FY"].eq(2025)]
    assert abs(float(light["delta"].iloc[0]) - (-0.492090)) < 5e-6
    assert abs(float(vktpc["delta"].iloc[0]) - (-0.092884)) < 5e-6


def test_effective_rate_audit_has_no_infinities() -> None:
    frame = read("effective_rate_audit.csv")
    numeric_columns = frame.select_dtypes(include=[np.number])
    assert not numeric_columns.empty
    assert not np.isinf(numeric_columns.to_numpy(dtype=float, na_value=np.nan)).any()


def test_class_shares_sum_to_one_and_are_opt_in_only() -> None:
    frame = read("class_share_audit.csv")
    share_columns = ["befu26_conventional_share", "befu26_bev_share", "befu26_phev_share"]
    complete = frame.dropna(subset=share_columns)
    assert not complete.empty
    sums = complete[share_columns].sum(axis=1)
    assert (sums - 1.0).abs().max() <= 1e-9
    assert "composition_refresh_candidate" in frame.columns
    notes = " ".join(frame["notes"].astype(str).unique()).lower()
    assert "opt-in" in notes and "unchanged" in notes


def test_bridge_impact_non_empty_for_both_engines() -> None:
    frame = read("current_bridge_vintage_impact.csv")
    assert not frame.empty
    assert set(frame["engine"].unique()) == {"ensemble", "ar1"}
    for engine in ("ensemble", "ar1"):
        assert len(frame[frame["engine"].eq(engine)]) > 0


@pytest.mark.parametrize("engine", ["ensemble", "ar1"])
def test_bridge_impact_baseline_matches_pinned_file(engine: str) -> None:
    impact = read("current_bridge_vintage_impact.csv")
    impact = impact[impact["engine"].eq(engine)]
    pinned = pd.read_csv(
        OUT / f"pre_bridge_refresh_chart_rows_{engine}.csv", low_memory=False
    )
    pinned = pinned[
        pinned["scenario_name"].astype(str).isin(["current_basecase", "current_comparison_1"])
        & pinned["time_grain"].astype(str).eq("june_year")
    ]
    pinned_values = {
        (str(row.scenario_name), str(row.series_id), int(row.june_year)): float(row.value)
        for row in pinned.itertuples()
    }
    sample = impact.sort_values(["scenario_name", "series_id", "june_year"]).iloc[::97]
    assert len(sample) >= 5
    for row in sample.itertuples():
        key = (str(row.scenario_name), str(row.series_id), int(row.june_year))
        assert key in pinned_values, f"impact row {key} missing from pinned baseline"
        assert float(row.baseline_value) == pytest.approx(pinned_values[key], abs=1e-9)


def test_policy_basis_contains_both_labelled_bases() -> None:
    frame = read("policy_basis_comparison.csv")
    bases = set(frame["comparison_basis"].unique())
    assert {"policy_normalised", "actual_default_ui"} <= bases
    for basis in ("policy_normalised", "actual_default_ui"):
        subset = frame[frame["comparison_basis"].eq(basis)]
        assert set(subset["fy"].unique()) >= {2026, 2027, 2028, 2029, 2030}
        assert subset["gap_current_minus_official"].notna().all()
    # The official side is always the published vintage.
    assert frame["official_basis"].astype(str).str.contains("published").all()


def test_decomposition_closes_and_is_labelled_financial_not_causal() -> None:
    frame = read("current_vs_befu26_financial_decomposition.csv")
    assert frame["residual_closure_term"].abs().max() <= 1e-6
    assert frame["ruc_identity_residual"].abs().max() <= 1e-6
    assert frame["net_fed_identity_residual"].abs().max() <= 1e-6
    notes = " ".join(frame["notes"].astype(str).unique()).lower()
    assert "not_causal" in notes or "not causal" in notes
    official_residual = frame[frame["FY"].eq(2027)]["official_published_source_residual"]
    assert (official_residual - 0.627012).abs().max() < 5e-6


def test_gap_by_stream_covers_streams_fys_engines() -> None:
    frame = read("current_vs_befu26_gap_by_stream_fy.csv")
    assert set(frame["engine"].unique()) == {"ensemble", "ar1"}
    assert len(set(frame["series_id"].unique())) == 8
    assert set(frame["FY"].unique()) == set(range(2026, 2051))
    assert len(frame) == 8 * 25 * 2
    assert frame["gap_current_minus_official"].notna().all()


def test_official_annual_is_verbatim_pack_copy() -> None:
    artifact = (OUT / "official_annual.csv").read_bytes()
    pack = (
        ROOT
        / "data"
        / "revenue_model_source_pack"
        / "official_vintages"
        / "befu26"
        / "official_annual.csv"
    ).read_bytes()
    assert artifact == pack


def test_workbook_inventory_contract() -> None:
    payload = json.loads((OUT / "workbook_inventory.json").read_text(encoding="utf-8"))
    assert payload["formula_count"] == 0
    assert payload["used_range"] == "A1:BD65"
    assert payload["year_span"] == {"min_fy": 2001, "max_fy": 2055, "n_year_columns": 55}
    registry = json.loads(
        (
            ROOT / "data" / "revenue_model_source_pack" / "official_vintage_registry.json"
        ).read_text(encoding="utf-8")
    )
    entry = next(v for v in registry["vintages"] if v["vintage_id"] == "BEFU26")
    assert payload["workbook"]["sha256"] == entry["workbook_sha256"]


def test_no_absolute_user_paths_in_artifacts() -> None:
    offenders = []
    for name in ARTIFACT_NAMES:
        text = (OUT / name).read_text(encoding="utf-8", errors="replace").lower()
        for fragment in FORBIDDEN_PATH_FRAGMENTS:
            if fragment in text:
                offenders.append((name, fragment))
    assert not offenders, f"absolute user paths found: {offenders}"


def test_validation_report_names_published_residual_and_revisions() -> None:
    text = (OUT / "validation_report.md").read_text(encoding="utf-8")
    assert "gross_ruc_revenue" in text
    assert "0.627012" in text
    assert "published_source_residual" in text
    assert "published_actual_revision" in text
    assert "light_petrol_vkt" in text and "ped_vkt_per_capita" in text
    # Impact headline and composition verdict sections are present.
    assert "Bridge-refresh impact headline" in text
    assert "Composition-refresh candidate verdict" in text
