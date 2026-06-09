from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.chart_sources import CHART_SOURCE_FILES, CORE_COLUMNS  # noqa: E402
from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.evidence_pack import load_evidence_pack  # noqa: E402
from model_dashboard.labels import OVERVIEW_STRESS_BUCKET_ORDER  # noqa: E402
from model_dashboard.score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS, project_score_basis_frame  # noqa: E402


EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
EXPECTED_FRONTIER_COUNTS = {"PED VKT per capita": 132, "Light RUC volume": 136, "Heavy RUC volume": 132}
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"
MULTI_SCORE_BASIS_SOURCE_FILES = {
    "diagnostics_r2_summary.csv",
    "reproducibility_component_r2.csv",
    "r2_ladder_summary.csv",
    "r2_training_fit_detail.csv",
    "r2_reproducibility_gap_register.csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dashboard chart source tables.")
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def read_table(filename: str) -> pd.DataFrame:
    path = CHART_SOURCE_DIR / filename
    if not path.exists():
        raise AssertionError(f"Missing chart source table: {path}")
    if path.stat().st_size == 0:
        raise AssertionError(f"Empty chart source table: {path}")
    return pd.read_csv(path)


def approx(actual: Any, expected: float, tolerance: float = 0.001) -> bool:
    value = pd.to_numeric(actual, errors="coerce")
    return pd.notna(value) and abs(float(value) - expected) <= tolerance


