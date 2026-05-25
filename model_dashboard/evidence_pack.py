from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import pandas as pd

from .data.chart_sources import write_chart_source_tables
from .data.config import DashboardData, DEFAULT_EVIDENCE_PACK_ROOT
from .data.diagnostics import DEFAULT_ACF_RESIDUAL_SCOPE, select_diagnostic_acf_scope
from .data.manifest import write_data_source_manifest
from .data.transforms import normalise_parquet_candidate
from .labels import STRESS_BUCKET_ORDER
from .metrics import add_stream_fields, normalise_paired, normalise_predictions, normalise_stress, normalise_weights, scale_percent_columns


REQUIRED_EVIDENCE_TABLES = (
    "candidate_cone.parquet",
    "finalists.parquet",
    "schiff_benchmark.parquet",
    "ensemble_components.parquet",
    "residual_predictions.parquet",
    "horizon_profiles.parquet",
    "stress_horizon.parquet",
    "scenario_comparison.parquet",
    "diagnostic_tests.parquet",
    "diagnostic_pass_matrix.parquet",
    "diagnostic_acf.parquet",
    "error_distribution.parquet",
    "annual_predictions.parquet",
    "chart_contract.parquet",
)


@dataclass(frozen=True)
class DashboardEvidencePack(DashboardData):
    """Parquet-first dashboard evidence pack consumed by the four primary pages."""


def resolve_evidence_pack_root(root: str | Path | None = None) -> Path:
    """Return the directory containing manifest.json and data/*.parquet.

    The supplied zip may be unpacked either directly as dashboard_evidence_pack
    or one level up as stage1_dashboard_evidence_pack_v1/dashboard_evidence_pack.
    """
    requested = Path(root or DEFAULT_EVIDENCE_PACK_ROOT).expanduser()
    downloads = Path.home() / "Downloads"
    candidates = [
        requested,
        requested / "dashboard_evidence_pack",
        requested / "stage1_dashboard_evidence_pack_v1" / "dashboard_evidence_pack",
        downloads / "dashboard_evidence_pack",
        downloads / "stage1_dashboard_evidence_pack_v1" / "dashboard_evidence_pack",
    ]
    for candidate in candidates:
        if (candidate / "manifest.json").exists() and (candidate / "data").is_dir():
            return candidate
    return requested


def evidence_pack_signature(root: str | Path | None = None) -> tuple[tuple[str, int, int], ...]:
    pack_root = resolve_evidence_pack_root(root)
    paths = [pack_root / "manifest.json", *[pack_root / "data" / name for name in REQUIRED_EVIDENCE_TABLES]]
    signature: list[tuple[str, int, int]] = []
    for path in paths:
        if not path.exists():
            continue
        stat = path.stat()
        signature.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


