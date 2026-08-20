"""Prove the generic delayed_6m state equals the legacy six-month answer.

Runs the same captures as ``scripts/characterize_legacy_6m_reference.py`` on
the CURRENT tree and compares them against the committed reference under
``artifacts/fed_deferral_duration/legacy_6m_reference`` (generated at the
recorded base SHA). Writes ``artifacts/fed_deferral_duration/
six_month_parity.csv`` with one row per compared frame.

Comparison contract:
  * frames whose schema or row set legitimately grew (rate schedules gained
    per-duration columns; replay frames gained the new policy scenarios) are
    compared on the legacy subset - same columns, same key-sorted rows;
  * frames the six-month state fully determines (chart rows, audits, detail
    frames, extract rows for the original 12 paths, uncertainty rows) must be
    exactly equal;
  * any difference is a hard failure - "close enough" is not accepted.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ABS_TOLERANCE = 0.0  # exact by default; never widened


def _read_reference(reference_dir: Path, name: str) -> pd.DataFrame | None:
    path = reference_dir / f"{name}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def _sorted_for_compare(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    keys = [c for c in ("scenario_name", "series_id", "stream", "pair_id", "path_id",
                        "policy_path_id", "quarter", "period", "canonical_period",
                        "target_period", "time_grain", "FY", "june_year", "fy",
                        "component", "trace_name", "scenario_role", "fed_path")
            if c in columns]
    ordered = frame[columns].copy()
    if keys:
        ordered = ordered.sort_values(keys, kind="stable")
    return ordered.reset_index(drop=True)


def compare_frames(
    name: str,
    current: pd.DataFrame,
    reference: pd.DataFrame,
    results: list[dict],
    *,
    subset_columns: bool = False,
) -> None:
    if reference is None:
        results.append({"frame": name, "status": "NO_REFERENCE", "detail": ""})
        return
    columns = sorted(set(reference.columns) & set(current.columns)) if subset_columns else sorted(reference.columns)
    missing = sorted(set(reference.columns) - set(current.columns))
    if missing:
        results.append({
            "frame": name,
            "status": "FAIL",
            "detail": f"columns missing from current: {missing[:6]}",
        })
        return
    ref = _sorted_for_compare(reference, columns)
    cur = _sorted_for_compare(current, columns)
    if len(ref) != len(cur):
        results.append({
            "frame": name,
            "status": "FAIL",
            "detail": f"row count {len(cur)} != reference {len(ref)}",
        })
        return
    worst = 0.0
    worst_col = ""
    for column in columns:
        ref_col = ref[column]
        cur_col = cur[column]
        if ref_col.dtype == bool or cur_col.dtype == bool:
            ref_col = ref_col.astype(str)
            cur_col = cur_col.astype(str)
        ref_num = pd.to_numeric(ref_col, errors="coerce").astype("float64")
        cur_num = pd.to_numeric(cur_col, errors="coerce").astype("float64")
        numeric_mask = ref_num.notna() | cur_num.notna()
        if numeric_mask.any():
            if not (ref_num.isna() == cur_num.isna()).all():
                results.append({
                    "frame": name, "status": "FAIL",
                    "detail": f"NaN pattern differs in {column}",
                })
                return
            delta = (ref_num - cur_num).abs().max()
            if pd.notna(delta) and float(delta) > worst:
                worst, worst_col = float(delta), column
        text_mask = ~numeric_mask
        if text_mask.any():
            ref_text = ref_col[text_mask].fillna("").astype(str)
            cur_text = cur_col[text_mask].fillna("").astype(str)
            if not ref_text.eq(cur_text).all():
                bad = ref_text[~ref_text.eq(cur_text)]
                results.append({
                    "frame": name, "status": "FAIL",
                    "detail": f"text differs in {column} ({len(bad)} rows)",
                })
                return
    status = "PASS" if worst <= ABS_TOLERANCE else "FAIL"
    results.append({
        "frame": name,
        "status": status,
        "detail": f"max_abs_delta={worst:.3g} in {worst_col}" if worst else "exact",
        "rows": len(ref),
        "columns": len(columns),
        "max_abs_delta": worst,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo_root))
    import os

    os.chdir(repo_root)
    reference_dir = repo_root / "artifacts" / "fed_deferral_duration" / "legacy_6m_reference"
    manifest = json.loads((reference_dir / "manifest.json").read_text(encoding="utf-8"))

    import app  # noqa: E402
    from model_dashboard.engine import ENGINE_AR1, ENGINE_ENSEMBLE, engine_revenue_outlook_dir  # noqa: E402
    from model_dashboard import rate_paths  # noqa: E402
    from model_dashboard.revenue_outlook import (  # noqa: E402
        PED_BRIDGE_DEFAULT_MODE,
        net_revenue_timing_comparison_frame,
        revenue_outlook_signature,
    )
    from scripts.build_revenue_outlook_policy_runtime import governed_key  # noqa: E402

    app.POLICY_RUNTIME_FAST_PATH_ENABLED = False
    results: list[dict] = []

    # ------------------------------------------------------------ rate paths
    quarterly = rate_paths.ped_quarterly_rate_schedules(repo_root).reset_index()
    compare_frames(
        "quarterly_ped_schedules",
        quarterly,
        _read_reference(reference_dir, "quarterly_ped_schedules"),
        results,
        subset_columns=True,
    )
    affected = rate_paths.fed_policy_affected_periods(repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M)
    reference_affected = json.loads((reference_dir / "affected_periods_delay_6m.json").read_text())
    results.append({
        "frame": "affected_periods_delay_6m",
        "status": "PASS" if {str(k): list(v) for k, v in affected.items()} == reference_affected else "FAIL",
        "detail": str(affected),
    })
    for name, state in (
        ("quarterly_factors_delay_6m", rate_paths.FED_POLICY_STATE_DELAYED_6M),
        ("quarterly_factors_no_uplift", rate_paths.FED_POLICY_STATE_NO_UPLIFT),
    ):
        current_factors = rate_paths.fed_policy_quarterly_factors(repo_root, state)
        reference_factors = json.loads((reference_dir / f"{name}.json").read_text())
        exact = set(current_factors) == set(reference_factors) and all(
            float(current_factors[k]) == float(reference_factors[k]) for k in current_factors
        )
        results.append({"frame": name, "status": "PASS" if exact else "FAIL", "detail": ""})

    compare_frames(
        "official_comparator_factors_delay_6m",
        rate_paths.official_comparator_policy_factors(repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M),
        _read_reference(reference_dir, "official_comparator_factors_delay_6m"),
        results,
    )
    compare_frames(
        "official_comparator_audit_delay_6m",
        rate_paths.official_comparator_policy_audit_frame(repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M),
        _read_reference(reference_dir, "official_comparator_audit_delay_6m"),
        results,
    )

    for engine in (ENGINE_AR1, ENGINE_ENSEMBLE):
        prefix = f"{engine}__"
        pack_dir = repo_root / engine_revenue_outlook_dir(engine)
        signature = revenue_outlook_signature(pack_dir, repo_root)
        pack = app.cached_load_revenue_outlook_pack(
            str(pack_dir), str(repo_root), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
        )
        assert pack is not None, engine

        annual = rate_paths.ped_rate_schedules(repo_root, pack.revenue_chart_rows).reset_index()
        compare_frames(
            prefix + "annual_ped_schedules",
            annual,
            _read_reference(reference_dir, prefix + "annual_ped_schedules"),
            results,
            subset_columns=True,
        )
        for name, state in (
            (prefix + "annual_factors_delay_6m", rate_paths.FED_POLICY_STATE_DELAYED_6M),
            (prefix + "annual_factors_no_uplift", rate_paths.FED_POLICY_STATE_NO_UPLIFT),
        ):
            current_factors = rate_paths.fed_policy_annual_factors(
                repo_root, pack.revenue_chart_rows, state
            )
            reference_factors = json.loads((reference_dir / f"{name}.json").read_text())
            exact = {str(k) for k in current_factors} == set(reference_factors) and all(
                float(current_factors[int(k)]) == float(v) for k, v in reference_factors.items()
            )
            results.append({"frame": name, "status": "PASS" if exact else "FAIL", "detail": ""})

        replay = app.cached_fuel_price_scenario_replay(signature, pack)

        inputs = replay.policy_scenario_inputs
        legacy_policy_rows = inputs[
            inputs.get("policy_state", pd.Series(dtype=str)).astype(str).isin(
                {"delay_6m", "no_uplift"}
            )
        ]
        compare_frames(
            prefix + "policy_scenario_inputs_policy_rows",
            legacy_policy_rows,
            _read_reference(reference_dir, prefix + "policy_scenario_inputs_policy_rows"),
            results,
            subset_columns=True,
        )
        pair = replay.policy_pair_factors
        compare_frames(
            prefix + "policy_pair_factors_delayed_6m",
            pair[pair["pair_id"].astype(str).str.contains("delayed_6m")],
            _read_reference(reference_dir, prefix + "policy_pair_factors_delayed_6m"),
            results,
        )
        bridge = replay.annual_bridge
        compare_frames(
            prefix + "annual_bridge_shifted_6m",
            bridge[bridge["policy_path_id"].astype(str).str.contains("shifted_6m")],
            _read_reference(reference_dir, prefix + "annual_bridge_shifted_6m"),
            results,
            subset_columns=True,
        )
        calibrated = replay.future_forecasts
        legacy_delay_names = {
            name
            for name in calibrated.get("scenario_name", pd.Series(dtype=str)).astype(str).unique()
            if "delay_6m" in name
        }
        compare_frames(
            prefix + "future_forecasts_delay_scenarios",
            calibrated[calibrated["scenario_name"].astype(str).isin(legacy_delay_names)],
            _read_reference(reference_dir, prefix + "future_forecasts_delay_scenarios"),
            results,
            subset_columns=True,
        )
        calibration_audit = replay.policy_demand_calibration_audit
        if not calibration_audit.empty and "scenario_name" in calibration_audit.columns:
            compare_frames(
                prefix + "policy_demand_calibration_audit_delay",
                calibration_audit[
                    calibration_audit["scenario_name"].astype(str).str.contains("delay_6m")
                ],
                _read_reference(reference_dir, prefix + "policy_demand_calibration_audit_delay"),
                results,
                subset_columns=True,
            )

        sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
        for label, current_state, official_state in (
            ("cur-delayed_6m__off-published", "delayed_6m", "published"),
            ("cur-published__off-delayed_6m", "published", "delayed_6m"),
        ):
            key = governed_key(pack, engine, current_state, official_state)
            recorded_digest = manifest["engines"][engine][label]["scenario_key_digest"]
            results.append({
                "frame": f"{prefix}{label}__scenario_key_digest",
                "status": "PASS" if key.digest() == recorded_digest else "FAIL",
                "detail": key.digest(),
            })
            chart_rows, _uptake, _eruc, policy_audit, _scenario_audit = (
                app.cached_scenario_overlay_rows(
                    signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
                )
            )
            touched = (
                chart_rows[chart_rows["_fed_policy"].astype(str).ne("")]
                if "_fed_policy" in chart_rows.columns
                else pd.DataFrame()
            )
            compare_frames(
                f"{prefix}{label}__chart_rows_policy_touched",
                touched,
                _read_reference(reference_dir, f"{prefix}{label}__chart_rows_policy_touched"),
                results,
            )
            compare_frames(
                f"{prefix}{label}__policy_audit",
                policy_audit if isinstance(policy_audit, pd.DataFrame) else pd.DataFrame(),
                _read_reference(reference_dir, f"{prefix}{label}__policy_audit"),
                results,
            )
            line, residuals, stack, bridge_components = app.cached_aligned_scenario_detail_frames(
                signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
            )
            if label == "cur-delayed_6m__off-published":
                compare_frames(
                    f"{prefix}central_line_rows_delayed_6m",
                    line[line["scenario_name"].astype(str).eq("current_basecase")],
                    _read_reference(reference_dir, f"{prefix}central_line_rows_delayed_6m"),
                    results,
                )
                factors = app.cached_fed_uplift_factors(signature, pack)["delayed_6m"]
                comparison = net_revenue_timing_comparison_frame(
                    chart_rows, factors, policy_timing_rows=replay.annual_bridge
                )
                reference_extract = _read_reference(reference_dir, f"{prefix}timing_comparison_extract")
                legacy_paths = set(reference_extract["path_id"].astype(str))
                compare_frames(
                    f"{prefix}timing_comparison_extract_legacy_paths",
                    comparison[comparison["path_id"].astype(str).isin(legacy_paths)].drop(
                        columns=["path_order"]
                    ),
                    reference_extract.drop(columns=["path_order"]),
                    results,
                    subset_columns=True,
                )
                results.append({
                    "frame": f"{prefix}timing_comparison_row_count",
                    "status": "PASS" if len(comparison) == 480 else "FAIL",
                    "detail": f"rows={len(comparison)}",
                })

    parity = pd.DataFrame(results)
    out_path = repo_root / "artifacts" / "fed_deferral_duration" / "six_month_parity.csv"
    parity.to_csv(out_path, index=False)
    failures = parity[parity["status"].eq("FAIL")]
    print(parity.to_string(index=False, max_colwidth=60))
    if not failures.empty:
        print(f"\nPARITY FAILED on {len(failures)} frames")
        return 1
    print(f"\nPARITY PASSED on {len(parity)} comparisons -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
