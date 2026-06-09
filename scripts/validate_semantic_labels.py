from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.diagnostic_matrix import DIAGNOSTIC_TOOLTIP_COPY  # noqa: E402
from model_dashboard.evidence_pack import load_evidence_pack  # noqa: E402
from model_dashboard.labels import model_hover_description, model_hover_title  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dashboard semantic labels.")
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def validate() -> list[tuple[str, str, str]]:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    load_evidence_pack(args.data_root, repo_root)

    app_text = read_text(repo_root / "app.py")
    plot_text = read_text(repo_root / "model_dashboard" / "plots.py")
    chart_spec = read_text(repo_root / "DASHBOARD_PAGE_CHART_SPEC.lock.md")
    screenshot_review = read_text(repo_root / "artifacts" / "screenshot_review.md")

    findings: list[tuple[str, str, str]] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        findings.append((name, "PASS" if passed else "FAIL", evidence))

    record(
        "Candidate count label is precise",
        "Plotted candidates" in app_text and "plotted candidates from" in app_text and "loaded candidates" not in app_text and "Candidate Models" not in app_text,
        "Overview KPI and frontier caption identify plotted candidate rows rather than vague loaded/model counts.",
    )
    record(
        "Frontier label explains balanced v6 frontier coverage",
        "Balanced all-stream frontier view; visual frontier samples are anchored to current finalists and Schiff " in app_text
        and "specification benchmarks and are excluded from governance scoring." in app_text
        and "All-stream frontier view; Light RUC uses challenger-search rows" not in app_text
        and "Coverage: PED" in app_text
        and "Curated cone sample" not in app_text,
        "Candidate frontier title/caption makes clear that v6 has balanced all-stream visualization samples excluded from governance scoring.",
    )
    record(
        "Candidate frontier has no dotted efficient-frontier line",
        "Efficient frontier" not in plot_text and '"dash": "dot"' not in plot_text,
        "Candidate Search Frontier uses candidate dots and explicit finalist/Schiff markers without a dotted connecting line.",
    )
    record(
        "Default stress chart excludes policy windows",
        "policy windows are excluded from the default view" in app_text
        and "OVERVIEW_STRESS_BUCKET_ORDER" in app_text,
        "Overview stress subtitle and bucket filtering keep 2024+/2022-23 out of Paper-style default.",
    )
    record(
        "Calibration R2 is not labelled adjusted R2",
        "Mean calibration R2" in app_text and "Mean Adjusted R2" not in app_text,
        "Diagnostics KPI title inspected in app.py.",
    )
    record(
        "Forecast R2 and calibration R2 are distinguished",
        "Forecast R2 versus calibration R2" in app_text
        and "Net forecast R2 after final model composition" in app_text
        and "actual-on-forecast validation regression" in app_text
        and "in-sample OLS R2" not in app_text,
        "Diagnostics and Governance labels distinguish net forecast R2 from calibration R2.",
    )
    record(
        "Full-sample gain chart is not labelled paired",
        "3. Full-sample Gain vs Schiff specification benchmark" in app_text and "Paired Gain vs Schiff" not in app_text,
        "Schiff gain chart title inspected in app.py.",
    )
    record(
        "Decision table separates full-sample gains from paired win rate",
        all(term in app_text for term in ["Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate"]),
        "Scenario and Schiff summary labels inspected in app.py.",
    )
    record(
        "Benchmark and decision summary fields expose governance tooltips",
        all(
            phrase in app_text
            for phrase in [
                "Schiff benchmark quarterly MAPE minus finalist quarterly MAPE",
                "Schiff benchmark annual MAPE minus finalist annual MAPE",
                "matched forecast comparisons",
                "MAPE gain, paired win rate, diagnostics and caveats",
                "Promoted because the finalist beats the Schiff specification benchmark",
            ]
        )
        and "render_info_tooltip" in app_text
        and "summary-tooltip-trigger" in read_text(repo_root / "model_dashboard" / "ui.py")
        and ".summary-tooltip-trigger:focus .summary-tooltip-text" in read_text(repo_root / "model_dashboard" / "ui.py")
        and ".summary-rec-badge:focus .summary-tooltip-text" in read_text(repo_root / "model_dashboard" / "ui.py"),
        "Schiff Benchmark and Scenario recommendation summaries have accessible hover/focus copy.",
    )
    record(
        "Residual vs fitted axis does not use misleading million-unit label",
        "Fitted value, native units" in (app_text + plot_text) and "Fitted value (m)" not in (app_text + plot_text),
        "Residual axis title inspected in app.py/plot helpers.",
    )
    diagnostic_matrix_text = read_text(repo_root / "model_dashboard" / "diagnostic_matrix.py")
    tooltip_requirements = {
        "ADF": "Augmented Dickey-Fuller test",
        "KPSS": "Kwiatkowski-Phillips-Schmidt-Shin test",
        "White": "White test",
        "Jarque-Bera": "Jarque-Bera test",
        "Cointegration": "Cointegration test",
    }
    record(
        "Diagnostic pass matrix headers and cells expose plain-English tooltips",
        all(phrase in DIAGNOSTIC_TOOLTIP_COPY.get(label, "") for label, phrase in tooltip_requirements.items())
        and "diagnostic_pass_matrix_html" in app_text
        and "html_chart_card" in app_text
        and "tabindex='0'" in diagnostic_matrix_text
        and "role='tooltip'" in diagnostic_matrix_text
        and ".diag-tooltip-trigger:hover .diag-tooltip-text" in read_text(repo_root / "model_dashboard" / "ui.py")
        and ".diag-tooltip-trigger:focus .diag-tooltip-text" in read_text(repo_root / "model_dashboard" / "ui.py"),
        "Diagnostic matrix tooltips are centralized, keyboard focusable, and rendered by the dashboard.",
    )

    gain_source = repo_root / "artifacts" / "chart_sources" / "schiff_paired_or_fullsample_gain.csv"
    if gain_source.exists():
        gain = pd.read_csv(gain_source)
        light = gain[gain["stream_label"].eq("Light RUC volume")]
        paired_gain = pd.to_numeric(light["paired_gain_pp"], errors="coerce").dropna()
        full_qtr_gain = pd.to_numeric(
            light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"],
            errors="coerce",
        ).dropna()
        full_annual_gain = pd.to_numeric(
            light[light["metric_name"].eq("Full-sample annual gain")]["metric_value"],
            errors="coerce",
        ).dropna()
        record(
            "Light RUC paper gains are not hidden by full-sample gain label",
            not paired_gain.empty
            and float(paired_gain.iloc[0]) > 0
            and not full_qtr_gain.empty
            and float(full_qtr_gain.iloc[0]) > 0
            and not full_annual_gain.empty
            and float(full_annual_gain.iloc[0]) > 0,
            f"paired_gain={float(paired_gain.iloc[0]) if not paired_gain.empty else 'missing'}; full_qtr_gain={float(full_qtr_gain.iloc[0]) if not full_qtr_gain.empty else 'missing'}; full_annual_gain={float(full_annual_gain.iloc[0]) if not full_annual_gain.empty else 'missing'}",
        )
    else:
        record("Light RUC paper gains are not hidden by full-sample gain label", False, "Missing Schiff gain source table.")

    record(
        "Light RUC operational annual watch is visible",
        "Operational annual watch" in app_text and "Light RUC" in app_text,
        "App text contains the visible operational annual watch note.",
    )

    contract_path = repo_root / "data" / "dashboard_evidence_pack_reproducibility" / "_ui_contract" / "reproducibility_panel_contract.csv"
    if contract_path.exists():
        panel_contract = pd.read_csv(contract_path)
        ped_feature = panel_contract[
            panel_contract["stream"].eq("PED VKT per capita")
            & panel_contract["panel"].eq("feature_importance")
        ]
        heavy_feature = panel_contract[
            panel_contract["stream"].eq("Heavy RUC volume")
            & panel_contract["panel"].eq("feature_importance")
        ]
        light_feature = panel_contract[
            panel_contract["stream"].eq("Light RUC volume")
            & panel_contract["panel"].eq("feature_importance")
        ]
        record(
            "Page 5 panel contract prevents component weights being labelled feature importance",
            not ped_feature.empty
            and not heavy_feature.empty
            and not light_feature.empty
            and str(ped_feature.iloc[0]["status"]) == "component_weight_only"
            and str(heavy_feature.iloc[0]["status"]) == "component_weight_only"
            and str(light_feature.iloc[0]["status"]) == "available"
            and "Component contribution" in app_text
            and "Ensemble component contribution" in app_text
            and "Feature importance ({short_stream_label(analytics_stream)})" not in app_text,
            "Contract CSV and app panel labels separate component contribution from true feature importance.",
        )
    else:
        record(
            "Page 5 panel contract prevents component weights being labelled feature importance",
            False,
            f"Missing contract file: {contract_path}",
        )

    record(
        "Page 5 unavailable explainability panels render governance caveats",
        "Feature-level refit not attempted; inner HPO/static-solver audit remains partial." in app_text
        and "Not emitted by parent component runs; future component-level replay required." in app_text
        and "page5-caveat-card" in app_text
        and "render_page5_missing_panel" in app_text,
        "PED/Heavy coefficients and sensitivities are rendered as styled missing-data cards, not empty charts.",
    )

    stale_spec_terms = [
        "Candidate Models",
        "Mean Adjusted R2",
        "Paired Gain vs Schiff",
    ]
    stale_in_spec = [term for term in stale_spec_terms if term in chart_spec]
    record(
        "Dashboard chart spec uses current semantic labels",
        not stale_in_spec,
        "stale_terms=" + ", ".join(stale_in_spec) if stale_in_spec else "No stale chart-spec labels found.",
    )

    record(
        "Screenshot review does not describe the full-sample chart as paired",
        "Paired Gain vs Schiff" not in screenshot_review,
        "artifacts/screenshot_review.md label wording inspected.",
    )

    hover_bad_terms = ["Full model", "Full component"]
    stale_hover_terms = [term for term in hover_bad_terms if term in plot_text]
    heavy_detail = model_hover_description(
        "HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64",
        weight=0.469332,
    )
    light_detail = model_hover_description("dynamic_RESID_GBR_n150_d1_lr0.05_w36")
    record(
        "Model hovers use management-friendly descriptions",
        "Model detail" in plot_text
        and "Component detail" in plot_text
        and not stale_hover_terms
        and model_hover_title("HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64")
        == "Dynamic ElasticNet model"
        and "Uses no lead variables" in heavy_detail
        and "Ensemble weight: 46.9%" in heavy_detail
        and model_hover_title("dynamic_RESID_GBR_n150_d1_lr0.05_w36") == "Dynamic residual GBM"
        and "two-stage model" in light_detail,
        "Hover templates use Model detail/Component detail and helper translations for Heavy RUC ElasticNet and Light RUC residual GBM.",
    )

    return findings


def main() -> int:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    try:
        findings = validate()
    except Exception as exc:
        findings = [("Semantic label validation", "FAIL", str(exc))]
    failed = [row for row in findings if row[1] != "PASS"]
    status = "passed" if not failed else "failed"
    lines = [
        "# Semantic Label Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {name} | {state} | {evidence} |" for name, state, evidence in findings)
    lines.append("")
    report = "\n".join(lines)
    (artifacts / "semantic_label_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