def validate() -> list[tuple[str, str, str]]:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    loaded = load_evidence_pack(args.data_root, repo_root)
    loaded_weights = loaded.data.get("weights", pd.DataFrame())

    findings: list[tuple[str, str, str]] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        findings.append((name, "PASS" if passed else "FAIL", evidence))

    for filename, (page, chart_id) in CHART_SOURCE_FILES.items():
        try:
            table = read_table(filename)
            missing = [column for column in CORE_COLUMNS if column not in table.columns]
            page_ok = set(table["page"].dropna().astype(str)) == {page}
            id_ok = set(table["chart_id"].dropna().astype(str)) == {chart_id}
            basis_ok = table["calculation_basis"].dropna().astype(str).str.len().gt(0).all()
            score_basis_values = set(table["score_basis"].dropna().astype(str)) if "score_basis" in table.columns else set()
            if filename in MULTI_SCORE_BASIS_SOURCE_FILES:
                score_basis_ok = {PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS}.issubset(score_basis_values)
            else:
                score_basis_ok = score_basis_values == {PAPER_SCORE_BASIS}
            record(
                f"{filename} exists and has required columns",
                not missing and page_ok and id_ok and basis_ok and score_basis_ok,
                f"rows={len(table):,}; missing={missing}; page_ok={page_ok}; chart_id_ok={id_ok}; score_basis_ok={score_basis_ok}",
            )
        except Exception as exc:
            record(f"{filename} exists and has required columns", False, str(exc))

    kpi = read_table("overview_kpi_cards.csv")
    schiff = loaded.data.get("schiff_df", pd.DataFrame())
    finalists = loaded.data.get("recommended", pd.DataFrame())
    annual_mean_row = kpi[kpi["metric_name"].eq("Schiff specification annual MAPE mean")]
    annual_gain_row = kpi[kpi["metric_name"].eq("Annual gain vs Schiff specification benchmark")]
    expected_schiff_annual = float(pd.to_numeric(schiff["annual_mape"], errors="coerce").mean()) if "annual_mape" in schiff.columns else float("nan")
    expected_finalist_annual = float(pd.to_numeric(finalists["annual_mape"], errors="coerce").mean()) if "annual_mape" in finalists.columns else float("nan")
    expected_gain = expected_schiff_annual - expected_finalist_annual
    kpi_ok = (
        not annual_mean_row.empty
        and not annual_gain_row.empty
        and annual_mean_row["source_file"].astype(str).eq("schiff_benchmark.parquet").all()
        and annual_mean_row["source_column"].astype(str).eq("annual_mape").all()
        and approx(annual_mean_row["metric_value"].iloc[0], expected_schiff_annual)
        and approx(annual_gain_row["metric_value"].iloc[0], expected_gain)
        and "score_basis" in kpi.columns
        and set(kpi["score_basis"].dropna().astype(str)) == {"schiff_paper_horizon_mean"}
    )
    record(
        "Overview annual KPI benchmark source reconciles to Schiff benchmark annual_mape",
        kpi_ok,
        f"Schiff annual mean={expected_schiff_annual:.3f}; finalist annual mean={expected_finalist_annual:.3f}; gain={expected_gain:.3f}.",
    )

    ensemble = read_table("overview_ensemble_composition.csv")
    expected_weights = loaded_weights.copy()
    if "component_rank" not in expected_weights.columns and not expected_weights.empty:
        expected_weights = expected_weights.sort_values(["stream_label", "weight"], ascending=[True, False]).copy()
        expected_weights["component_rank"] = expected_weights.groupby("stream_label", dropna=False).cumcount() + 1
    if {"stream_label", "component_rank", "weight"}.issubset(expected_weights.columns):
        expected_weights["expected_weight_pct"] = pd.to_numeric(expected_weights["weight"], errors="coerce") * 100
        expected_weights = expected_weights[["stream_label", "component_rank", "expected_weight_pct"]].dropna(
            subset=["stream_label", "component_rank", "expected_weight_pct"]
        )
    else:
        expected_weights = pd.DataFrame(columns=["stream_label", "component_rank", "expected_weight_pct"])
    actual_weights = ensemble[["stream_label", "component_rank", "weight_pct"]].copy()
    actual_weights["component_rank"] = pd.to_numeric(actual_weights["component_rank"], errors="coerce")
    actual_weights["weight_pct"] = pd.to_numeric(actual_weights["weight_pct"], errors="coerce")
    expected_weights["component_rank"] = pd.to_numeric(expected_weights["component_rank"], errors="coerce")
    weight_join = expected_weights.merge(actual_weights, on=["stream_label", "component_rank"], how="outer", indicator=True)
    weight_delta = (weight_join["weight_pct"] - weight_join["expected_weight_pct"]).abs()
    ensemble_ok = not expected_weights.empty and weight_join["_merge"].eq("both").all() and weight_delta.fillna(999).le(0.001).all()
    demo_fragments = {"57.1", "38.7", "23.2", "21.8", "48.7", "37.7", "13.7"}
    demo_visible = any(fragment in ",".join(ensemble["metric_display"].astype(str)) for fragment in demo_fragments)
    record(
        "Ensemble source uses Parquet component weights",
        ensemble_ok and not demo_visible,
        f"Compared {len(expected_weights):,} Parquet component weights to chart source rows.",
    )

    stress = read_table("overview_stress_horizon_checks.csv")
    stress_ok = True
    for stream in EXPECTED_STREAMS:
        stream_rows = stress[stress["stream_label"].eq(stream)]
        stress_ok = stress_ok and stream_rows["stress_bucket"].tolist() == list(OVERVIEW_STRESS_BUCKET_ORDER)
    for stream in ["PED VKT per capita", "Light RUC volume"]:
        for bucket in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]:
            row = stress[stress["stream_label"].eq(stream) & stress["stress_bucket"].eq(bucket)]
            stress_ok = stress_ok and not row.empty and pd.to_numeric(row["metric_value"], errors="coerce").notna().any()
    heavy = stress[stress["stream_label"].eq("Heavy RUC volume")].set_index("stress_bucket")
    heavy_core = all(
        pd.notna(pd.to_numeric(heavy.loc[bucket, "metric_value"], errors="coerce"))
        for bucket in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]
    )
    policy_hidden = not stress["stress_bucket"].astype(str).isin(["2024+", "2022-23"]).any()
    record(
        "Stress chart source uses default paper horizon buckets only",
        stress_ok and heavy_core and policy_hidden,
        "Overview default source table includes 1-4, 5-8, 9-12 and Annual only; policy windows stay out of the main chart.",
    )

    frontier = read_table("overview_candidate_search_frontier.csv")
    frontier_streams = set(frontier["stream_label"].dropna().astype(str))
    frontier_has_required_streams = EXPECTED_STREAMS.issubset(frontier_streams)
    frontier_counts = frontier["stream_label"].dropna().astype(str).value_counts().to_dict()
    balanced_counts = frontier_counts == EXPECTED_FRONTIER_COUNTS
    frontier_has_sample_contract = {"frontier_sample_class", "frontier_sample_note"}.issubset(frontier.columns)
    sample_classes = set(frontier.get("frontier_sample_class", pd.Series(dtype=str)).dropna().astype(str))
    has_visual_samples = "balanced_visual_frontier_sample" in sample_classes and "anchor" in sample_classes
    has_frontier_notes = frontier.get("frontier_sample_note", pd.Series(dtype=str)).dropna().astype(str).str.len().gt(0).any()
    record(
        "Candidate frontier source includes balanced v6 all-stream sample metadata",
        len(frontier) == 400 and balanced_counts and frontier_has_required_streams and frontier_has_sample_contract and has_visual_samples and has_frontier_notes,
        f"rows={len(frontier):,}; counts={frontier_counts}; sample_classes={sorted(sample_classes)}.",
    )

    candidate = loaded.data.get("candidate_df", pd.DataFrame())
    score_basis_failures: list[str] = []
    if candidate.empty:
        score_basis_failures.append("candidate_df empty")
    else:
        mask = pd.Series(False, index=candidate.index)
        for column in ["plot_default_include", "is_plot_candidate"]:
            if column in candidate.columns:
                mask = mask | candidate[column].fillna(False).astype(bool)
        plotted = candidate[mask].copy() if mask.any() else candidate.copy()
        for basis in [PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS]:
            projected = project_score_basis_frame(plotted, basis)
            projected = projected.dropna(subset=["quarterly_mape", "annual_mape"])
            counts = projected["stream_label"].dropna().astype(str).value_counts().to_dict()
            if len(projected) != 400 or counts != EXPECTED_FRONTIER_COUNTS:
                score_basis_failures.append(f"{basis}: rows={len(projected)}, counts={counts}")
    record(
        "Candidate frontier has balanced all-stream rows under both score bases",
        not score_basis_failures,
        "Paper and Operational score-basis projections both contain 400 rows with PED 132, Light RUC 136, Heavy RUC 132."
        if not score_basis_failures
        else "; ".join(score_basis_failures),
    )

    contamination: list[str] = []
    for filename in CHART_SOURCE_FILES:
        if filename == "overview_candidate_search_frontier.csv":
            continue
        table = read_table(filename)
        text = table.fillna("").astype(str)
        sample_col_present = "frontier_sample_class" in table.columns and table["frontier_sample_class"].dropna().astype(str).str.len().gt(0).any()
        visual_model_present = text.apply(
            lambda row: row.str.contains("VISUAL_FRONTIER_SAMPLE", case=False, regex=False).any()
            or row.str.contains("balanced_frontier", case=False, regex=False).any(),
            axis=1,
        ).any()
        if sample_col_present or visual_model_present:
            contamination.append(filename)
    record(
        "Visual frontier sample rows are isolated to Candidate Search Frontier",
        not contamination,
        "No non-frontier source table contains visual frontier sample metadata or VISUAL_FRONTIER_SAMPLE model rows."
        if not contamination
        else "Contaminated tables: " + ", ".join(contamination),
    )

    scenario = read_table("scenario_decision_summary.csv")
    scenario_terms = {"Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate"}
    record("Scenario summary labels full-sample gains and paired win rate", scenario_terms.issubset(set(scenario["metric_name"])), "Decision-source metric labels inspected.")

    gain = read_table("schiff_paired_or_fullsample_gain.csv")
    gain_text = " ".join(gain["chart_title"].astype(str).unique()) + " " + " ".join(gain["calculation_basis"].astype(str).unique())
    light_gain = gain[gain["stream_label"].eq("Light RUC volume")]
    light_paired_positive = float(light_gain["paired_gain_pp"].dropna().iloc[0]) > 0
    light_full_qtr_positive = float(
        light_gain[light_gain["metric_name"].eq("Full-sample quarterly gain")]["metric_value"].dropna().iloc[0]
    ) > 0
    light_full_annual_positive = float(
        light_gain[light_gain["metric_name"].eq("Full-sample annual gain")]["metric_value"].dropna().iloc[0]
    ) > 0
    record(
        "Schiff gain chart is labelled full-sample and preserves Light RUC paper gains",
        "Full-sample" in gain_text
        and "Paired Gain vs Schiff" not in gain_text
        and light_paired_positive
        and light_full_qtr_positive
        and light_full_annual_positive,
        f"Light qtr gain={float(light_gain[light_gain['metric_name'].eq('Full-sample quarterly gain')]['metric_value'].dropna().iloc[0]):.3f} pp; annual gain={float(light_gain[light_gain['metric_name'].eq('Full-sample annual gain')]['metric_value'].dropna().iloc[0]):.3f} pp; paired gain={float(light_gain['paired_gain_pp'].dropna().iloc[0]):.3f} pp.",
    )

    for filename in ["scenario_horizon_comparison.csv", "schiff_benchmark_horizon_profiles.csv"]:
        table = read_table(filename)
        record(
            f"{filename} includes all streams and scenarios",
            EXPECTED_STREAMS.issubset(set(table["stream_label"])) and {"Finalist", "Schiff"}.issubset(set(table["scenario"])),
            f"streams={sorted(set(table['stream_label'].dropna()))}; scenarios={sorted(set(table['scenario'].dropna()))}",
        )

    acf = read_table("diagnostics_residual_autocorrelation.csv")
    acf_notes = " ".join(acf["notes"].dropna().astype(str))
    record(
        "ACF source table uses one documented residual scope",
        EXPECTED_STREAMS.issubset(set(acf["stream_label"]))
        and "All selected quarterly residuals averaged by target period" in acf_notes
        and not acf.duplicated(["stream_label", "lag"]).any(),
        f"rows={len(acf):,}; scopes={sorted(set(acf['notes'].dropna().astype(str)))}",
    )

    pass_matrix = read_table("diagnostics_pass_matrix.csv")
    record(
        "Diagnostics source labels calibration R2 and Watch/Fail statuses",
        "Calibration R2" in set(pass_matrix["metric_name"]) and "Adjusted R2" not in set(pass_matrix["metric_name"]) and {"Watch", "Fail"}.issubset(set(pass_matrix["pass_status"])),
        f"tests={sorted(set(pass_matrix['metric_name'].dropna()))}",
    )

    residual = read_table("diagnostics_residual_vs_fitted.csv")
    record(
        "Residual vs fitted source uses native-unit calculation basis",
        residual["calculation_basis"].str.contains("native stream units", regex=False).all(),
        f"rows={len(residual):,}",
    )

    return findings


def main() -> int:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    try:
        findings = validate()
    except Exception as exc:
        findings = [("Chart source validation", "FAIL", str(exc))]
    failed = [row for row in findings if row[1] != "PASS"]
    status = "passed" if not failed else "failed"
    lines = [
        "# Chart Source Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {name} | {state} | {evidence} |" for name, state, evidence in findings)
    lines.append("")
    report = "\n".join(lines)
    (artifacts / "chart_source_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