def load_evidence_pack(root: str | Path | None = None, repo_root: str | Path | None = None) -> DashboardEvidencePack:
    pack_root = resolve_evidence_pack_root(root)
    manifest_path = pack_root / "manifest.json"
    data_dir = pack_root / "data"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Evidence-pack manifest not found: {manifest_path}")
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Evidence-pack data folder not found: {data_dir}")

    missing = [name for name in REQUIRED_EVIDENCE_TABLES if not (data_dir / name).exists()]
    if missing:
        raise FileNotFoundError("Evidence pack is missing required table(s): " + ", ".join(missing))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = {name: pd.read_parquet(data_dir / name) for name in REQUIRED_EVIDENCE_TABLES}
    tables = {name.removesuffix(".parquet"): frame for name, frame in raw.items()}

    candidate = _normalise_candidate(tables["candidate_cone"])
    finalists = _normalise_model_rows(tables["finalists"], scenario="Finalist")
    schiff = _normalise_model_rows(tables["schiff_benchmark"], scenario="Schiff")
    ensemble = _normalise_ensemble_components(tables["ensemble_components"])
    residual_predictions = _normalise_residual_predictions(tables["residual_predictions"])
    annual_predictions = _normalise_annual_predictions(tables["annual_predictions"])
    horizon = _normalise_horizon_profiles(tables["horizon_profiles"])
    stress = _normalise_stress_horizon(tables["stress_horizon"])
    diagnostic_tests = _normalise_diagnostic_tests(tables["diagnostic_tests"])
    pass_matrix = _normalise_pass_matrix(tables["diagnostic_pass_matrix"])
    acf = _normalise_acf(tables["diagnostic_acf"])
    error_distribution = _normalise_error_distribution(tables["error_distribution"])
    scenario = _normalise_scenario_comparison(tables["scenario_comparison"], finalists, schiff)
    paired = _paired_from_scenario(scenario)
    contract = tables["chart_contract"].copy()

    default_mask = pd.Series(False, index=candidate.index)
    for column in ["plot_default_include", "is_plot_candidate"]:
        if column in candidate.columns:
            default_mask = default_mask | candidate[column].fillna(False).astype(bool)
    summary = candidate[default_mask].copy() if default_mask.any() else candidate.copy()
    if "is_extreme_outlier" in summary.columns:
        summary = summary[~summary["is_extreme_outlier"].fillna(False).astype(bool)].copy()

    curated_manifest = pd.DataFrame(
        [
            {
                "created_at": manifest.get("created_at"),
                "source": "dashboard_evidence_pack_v1",
                "source_file": "manifest.json",
                "parquet_path": str(pack_root),
                "metadata_path": str(manifest_path),
                "row_counts": {name: len(frame) for name, frame in tables.items()},
            }
        ]
    )

    data: dict[str, pd.DataFrame] = {
        "candidate_df": candidate,
        "finalists_df": finalists,
        "recommended": finalists,
        "summary": summary,
        "schiff_df": schiff,
        "schiff_benchmark": schiff,
        "ensemble_df": ensemble,
        "weights": ensemble,
        "stress_df": stress[stress["scenario_role"].eq("Finalist")].copy(),
        "stress": stress[stress["scenario_role"].eq("Finalist")].copy(),
        "horizon_df": horizon,
        "diagnostic_df": diagnostic_tests,
        "diagnostic_tests": diagnostic_tests,
        "diagnostic_pass_matrix": pass_matrix,
        "diagnostic_acf": acf,
        "quarterly_predictions": residual_predictions,
        "residual_predictions": residual_predictions,
        "error_distribution": error_distribution,
        "annual_predictions": annual_predictions,
        "paired_vs_schiff": paired,
        "scenario_comparison": scenario,
        "chart_contract": contract,
        "curated_manifest": curated_manifest,
        "errors": pd.DataFrame(),
        "features": pd.DataFrame(),
        "variant_features": pd.DataFrame(),
        "leaderboards": pd.DataFrame(),
        "quarterly_summary": pd.DataFrame(),
        "annual_summary": pd.DataFrame(),
        "audit_tables": pd.DataFrame(),
    }

    repo_path = Path(repo_root).expanduser() if repo_root is not None else Path.cwd()
    source_manifest = _build_manifest_artifact(root, pack_root, manifest, data_dir, tables)
    write_data_source_manifest(repo_path, source_manifest)
    _write_compat_source_tables(repo_path, data)
    write_chart_source_tables(repo_path, data)
    return DashboardEvidencePack(
        run_dir=pack_root,
        data=data,
        file_status=_file_status(pack_root, tables),
        warnings=tuple(),
        manifest=source_manifest,
    )


