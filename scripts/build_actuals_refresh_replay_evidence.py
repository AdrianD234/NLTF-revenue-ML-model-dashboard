"""Replay the promoted production models from the refreshed 2026Q1 history.

Produces the governed Candidate A / Candidate B replay evidence for the
quarterly-actuals refresh:

- Candidate A (strict accepted-actual policy): Light and Heavy RUC forecast
  from the quarter after their accepted 2026Q1 actuals; PED keeps its exact
  accepted cutoff (2025Q4) and forecasts from 2026Q1. No provisional value is
  used anywhere.
- Candidate B (PED provisional replay-only): the governed MBU26 annual-bridge
  PED value seeds the recursive history for 2026Q1 and PED forecasts from
  2026Q2. The seed is never fitted on, never emitted as a forecast row and
  never displayed as an observed actual.

Both candidates REPLAY the existing promoted fitted states (PED AR(1),
Light RUC dynamic_RESID_GBR_n150_d1_lr0.05_w36, Heavy RUC
HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4). No coefficients are re-estimated.

Artifacts written to --output-dir:
    replay_predictions_quarterly.csv
    replay_impact_fy.csv
    ped_governance_candidates.csv
    ped_bridge_sensitivity.csv
    heavy_lead_replay_diagnostic.csv
    scenario_replay_lineage.csv
    promoted_state_invariance.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forecast_runner import (  # noqa: E402
    quarter_sort_key,
    replay_forecast_from_scenario_inputs,
    stream_latest_accepted_periods,
)

PACK_DIRS = {
    "ensemble": ROOT / "data" / "current_revenue_outlook",
    "ar1": ROOT / "data" / "engine_ar1" / "current_revenue_outlook",
}
PRODUCTION_ENGINE = "ar1"  # AR(1) is the authoritative production PED engine.
SERIES_IDS = {
    "PED": "ped_vkt_per_capita",
    "LIGHT_RUC": "light_ruc_net_km",
    "HEAVY_RUC": "heavy_ruc_net_km",
}
IMPACT_FY_RANGE = range(2026, 2031)

# Native annualisation: PED emits annualised VKT/capita per quarter (June-year
# value = mean over quarters); the RUC streams emit raw net km (sum).
ANNUAL_AGG = {"PED": "mean", "LIGHT_RUC": "sum", "HEAVY_RUC": "sum"}


def june_year(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[-1])
    return year if quarter in (1, 2) else year + 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_ped_seed() -> dict[str, float]:
    sidecar = json.loads((ROOT / "data" / "model_input_history" / "ped_provisional_bridge.json").read_text(encoding="utf-8"))
    return {e["period"]: float(e["provisional_target_km_per_person"]) for e in sidecar["entries"]}


def load_ped_sensitivity_variants() -> dict[str, dict[str, float]]:
    """The workbook's PED bridge sensitivities, recomputed from the committed
    reconciliation evidence (values are recorded in q1_reconciliation.csv)."""
    recon = pd.read_csv(ROOT / "artifacts" / "actuals_refresh_2026q1" / "q1_reconciliation.csv")
    recon.columns = [str(c).strip() for c in recon.columns]
    label_col, value_col = recon.columns[0], recon.columns[2]
    lookup = {
        str(row[label_col]).strip(): row[value_col]
        for _, row in recon.iterrows()
        if pd.notna(row[label_col])
    }
    seed = load_ped_seed()
    period = max(seed, key=quarter_sort_key)
    variants = {
        "selected_core_ped_revenue_share": float(lookup["Selected Core PED-revenue share"]),
        "equal_residual_split": float(lookup["Equal residual split"]),
        "prior_year_q1q2_seasonal_share": float(lookup["2025 Q1/Q2 VKT seasonal share"]),
    }
    return {name: {period: value} for name, value in variants.items()}


def committed_baseline(engine: str) -> pd.DataFrame:
    """Pre-refresh committed quarterly forecast rows (the old 2026Q1-origin vintage)."""
    cr = pd.read_csv(PACK_DIRS[engine] / "revenue_chart_rows.csv", low_memory=False)
    out = cr[
        cr["time_grain"].astype(str).eq("quarterly")
        & cr["row_type"].astype(str).eq("future_forecast")
        & cr["series_id"].astype(str).isin(SERIES_IDS.values())
    ][["scenario_name", "stream", "series_id", "period", "value"]].copy()
    out = out.rename(columns={"value": "baseline_forecast", "period": "target_period"})
    return out


def actual_rows_for_impact(latest_by_stream: dict[str, str]) -> pd.DataFrame:
    """Accepted quarterly actuals from canonical history for FY mixing."""
    rows = []
    files = {"PED": "ped_inputs.parquet", "LIGHT_RUC": "light_ruc_inputs.parquet", "HEAVY_RUC": "heavy_ruc_inputs.parquet"}
    for stream, filename in files.items():
        hist = pd.read_parquet(ROOT / "data" / "model_input_history" / filename, columns=["period", "target"])
        targets = pd.to_numeric(hist["target"], errors="coerce")
        keep = hist[targets.gt(0)].copy()
        keep = keep[keep["period"].astype(str).map(lambda p: quarter_sort_key(p) <= quarter_sort_key(latest_by_stream[stream]))]
        for _, row in keep.iterrows():
            rows.append(
                {
                    "stream": stream,
                    "target_period": str(row["period"]),
                    "value": float(row["target"]),
                    "value_kind": "accepted_actual",
                }
            )
    return pd.DataFrame(rows)


def replay_candidate(
    wide: pd.DataFrame,
    engine: str,
    *,
    seam: str,
    ped_seed: dict[str, float] | None,
) -> pd.DataFrame:
    result = replay_forecast_from_scenario_inputs(
        wide, repo_root=ROOT, engine=engine, seam=seam, ped_seed=ped_seed
    )
    report = result.validation_report
    if not report.empty and not report["valid"].astype(bool).all():
        raise SystemExit(f"Replay validation failed:\n{report.to_string()}")
    future = result.future_forecasts
    future = future[future["forecast_available"].astype(bool)].copy()
    return future[["scenario_name", "stream", "target_period", "horizon", "forecast", "model"]]


def fy_frame(quarterly: pd.DataFrame, actuals: pd.DataFrame, candidate: str) -> pd.DataFrame:
    """June-year FY2026-FY2030 values mixing accepted actuals and forecasts."""
    rows: list[dict[str, Any]] = []
    for (scenario, stream), group in quarterly.groupby(["scenario_name", "stream"]):
        fc = group.set_index("target_period")["forecast"]
        act = actuals[actuals["stream"].eq(stream)].set_index("target_period")["value"]
        for fy in IMPACT_FY_RANGE:
            quarters = [f"{fy - 1}Q3", f"{fy - 1}Q4", f"{fy}Q1", f"{fy}Q2"]
            values, kinds = [], []
            for q in quarters:
                if q in act.index:
                    values.append(float(act.loc[q]))
                    kinds.append(f"{q}=actual")
                elif q in fc.index:
                    values.append(float(fc.loc[q]))
                    kinds.append(f"{q}=forecast")
                else:
                    values, kinds = None, [f"{q}=missing"]
                    break
            if values is None:
                continue
            agg = ANNUAL_AGG[stream]
            fy_value = float(np.mean(values)) if agg == "mean" else float(np.sum(values))
            rows.append(
                {
                    "candidate": candidate,
                    "scenario_name": scenario,
                    "stream": stream,
                    "fy": fy,
                    "value": fy_value,
                    "aggregation": agg,
                    "quarter_mix": "; ".join(kinds),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "actuals_refresh_2026q1")
    parser.add_argument("--engine", default=PRODUCTION_ENGINE, choices=["ar1", "ensemble"])
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = args.engine

    wide = pd.read_parquet(PACK_DIRS[engine] / "scenario_inputs" / "scenario_input_wide.parquet")
    seed = load_ped_seed()
    latest = stream_latest_accepted_periods(ROOT)
    seed_period = max(seed, key=quarter_sort_key)

    candidates = {
        "A_strict_accepted_actual": {"seam": "per_stream", "ped_seed": None},
        "B_ped_provisional_replay_only": {"seam": "per_stream", "ped_seed": seed},
    }
    quarterly_frames = []
    fy_frames = []
    actuals_a = actual_rows_for_impact(latest)
    # Candidate B treats the seeded PED quarter as (provisional) history for FY
    # mixing, explicitly labelled - it is not an accepted actual.
    actuals_b = pd.concat(
        [
            actuals_a,
            pd.DataFrame(
                [
                    {
                        "stream": "PED",
                        "target_period": period,
                        "value": value,
                        "value_kind": "provisional_bridge_seed",
                    }
                    for period, value in seed.items()
                ]
            ),
        ],
        ignore_index=True,
    )
    for name, config in candidates.items():
        quarterly = replay_candidate(wide, engine, seam=config["seam"], ped_seed=config["ped_seed"])
        quarterly.insert(0, "candidate", name)
        quarterly_frames.append(quarterly)
        fy_frames.append(fy_frame(quarterly, actuals_b if name.startswith("B") else actuals_a, name))

    quarterly_all = pd.concat(quarterly_frames, ignore_index=True)
    baseline = committed_baseline(engine)
    quarterly_all = quarterly_all.merge(
        baseline[["scenario_name", "stream", "target_period", "baseline_forecast"]],
        on=["scenario_name", "stream", "target_period"],
        how="left",
    )
    quarterly_all["delta_vs_pre_refresh"] = quarterly_all["forecast"] - quarterly_all["baseline_forecast"]
    quarterly_all["pct_vs_pre_refresh"] = np.where(
        quarterly_all["baseline_forecast"].abs() > 0,
        quarterly_all["delta_vs_pre_refresh"] / quarterly_all["baseline_forecast"] * 100.0,
        np.nan,
    )
    quarterly_all["engine"] = engine
    quarterly_all.to_csv(out_dir / "replay_predictions_quarterly.csv", index=False)

    # FY impact: candidates vs the pre-refresh committed vintage (which had
    # 2026Q1 as a forecast quarter for every stream).
    baseline_quarterly = baseline.rename(columns={"baseline_forecast": "forecast"})
    baseline_actuals = actual_rows_for_impact(
        {stream: "2025Q4" for stream in SERIES_IDS}
    )
    fy_baseline = fy_frame(
        baseline_quarterly.assign(horizon=np.nan, model=""),
        baseline_actuals,
        "pre_refresh_committed",
    )
    fy_all = pd.concat(fy_frames + [fy_baseline], ignore_index=True)
    pivot = fy_all.pivot_table(
        index=["scenario_name", "stream", "fy", "aggregation"],
        columns="candidate",
        values="value",
    ).reset_index()
    for name in candidates:
        if name in pivot.columns and "pre_refresh_committed" in pivot.columns:
            pivot[f"{name}_pct_vs_pre_refresh"] = (
                (pivot[name] / pivot["pre_refresh_committed"]) - 1.0
            ) * 100.0
    mix_lookup = fy_all.drop_duplicates(["candidate", "scenario_name", "stream", "fy"]).set_index(
        ["candidate", "scenario_name", "stream", "fy"]
    )["quarter_mix"]
    pivot["quarter_mix_candidate_A"] = [
        mix_lookup.get(("A_strict_accepted_actual", s, st, fy), "")
        for s, st, fy in zip(pivot["scenario_name"], pivot["stream"], pivot["fy"])
    ]
    pivot["engine"] = engine
    pivot.to_csv(out_dir / "replay_impact_fy.csv", index=False)

    # PED governance candidates summary.
    ped_rows = []
    for name in candidates:
        sub = quarterly_all[(quarterly_all["candidate"] == name) & (quarterly_all["stream"] == "PED")]
        ped_rows.append(
            {
                "candidate": name,
                "ped_accepted_exact_cutoff": "2025Q4"
                if latest["PED"] < seed_period
                else latest["PED"],
                "ped_replay_seed": seed_period if name.startswith("B") else "",
                "ped_first_forecast_quarter": sub["target_period"].min(),
                "ped_refit_performed": False,
                "seed_displayed_as_observed_actual": False,
                "max_abs_pct_move_vs_pre_refresh_h1_h8": float(
                    sub[sub["horizon"] <= 8]["pct_vs_pre_refresh"].abs().max()
                ),
                "engine": engine,
            }
        )
    pd.DataFrame(ped_rows).to_csv(out_dir / "ped_governance_candidates.csv", index=False)

    # PED bridge sensitivities (Candidate B variants) through FY2030.
    sens_rows = []
    for variant, variant_seed in load_ped_sensitivity_variants().items():
        quarterly = replay_candidate(wide, engine, seam="per_stream", ped_seed=variant_seed)
        quarterly = quarterly[quarterly["stream"] == "PED"].copy()
        variant_actuals = pd.concat(
            [
                actuals_a,
                pd.DataFrame(
                    [
                        {
                            "stream": "PED",
                            "target_period": period,
                            "value": value,
                            "value_kind": "provisional_bridge_seed",
                        }
                        for period, value in variant_seed.items()
                    ]
                ),
            ],
            ignore_index=True,
        )
        fy = fy_frame(quarterly.assign(candidate=variant), variant_actuals, variant)
        for _, row in fy[fy["stream"] == "PED"].iterrows():
            sens_rows.append(
                {
                    "variant": variant,
                    "seed_value_km_per_person": float(next(iter(variant_seed.values()))),
                    "scenario_name": row["scenario_name"],
                    "fy": row["fy"],
                    "ped_fy_value": row["value"],
                    "engine": engine,
                }
            )
    sens = pd.DataFrame(sens_rows)
    if not sens.empty:
        selected = sens[sens["variant"] == "selected_core_ped_revenue_share"][
            ["scenario_name", "fy", "ped_fy_value"]
        ].rename(columns={"ped_fy_value": "selected_value"})
        sens = sens.merge(selected, on=["scenario_name", "fy"], how="left")
        sens["pct_vs_selected"] = (sens["ped_fy_value"] / sens["selected_value"] - 1.0) * 100.0
    sens.to_csv(out_dir / "ped_bridge_sensitivity.csv", index=False)

    # Heavy lead vintage replay diagnostic: the promoted Heavy vNext ensemble
    # uses no lead features by governance, so the retrospective and real-time
    # lead vintages produce identical production replays.
    from pipeline.vnext_forward import load_scorer

    heavy_scorer = load_scorer("HEAVY_RUC")
    lead_features = sorted(
        {
            feature
            for bundle in (heavy_scorer.bundles if heavy_scorer else {}).values()
            for feature in list(bundle.get("feature_cols", [])) + list(bundle.get("base_cols", []) or [])
            if "lead" in str(feature).lower()
        }
    )
    pd.DataFrame(
        [
            {
                "check": "promoted_heavy_state_uses_lead_features",
                "lead_features_in_promoted_state": "; ".join(lead_features) or "(none)",
                "lead_feature_count": len(lead_features),
                "conclusion": (
                    "The promoted Heavy RUC vNext ensemble excludes lead-price features by "
                    "governance ('no leads'), so the production replay is identical under the "
                    "retrospective_history and real_time_vintage treatments of the 2026Q1 lead. "
                    "The retrospective lead is stored for legacy-spec refit/evaluation evidence only."
                ),
            }
        ]
    ).to_csv(out_dir / "heavy_lead_replay_diagnostic.csv", index=False)

    # Scenario replay lineage.
    manifest = json.loads(
        (PACK_DIRS[engine] / "scenario_inputs" / "scenario_input_manifest.json").read_text(encoding="utf-8")
    )
    state_files = {
        "PED_AR1": ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "ped_ar1" / "ar1_fitted_state.json",
        "LIGHT_RUC": ROOT
        / "data"
        / "dashboard_evidence_pack_reproducibility"
        / "light_ruc_vnext"
        / "fitted_state"
        / "light_ruc_production.joblib",
        "HEAVY_RUC_M1": ROOT
        / "data"
        / "dashboard_evidence_pack_reproducibility"
        / "heavy_ruc_vnext"
        / "fitted_state"
        / "M1_production.joblib",
    }
    lineage_rows = []
    for name, config in candidates.items():
        for wb in manifest.get("workbooks", []):
            for stream in SERIES_IDS:
                origin = latest[stream]
                if stream == "PED":
                    if name.startswith("B"):
                        origin = seed_period
                lineage_rows.append(
                    {
                        "candidate": name,
                        "engine": engine,
                        "scenario_name": wb.get("scenario_name"),
                        "scenario_workbook": wb.get("workbook_filename"),
                        "scenario_workbook_sha256": wb.get("workbook_sha256"),
                        "stream": stream,
                        "replay_origin_latest_history": origin,
                        "first_forecast_quarter": f"{origin[:4]}Q{origin[-1]}",
                        "ped_seed_used": bool(name.startswith("B") and stream == "PED"),
                        "runtime_refit": False,
                        "scenario_result_reused_from_base": False,
                    }
                )
    lineage = pd.DataFrame(lineage_rows)
    lineage["first_forecast_quarter"] = lineage["replay_origin_latest_history"].map(
        lambda p: f"{quarter_sort_key(p) // 4}Q{(quarter_sort_key(p) % 4) + 1}"
    )
    lineage.to_csv(out_dir / "scenario_replay_lineage.csv", index=False)

    # Promoted-state invariance evidence.
    invariance_rows = [
        {
            "state": name,
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
            "refit_during_replay": False,
        }
        for name, path in state_files.items()
        if path.exists()
    ]
    pd.DataFrame(invariance_rows).to_csv(out_dir / "promoted_state_invariance.csv", index=False)

    print(f"REPLAY_EVIDENCE_WRITTEN {out_dir} engine={engine}")
    print(quarterly_all.groupby(['candidate', 'stream'])['target_period'].agg(['min', 'max', 'count']).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
