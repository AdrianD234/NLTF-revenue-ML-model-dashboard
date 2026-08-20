"""Characterise the production six-month FED deferral answer at the base SHA.

Run with the repo's .venv python, cwd anywhere, passing:
    --repo-root <path to clean checkout at the base SHA>
    --out <output directory for the reference evidence>

Captures, for both engines (ar1, ensemble):
  * quarterly PED schedules (planned / no-uplift / delayed_6m) and factors;
  * directly affected quarters and annual factors;
  * PED / Light RUC / Heavy RUC policy scenario inputs (audit fields);
  * rebuilt Light lag and Heavy lead columns;
  * raw and structurally calibrated forecasts for the policy scenarios;
  * annual bridge rows per policy path;
  * policy pair factors (baseline_delayed_6m);
  * full chart rows + policy audit for current=delayed_6m x official=published
    and current=published x official=delayed_6m (reference pipeline, fast
    path disabled);
  * aligned detail frames (line reconciliation, formula residuals, stack,
    bridge components);
  * the 12-path FY2026-FY2030 net revenue timing comparison extract;
  * official comparator factors and audit for delay_6m;
  * uncertainty band rows for the delayed_6m centre (from the committed
    policy runtime pack, whose build verified them against the reference);
  * sha256 of every full frame (canonical CSV bytes) plus the complete
    policy-relevant rows as CSVs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def canonical_frame_hash(frame: pd.DataFrame) -> str:
    """Deterministic content hash of a frame (column-name sorted CSV bytes)."""
    if frame is None:
        return "none"
    ordered = frame[sorted(frame.columns)].copy()
    payload = ordered.to_csv(index=False, float_format="%.17g").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(repo_root))
    import os

    os.chdir(repo_root)

    import app  # noqa: E402
    from model_dashboard.engine import ENGINE_AR1, ENGINE_ENSEMBLE, engine_revenue_outlook_dir  # noqa: E402
    from model_dashboard import rate_paths  # noqa: E402
    from model_dashboard.revenue_outlook import (  # noqa: E402
        PED_BRIDGE_DEFAULT_MODE,
        net_revenue_timing_comparison_frame,
        revenue_outlook_signature,
    )
    from scripts.build_revenue_outlook_policy_runtime import governed_key  # noqa: E402

    # The reference pipeline, never the materialised fast path.
    app.POLICY_RUNTIME_FAST_PATH_ENABLED = False

    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.strip()

    manifest: dict = {
        "base_sha": base_sha,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "characterize_legacy_6m.py",
        "policy_states": {
            "current": "delayed_6m (runtime id) / delay_6m (calculation id)",
            "official": "delayed_6m",
        },
        "engines": {},
        "source_hashes": {},
        "frame_hashes": {},
        "row_counts": {},
    }

    for rel in (
        "data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv",
        "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv",
        "data/current_revenue_outlook/sensitivity_seed_inputs.csv",
    ):
        path = repo_root / rel
        manifest["source_hashes"][rel] = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"
        )

    def record(name: str, frame: pd.DataFrame, *, write_full: bool = True) -> None:
        manifest["frame_hashes"][name] = canonical_frame_hash(frame)
        manifest["row_counts"][name] = int(len(frame)) if frame is not None else 0
        if write_full and frame is not None:
            frame.to_csv(out_dir / f"{name}.csv", index=False)

    # ------------------------------------------------------------ rate paths
    quarterly = rate_paths.ped_quarterly_rate_schedules(repo_root).reset_index()
    record("quarterly_ped_schedules", quarterly)

    affected = rate_paths.fed_policy_affected_periods(repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M)
    (out_dir / "affected_periods_delay_6m.json").write_text(
        json.dumps({str(k): list(v) for k, v in affected.items()}, indent=2, sort_keys=True)
    )
    qfactors = rate_paths.fed_policy_quarterly_factors(repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M)
    (out_dir / "quarterly_factors_delay_6m.json").write_text(
        json.dumps(qfactors, indent=2, sort_keys=True)
    )
    qfactors_off = rate_paths.fed_policy_quarterly_factors(repo_root, rate_paths.FED_POLICY_STATE_NO_UPLIFT)
    (out_dir / "quarterly_factors_no_uplift.json").write_text(
        json.dumps(qfactors_off, indent=2, sort_keys=True)
    )

    official_delay = rate_paths.official_comparator_policy_factors(
        repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M
    )
    record("official_comparator_factors_delay_6m", official_delay)
    official_audit = rate_paths.official_comparator_policy_audit_frame(
        repo_root, rate_paths.FED_POLICY_STATE_DELAYED_6M
    )
    record("official_comparator_audit_delay_6m", official_audit)

    for engine in (ENGINE_AR1, ENGINE_ENSEMBLE):
        prefix = f"{engine}__"
        pack_dir = repo_root / engine_revenue_outlook_dir(engine)
        signature = revenue_outlook_signature(pack_dir, repo_root)
        pack = app.cached_load_revenue_outlook_pack(
            str(pack_dir), str(repo_root), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
        )
        assert pack is not None, engine

        annual = rate_paths.ped_rate_schedules(repo_root, pack.revenue_chart_rows).reset_index()
        record(prefix + "annual_ped_schedules", annual)
        annual_delay = rate_paths.fed_uplift_delayed_factors(repo_root, pack.revenue_chart_rows)
        (out_dir / f"{prefix}annual_factors_delay_6m.json").write_text(
            json.dumps({str(k): v for k, v in annual_delay.items()}, indent=2, sort_keys=True)
        )
        annual_off = rate_paths.fed_uplift_off_factors(repo_root, pack.revenue_chart_rows)
        (out_dir / f"{prefix}annual_factors_no_uplift.json").write_text(
            json.dumps({str(k): v for k, v in annual_off.items()}, indent=2, sort_keys=True)
        )

        replay = app.cached_fuel_price_scenario_replay(signature, pack)

        # Policy scenario inputs: keep the complete frame hash plus the
        # policy-relevant rows (delay/no-uplift scenarios) in full.
        inputs = replay.policy_scenario_inputs
        record(prefix + "policy_scenario_inputs_full", inputs, write_full=False)
        policy_rows = inputs[inputs.get("policy_state", pd.Series(dtype=str)).astype(str).ne("")]
        record(prefix + "policy_scenario_inputs_policy_rows", policy_rows)

        pair = replay.policy_pair_factors
        record(prefix + "policy_pair_factors_full", pair, write_full=False)
        record(
            prefix + "policy_pair_factors_delayed_6m",
            pair[pair["pair_id"].astype(str).str.contains("delayed_6m")],
        )

        bridge = replay.annual_bridge
        record(prefix + "annual_bridge_full", bridge, write_full=False)
        if "policy_path_id" in bridge.columns:
            record(
                prefix + "annual_bridge_shifted_6m",
                bridge[bridge["policy_path_id"].astype(str).str.contains("shifted_6m")],
            )

        raw_components = getattr(replay.replay, "component_forecasts", None)
        if isinstance(raw_components, pd.DataFrame):
            record(prefix + "raw_component_forecasts_full", raw_components, write_full=False)
        structural = replay.structural_component_forecasts
        record(prefix + "structural_component_forecasts_full", structural, write_full=False)
        calibrated = replay.future_forecasts
        record(prefix + "future_forecasts_full", calibrated, write_full=False)
        if "scenario_name" in calibrated.columns:
            delay_scen = calibrated[
                calibrated["scenario_name"].astype(str).str.contains("delay", case=False)
            ]
            record(prefix + "future_forecasts_delay_scenarios", delay_scen)
        calibration_audit = replay.policy_demand_calibration_audit
        record(prefix + "policy_demand_calibration_audit_full", calibration_audit, write_full=False)
        if not calibration_audit.empty and "scenario_name" in calibration_audit.columns:
            record(
                prefix + "policy_demand_calibration_audit_delay",
                calibration_audit[
                    calibration_audit["scenario_name"].astype(str).str.contains("delay", case=False)
                ],
            )
        record(prefix + "policy_validation_report", replay.policy_validation_report, write_full=False)
        record(prefix + "input_audit_full", replay.input_audit, write_full=False)
        record(prefix + "quarterly_factors_full", replay.quarterly_factors, write_full=False)
        record(prefix + "annual_factors_full", replay.annual_factors, write_full=False)
        record(prefix + "replay_inputs_full", replay.replay_inputs, write_full=False)

        sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")

        for label, current_state, official_state in (
            ("cur-delayed_6m__off-published", "delayed_6m", "published"),
            ("cur-published__off-delayed_6m", "published", "delayed_6m"),
        ):
            key = governed_key(pack, engine, current_state, official_state)
            chart_rows, uptake_audit, eruc_audit, policy_audit, scenario_audit = (
                app.cached_scenario_overlay_rows(
                    signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
                )
            )
            record(f"{prefix}{label}__chart_rows", chart_rows, write_full=False)
            record(
                f"{prefix}{label}__policy_audit",
                policy_audit if isinstance(policy_audit, pd.DataFrame) else pd.DataFrame(),
            )
            record(
                f"{prefix}{label}__scenario_audit",
                scenario_audit if isinstance(scenario_audit, pd.DataFrame) else pd.DataFrame(),
                write_full=False,
            )
            # Policy-touched chart rows in full (the six-month wedge itself).
            if "_fed_policy" in chart_rows.columns:
                touched = chart_rows[chart_rows["_fed_policy"].astype(str).ne("")]
                record(f"{prefix}{label}__chart_rows_policy_touched", touched)

            line, residuals, stack, bridge_components = app.cached_aligned_scenario_detail_frames(
                signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
            )
            record(f"{prefix}{label}__line_reconciliation", line, write_full=False)
            record(f"{prefix}{label}__formula_residuals", residuals, write_full=False)
            record(f"{prefix}{label}__stack_components", stack, write_full=False)
            record(f"{prefix}{label}__bridge_components", bridge_components, write_full=False)
            manifest["engines"].setdefault(engine, {})[label] = {
                "scenario_key_digest": key.digest(),
                "scenario_key": key.canonical_mapping(),
            }

            if label == "cur-delayed_6m__off-published":
                # The extract built under the six-month current state.
                factors = app.cached_fed_uplift_factors(signature, pack)["delayed_6m"]
                comparison = net_revenue_timing_comparison_frame(
                    chart_rows, factors, policy_timing_rows=replay.annual_bridge
                )
                record(f"{prefix}timing_comparison_extract", comparison)
                # Selected central line rows for the uncertainty centre check.
                central = line[line["scenario_name"].astype(str).eq("current_basecase")]
                record(f"{prefix}central_line_rows_delayed_6m", central)

        # Committed policy-aware uncertainty rows for the delayed_6m centre.
        bands_path = repo_root / "data" / "revenue_outlook_policy_runtime" / engine / "uncertainty_band_rows.parquet"
        if bands_path.exists():
            bands = pd.read_parquet(bands_path)
            selected = bands[bands["policy_state"].astype(str).eq("delayed_6m")]
            record(prefix + "uncertainty_band_rows_delayed_6m", selected)

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