def _normalise_candidate(frame: pd.DataFrame) -> pd.DataFrame:
    out = normalise_parquet_candidate(frame)
    if "is_plot_candidate" not in out.columns:
        out["is_plot_candidate"] = out.get("plot_default_include", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["stage"] = "final"
    out["variant"] = out.get("feature_set", pd.Series("Evidence pack", index=out.index)).fillna("Evidence pack")
    out["source_file"] = "candidate_cone.parquet"
    return out


def _normalise_model_rows(frame: pd.DataFrame, *, scenario: str) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out = _coerce_percent_columns(out)
    out["stage"] = "final"
    out["variant"] = scenario
    out["scenario"] = scenario
    out["scenario_role"] = scenario
    out["source_family"] = "Evidence pack"
    out["model_kind"] = out.get("role", pd.Series(scenario, index=out.index))
    out["is_current_recommended"] = scenario == "Finalist"
    out["is_recommended_finalist"] = scenario == "Finalist"
    out["is_finalist"] = scenario == "Finalist"
    out["is_pure_schiff"] = scenario == "Schiff"
    out["is_schiff"] = scenario == "Schiff"
    out["source_file"] = "finalists.parquet" if scenario == "Finalist" else "schiff_benchmark.parquet"
    return out


def _normalise_ensemble_components(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out["ensemble"] = out.get("finalist_model", pd.Series(pd.NA, index=out.index))
    out["ensemble_short"] = out.get("finalist_model_short", pd.Series(pd.NA, index=out.index))
    out["model"] = out["ensemble"]
    out["model_short"] = out["ensemble_short"]
    out["stage"] = "final"
    out["variant"] = "Finalist"
    out["weight"] = pd.to_numeric(out.get("weight"), errors="coerce")
    if "weight_pct" not in out.columns:
        out["weight_pct"] = out["weight"] * 100.0
    out["source"] = "ensemble_components.parquet"
    out["source_file"] = "ensemble_components.parquet"
    return normalise_weights(out)


def _normalise_residual_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out["stage"] = "final"
    out["variant"] = out.get("scenario", pd.Series("Finalist", index=out.index)).fillna("Finalist")
    out["scenario_role"] = out["variant"]
    out["selected_role"] = out["variant"]
    if "abs_error_pct" in out.columns:
        out["ape"] = pd.to_numeric(out["abs_error_pct"], errors="coerce")
    out["source_file"] = "residual_predictions.parquet"
    return normalise_predictions(out, annual=False)


def _normalise_annual_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out["stage"] = "final"
    out["variant"] = out.get("scenario", pd.Series("Finalist", index=out.index)).fillna("Finalist")
    out["scenario_role"] = out["variant"]
    if "target_year" in out.columns and "target_period" not in out.columns:
        out["target_period"] = out["target_year"].astype(str)
    if "abs_error_pct" in out.columns:
        out["ape"] = pd.to_numeric(out["abs_error_pct"], errors="coerce")
    out["source_file"] = "annual_predictions.parquet"
    return normalise_predictions(out, annual=True)


def _normalise_horizon_profiles(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out = _coerce_percent_columns(out)
    out["scenario_role"] = out.get("scenario", pd.Series(pd.NA, index=out.index))
    out["stage"] = "final"
    out["variant"] = out["scenario_role"]
    out["source_file"] = "horizon_profiles.parquet"
    return out


def _normalise_stress_horizon(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out = _coerce_percent_columns(out)
    out["scenario_role"] = out.get("scenario", pd.Series(pd.NA, index=out.index))
    out["stage"] = "final"
    out["variant"] = out["scenario_role"]
    out["n_pairs"] = pd.to_numeric(out.get("n"), errors="coerce")
    out["source_column"] = "mape"
    out["source_file"] = "stress_horizon.parquet"
    out = normalise_stress(out)
    out["stress_bucket"] = pd.Categorical(out["stress_bucket"].astype(str), categories=STRESS_BUCKET_ORDER, ordered=True)
    return out.sort_values(["stream_label", "scenario_role", "stress_bucket"]).reset_index(drop=True)


def _normalise_diagnostic_tests(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out["stage"] = "final"
    out["variant"] = out.get("scenario", pd.Series(pd.NA, index=out.index))
    out["role"] = out.get("role", pd.Series("", index=out.index)).astype(str).replace({"Our finalist": "finalist", "Schiff benchmark": "schiff"})
    aliases = {
        "adj_r2": "calibration_r2",
        "adf_pvalue": "adf_p_resid",
        "kpss_pvalue": "kpss_p_resid",
        "breusch_pagan_pvalue": "breusch_pagan_p",
        "white_pvalue": "white_p",
        "arch_lm_pvalue": "arch_lm_p",
        "jarque_bera_pvalue": "jarque_bera_p",
        "cointegration_pvalue": "coint_p_actual_pred",
    }
    for target, source in aliases.items():
        if target not in out.columns and source in out.columns:
            out[target] = out[source]
    out["source_file"] = "diagnostic_tests.parquet"
    return _coerce_percent_columns(out)


def _normalise_pass_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out["stage"] = "final"
    out["variant"] = out.get("scenario", pd.Series("Finalist", index=out.index))
    out["source_file"] = "diagnostic_pass_matrix.parquet"
    return out


def _normalise_acf(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out = _coerce_percent_columns(out)
    out["stage"] = "final"
    out["variant"] = out.get("scenario", pd.Series("Finalist", index=out.index))
    out["calculation_method"] = out.get("calculation_method", pd.Series("Supplied diagnostic ACF", index=out.index))
    out["residual_source"] = out.get("residual_scope", pd.Series("Supplied diagnostic residual scope", index=out.index))
    out["source_file"] = "diagnostic_acf.parquet"
    return out


def _normalise_error_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out = _coerce_percent_columns(out)
    out["stage"] = "final"
    out["variant"] = out.get("scenario", pd.Series("Finalist", index=out.index))
    out["ape"] = pd.to_numeric(out.get("abs_error_pct"), errors="coerce")
    out["source_file"] = "error_distribution.parquet"
    return out


def _normalise_scenario_comparison(frame: pd.DataFrame, finalists: pd.DataFrame, schiff: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out = add_stream_fields(out)
    out = _coerce_percent_columns(out)
    finalist_models = finalists.set_index("stream_label")["model"].to_dict() if "model" in finalists.columns else {}
    schiff_models = schiff.set_index("stream_label")["model"].to_dict() if "model" in schiff.columns else {}
    out["finalist_model"] = out["stream_label"].map(finalist_models)
    out["schiff_model"] = out["stream_label"].map(schiff_models)
    out["quarterly_gain_pp"] = out["full_sample_qtr_gain_pp"]
    out["annual_gain_pp"] = out["full_sample_annual_gain_pp"]
    out["win_rate"] = out["paired_win_rate_pct"]
    out["source_file"] = "scenario_comparison.parquet"
    return out


def _paired_from_scenario(scenario: pd.DataFrame) -> pd.DataFrame:
    if scenario.empty:
        return pd.DataFrame()
    out = scenario.rename(
        columns={
            "paired_common_pairs": "n_common_pairs",
            "paired_schiff_mape": "baseline_mape",
            "paired_finalist_mape": "challenger_mape",
            "paired_gain_pp": "mape_improvement_pct_points",
            "paired_win_rate_pct": "challenger_win_rate",
            "schiff_model": "baseline",
            "finalist_model": "challenger",
        }
    ).copy()
    out["stage"] = "final"
    out["variant"] = "Finalist vs Schiff"
    out["source_file"] = "scenario_comparison.parquet"
    return normalise_paired(out)


def _coerce_percent_columns(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        column
        for column in frame.columns
        if any(token in str(column).lower() for token in ["mape", "bias", "ape", "gain", "rate", "r2", "acf", "durbin", "pvalue", "_p"])
    ]
    out = frame.copy()
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return scale_percent_columns(out)


def _build_manifest_artifact(
    requested_root: str | Path | None,
    pack_root: Path,
    manifest: dict[str, Any],
    data_dir: Path,
    tables: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_mode": "dashboard_evidence_pack",
        "schema_version": manifest.get("schema_version"),
        "requested_data_root": str(Path(requested_root or DEFAULT_EVIDENCE_PACK_ROOT).expanduser()),
        "resolved_root": str(pack_root),
        "manifest_path": str(pack_root / "manifest.json"),
        "data_dir": str(data_dir),
        "required_files": list(REQUIRED_EVIDENCE_TABLES),
        "resolved_paths": {name: str(data_dir / f"{name}.parquet") for name in tables},
        "row_counts": {name: int(len(frame)) for name, frame in tables.items()},
        "required_dashboard_rule": manifest.get("required_dashboard_rule"),
    }


def _file_status(pack_root: Path, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, frame in tables.items():
        path = pack_root / "data" / f"{name}.parquet"
        stat = path.stat()
        rows.append(
            {
                "Dataset": name.replace("_", " ").title(),
                "File": path.name,
                "Found?": "Yes",
                "Rows": f"{len(frame):,}",
                "Columns": f"{len(frame.columns):,}",
                "Size": _format_size(stat.st_size),
                "Last modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return pd.DataFrame(rows)


def _write_compat_source_tables(repo_root: Path, data: dict[str, pd.DataFrame]) -> None:
    artifacts = repo_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    ensemble = data["weights"].copy()
    ensemble["weight_pct"] = pd.to_numeric(ensemble["weight"], errors="coerce") * 100.0
    ensemble.rename(columns={"ensemble_short": "model_short"}, inplace=True)
    _write_csv_atomic(
        ensemble[
        ["stream_label", "model_short", "component_rank", "component_short", "component_model", "weight", "weight_pct", "source"]
        ],
        artifacts / "ensemble_composition_source_table.csv",
    )

    scenario = data["scenario_comparison"].copy()
    scenario.rename(
        columns={
            "finalist_model": "scenario_a_model",
            "schiff_model": "scenario_b_model",
            "finalist_quarterly_mape": "scenario_a_quarterly_mape",
            "schiff_quarterly_mape": "scenario_b_quarterly_mape",
            "finalist_annual_mape": "scenario_a_annual_mape",
            "schiff_annual_mape": "scenario_b_annual_mape",
            "paired_finalist_mape": "paired_model_mape",
            "full_sample_qtr_gain_pp": "full_sample_qtr_gain_pp",
        },
        inplace=True,
    )
    _write_csv_atomic(
        scenario[
        [
            "stream_label",
            "scenario_a_model",
            "scenario_b_model",
            "scenario_a_quarterly_mape",
            "scenario_b_quarterly_mape",
            "scenario_a_annual_mape",
            "scenario_b_annual_mape",
            "full_sample_qtr_gain_pp",
            "full_sample_annual_gain_pp",
            "paired_common_pairs",
            "paired_model_mape",
            "paired_schiff_mape",
            "paired_gain_pp",
            "paired_win_rate_pct",
            "recommendation",
        ]
        ],
        artifacts / "scenario_comparison_source_table.csv",
    )

    horizon_rows = []
    for _, row in data["horizon_df"].iterrows():
        for page in ["Scenario Comparison", "Schiff Benchmark"]:
            horizon_rows.append(
                {
                    "page": page,
                    "stream_label": row.get("stream_label"),
                    "scenario": row.get("scenario_role"),
                    "horizon": row.get("horizon"),
                    "mape": row.get("mape"),
                    "source_column": row.get("source_column", "mape"),
                    "source": "horizon_profiles.parquet",
                }
            )
    _write_csv_atomic(pd.DataFrame(horizon_rows), artifacts / "horizon_comparison_source_table.csv")
    acf_source = select_diagnostic_acf_scope(data["diagnostic_acf"], DEFAULT_ACF_RESIDUAL_SCOPE)
    _write_csv_atomic(acf_source, artifacts / "diagnostic_acf_source_table.csv")
    _write_csv_atomic(_diagnostic_kpi_source_table(data["diagnostic_df"]), artifacts / "diagnostics_kpi_source_table.csv")
    _write_diagnostic_status_rules(artifacts / "diagnostic_status_rules.md")


def _diagnostic_kpi_source_table(diagnostics: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "kpi",
        "basis",
        "stream_label",
        "model",
        "role",
        "source_column",
        "value",
        "source_file",
    ]
    if diagnostics is None or diagnostics.empty:
        return pd.DataFrame(columns=columns)
    data = diagnostics.copy()
    if "role" in data.columns:
        finalists = data[data["role"].astype(str).str.contains("finalist", case=False, na=False)].copy()
        if not finalists.empty:
            data = finalists
    rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        for kpi, column in [
            ("Mean Durbin-Watson", "durbin_watson"),
            ("Mean calibration R2", "calibration_r2" if "calibration_r2" in data.columns else "adj_r2"),
            ("Heteroscedasticity Pass", "breusch_pagan_pvalue"),
            ("Heteroscedasticity Pass", "white_pvalue"),
        ]:
            if column not in data.columns:
                continue
            rows.append(
                {
                    "kpi": kpi,
                    "basis": "Current finalist rows only",
                    "stream_label": row.get("stream_label"),
                    "model": row.get("model"),
                    "role": row.get("role"),
                    "source_column": column,
                    "value": row.get(column),
                    "source_file": "diagnostic_tests.parquet",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _write_diagnostic_status_rules(path: Path) -> None:
    content = """# Diagnostic Status Rules

Status: PASS

Diagnostic Pass Matrix uses Pass / Watch / Fail semantics.

- Core diagnostics: Durbin-Watson, ADF, KPSS, Breusch-Pagan, White and Cointegration.
- Overall = Fail when one or more core diagnostics fail.
- Overall = Watch when all core diagnostics pass but a non-core diagnostic such as Jarque-Bera is cautionary.
- Overall = Pass when core diagnostics pass and no non-core caution is present.
- Normality is advisory evidence. Jarque-Bera alone must not force Overall = Fail.
"""
    path.write_text(content, encoding="utf-8")


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False)
    for attempt in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.25 * (attempt + 1))


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


__all__ = [
    "DashboardEvidencePack",
    "REQUIRED_EVIDENCE_TABLES",
    "evidence_pack_signature",
    "load_evidence_pack",
    "resolve_evidence_pack_root",
]
