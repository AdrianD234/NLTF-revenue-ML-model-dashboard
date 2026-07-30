"""Shadow (challenger) refits of the promoted Light and Heavy RUC recipes.

Refits the EXACT promoted recipes - unchanged features, hyperparameters and
windows - on the enlarged history that now includes the accepted 2026Q1
actuals, and compares the challengers against the promoted states. This is
analysis-only evidence: nothing is promoted, no production state file is
touched, and PED is explicitly excluded (its 2026Q1 value is a provisional
bridge that must never enter an estimation sample).

Outputs (under --output-dir):
    light_heavy_refit_comparison.csv   parameter/window/in-sample/forecast deltas
    refit_h1_backtest_evidence.csv     honest new out-of-sample evidence: the
                                       PROMOTED states' 2026Q1 (h1) predictions
                                       against the now-known actuals
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

from model_dashboard import forecast_runner as fr  # noqa: E402

SCENARIO_INPUTS = ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "scenario_inputs" / "scenario_input_wide.parquet"
HEAVY_STATE_DIR = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc_vnext"
ACTUALS = {
    # Accepted exact 2026Q1 Core Data actuals (canonical history).
    "LIGHT_RUC": 3196014020.0,
    "HEAVY_RUC": 1039372457.0,
}
IMPACT_FYS = range(2026, 2031)


def june_year(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[-1])
    return year if quarter in (1, 2) else year + 1


def _light_challenger() -> fr.LightRucPromotedState:
    """Refit the exact promoted Light recipe with the accepted 2026Q1 actual."""
    from sklearn.ensemble import GradientBoostingRegressor

    history = pd.read_parquet(ROOT / fr.MODEL_INPUT_HISTORY_DIR / fr.MODEL_INPUT_HISTORY_FILES["LIGHT_RUC"])
    latest = fr.stream_latest_accepted_periods(ROOT)["LIGHT_RUC"]
    frame = fr._light_ruc_feature_frame(history, pd.DataFrame(), latest)
    rows = frame[frame["sample_scope"].eq("history")].replace([np.inf, -np.inf], np.nan)
    rows = rows.dropna(subset=["target", *fr.LIGHT_RUC_RESIDUAL_FEATURES])
    rows = rows[pd.to_numeric(rows["target"], errors="coerce").gt(0)]
    train = rows.sort_values("period_key").tail(fr.LIGHT_RUC_WINDOW)

    y = np.log(pd.to_numeric(train["target"], errors="coerce").to_numpy(dtype=float))
    base_x = train[fr.LIGHT_RUC_BASE_FEATURES].to_numpy(dtype=float)
    beta = fr._ols_fit(base_x, y)
    residual_model = GradientBoostingRegressor(**fr.LIGHT_RUC_STATE_HYPERPARAMETERS)
    residual_model.fit(
        train[fr.LIGHT_RUC_RESIDUAL_FEATURES].to_numpy(dtype=float),
        y - fr._ols_predict(base_x, beta),
    )
    fit_log = fr._ols_predict(base_x, beta) + residual_model.predict(
        train[fr.LIGHT_RUC_RESIDUAL_FEATURES].to_numpy(dtype=float)
    )
    state = fr.LightRucPromotedState(
        ols_beta=beta,
        base_features=tuple(fr.LIGHT_RUC_BASE_FEATURES),
        residual_model=residual_model,
        residual_features=tuple(fr.LIGHT_RUC_RESIDUAL_FEATURES),
        window=fr.LIGHT_RUC_WINDOW,
        random_state=42,
        recipe="shadow refit with accepted 2026Q1 actual (analysis only, NOT promoted)",
        sha256="shadow_refit_not_promoted",
        train_window_start=str(train.iloc[0]["period"]),
        train_window_end=str(train.iloc[-1]["period"]),
        train_rows=len(train),
        max_training_fit_replay_delta=float("nan"),
    )
    in_sample = {
        "train_window_start": state.train_window_start,
        "train_window_end": state.train_window_end,
        "train_rows": state.train_rows,
        "in_sample_rmse_log": float(np.sqrt(np.mean((fit_log - y) ** 2))),
        "in_sample_mape_pct": float(np.mean(np.abs(np.exp(fit_log) / np.exp(y) - 1.0)) * 100.0),
    }
    return state, in_sample


def _light_promoted_in_sample(promoted: fr.LightRucPromotedState) -> dict[str, Any]:
    history = pd.read_parquet(ROOT / fr.MODEL_INPUT_HISTORY_DIR / fr.MODEL_INPUT_HISTORY_FILES["LIGHT_RUC"])
    frame = fr._light_ruc_feature_frame(history, pd.DataFrame(), promoted.train_window_end)
    rows = frame[frame["sample_scope"].eq("history")].replace([np.inf, -np.inf], np.nan)
    rows = rows.dropna(subset=["target", *fr.LIGHT_RUC_RESIDUAL_FEATURES])
    rows = rows[pd.to_numeric(rows["target"], errors="coerce").gt(0)]
    rows = rows[rows["period"].astype(str) <= promoted.train_window_end]
    train = rows.sort_values("period_key").tail(promoted.window)
    y = np.log(pd.to_numeric(train["target"], errors="coerce").to_numpy(dtype=float))
    base_x = train[list(promoted.base_features)].to_numpy(dtype=float)
    fit_log = fr._ols_predict(base_x, promoted.ols_beta) + promoted.residual_model.predict(
        train[list(promoted.residual_features)].to_numpy(dtype=float)
    )
    return {
        "train_window_start": promoted.train_window_start,
        "train_window_end": promoted.train_window_end,
        "train_rows": promoted.train_rows,
        "in_sample_rmse_log": float(np.sqrt(np.mean((fit_log - y) ** 2))),
        "in_sample_mape_pct": float(np.mean(np.abs(np.exp(fit_log) / np.exp(y) - 1.0)) * 100.0),
    }


def _heavy_states() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load promoted Heavy member bundles and refit challengers at 2026Q1."""
    import joblib

    from pipeline.vnext_core import fit_at_origin, load_stream_data
    from pipeline.vnext_run import _spec_by_name

    manifest = json.loads((HEAVY_STATE_DIR / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    sd = load_stream_data(ROOT, "HEAVY_RUC")
    rows: list[dict[str, Any]] = []
    challenger_bundles: dict[str, Any] = {}
    for label, entry in manifest["production_states"].items():
        member_model = entry["component_model"]
        spec = _spec_by_name("HEAVY_RUC", member_model)
        promoted = joblib.load(HEAVY_STATE_DIR / entry["file"])
        challenger = fit_at_origin(sd, spec, sd.latest_actual)
        assert challenger is not None, f"{member_model}: challenger fit failed"
        challenger_bundles[label] = {
            "model": challenger.model,
            "feature_cols": challenger.feature_cols,
            "base_cols": challenger.base_cols,
            "all_na_cols": challenger.all_na_cols,
            "base_all_na_cols": challenger.base_all_na_cols,
            "spec": promoted["spec"],
        }

        def _params(model: Any) -> dict[str, np.ndarray]:
            if isinstance(model, dict) and model.get("kind") == "residual":
                return {
                    "base_coef": np.append(model["base"].coef_, model["base"].intercept_),
                    "resid_importances": np.asarray(model["resid"].feature_importances_, dtype=float),
                }
            if hasattr(model, "coef_"):
                return {"coef": np.append(np.ravel(model.coef_), getattr(model, "intercept_", 0.0))}
            if hasattr(model, "feature_importances_"):
                return {"importances": np.asarray(model.feature_importances_, dtype=float)}
            return {}

        old_params = _params(promoted["model"])
        new_params = _params(challenger.model)
        param_deltas = {}
        for key in old_params:
            if key in new_params and old_params[key].shape == new_params[key].shape:
                param_deltas[f"max_abs_delta_{key}"] = float(np.max(np.abs(old_params[key] - new_params[key])))
            else:
                param_deltas[f"max_abs_delta_{key}"] = float("nan")

        fit_log = np.array(
            [
                _predict_bundle(challenger_bundles[label], challenger.X_train.iloc[[i]],
                                None if challenger.X_train_base is None else challenger.X_train_base.iloc[[i]])
                for i in range(len(challenger.X_train))
            ]
        )
        y = challenger.y_train.to_numpy(dtype=float)
        rows.append(
            {
                "stream": "HEAVY_RUC",
                "component": label,
                "component_model": member_model,
                "promoted_train_window": f"{entry['train_window_start']}..{entry['train_window_end']}",
                "challenger_train_window": (
                    f"{challenger.X_train.index.min()}..{challenger.X_train.index.max()}"
                ),
                "promoted_train_rows": entry["train_rows"],
                "challenger_train_rows": int(len(challenger.X_train)),
                "challenger_in_sample_rmse_log": float(np.sqrt(np.mean((fit_log - y) ** 2))),
                "challenger_in_sample_mape_pct": float(
                    np.mean(np.abs(np.exp(fit_log) / np.exp(y) - 1.0)) * 100.0
                ),
                **param_deltas,
                "promoted_state_sha256": entry["sha256"],
                "challenger_state_sha256": "shadow_refit_not_promoted",
            }
        )
    return challenger_bundles, rows


def _predict_bundle(bundle: dict[str, Any], x_row: pd.DataFrame, xb_row: pd.DataFrame | None) -> float:
    model = bundle["model"]
    x = x_row[bundle["feature_cols"]].astype(float).fillna(0.0)
    if isinstance(model, dict) and model.get("kind") == "residual":
        xb = xb_row[bundle["base_cols"]].astype(float).fillna(0.0)
        return float(model["base"].predict(xb.to_numpy(float))[0] + model["resid"].predict(x.to_numpy(float))[0])
    return float(model.predict(x.to_numpy(float))[0])


def _replay_with_states(
    light_state: fr.LightRucPromotedState | None,
    heavy_bundles: dict[str, Any] | None,
) -> pd.DataFrame:
    """Per-stream seam replay, optionally with injected challenger states."""
    import pipeline.vnext_forward as vf

    wide = pd.read_parquet(SCENARIO_INPUTS)
    original_light = fr.load_light_ruc_promoted_state
    original_load_scorer = vf.load_scorer
    if light_state is not None:
        fr.load_light_ruc_promoted_state = lambda *args, **kwargs: light_state  # noqa: ARG005
    if heavy_bundles is not None:
        def patched_load_scorer(stream: str):
            scorer = original_load_scorer(stream)
            if stream == "HEAVY_RUC" and scorer is not None:
                return vf.VNextScorer(
                    stream=scorer.stream,
                    manifest=scorer.manifest,
                    parity=scorer.parity,
                    bundles=heavy_bundles,
                    runtime_state_gate_delta=0.0,
                )
            return scorer

        vf.load_scorer = patched_load_scorer
    try:
        result = fr.replay_forecast_from_scenario_inputs(
            wide, repo_root=ROOT, engine="ar1", seam="per_stream"
        )
    finally:
        fr.load_light_ruc_promoted_state = original_light
        vf.load_scorer = original_load_scorer
    future = result.future_forecasts
    return future[future["forecast_available"].astype(bool)][
        ["scenario_name", "stream", "target_period", "horizon", "forecast"]
    ].copy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "actuals_refresh_2026q1")
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Light ---
    promoted_light = fr.load_light_ruc_promoted_state(ROOT)
    challenger_light, light_challenger_fit = _light_challenger()
    promoted_light_fit = _light_promoted_in_sample(promoted_light)
    light_row = {
        "stream": "LIGHT_RUC",
        "component": "LIGHT",
        "component_model": "dynamic_RESID_GBR_n150_d1_lr0.05_w36",
        "promoted_train_window": f"{promoted_light.train_window_start}..{promoted_light.train_window_end}",
        "challenger_train_window": f"{light_challenger_fit['train_window_start']}..{light_challenger_fit['train_window_end']}",
        "promoted_train_rows": promoted_light.train_rows,
        "challenger_train_rows": light_challenger_fit["train_rows"],
        "max_abs_delta_base_coef": float(
            np.max(np.abs(np.asarray(promoted_light.ols_beta) - np.asarray(challenger_light.ols_beta)))
        ),
        "max_abs_delta_resid_importances": float(
            np.max(
                np.abs(
                    np.asarray(promoted_light.residual_model.feature_importances_)
                    - np.asarray(challenger_light.residual_model.feature_importances_)
                )
            )
        ),
        "promoted_in_sample_rmse_log": promoted_light_fit["in_sample_rmse_log"],
        "promoted_in_sample_mape_pct": promoted_light_fit["in_sample_mape_pct"],
        "challenger_in_sample_rmse_log": light_challenger_fit["in_sample_rmse_log"],
        "challenger_in_sample_mape_pct": light_challenger_fit["in_sample_mape_pct"],
        "promoted_state_sha256": promoted_light.sha256,
        "challenger_state_sha256": "shadow_refit_not_promoted",
    }

    # --- Heavy ---
    heavy_bundles, heavy_rows = _heavy_states()

    # --- Forecast comparison: promoted vs challengers (FY2026-FY2030) ---
    promoted_forecasts = _replay_with_states(None, None)
    challenger_forecasts = _replay_with_states(challenger_light, heavy_bundles)
    merged = promoted_forecasts.merge(
        challenger_forecasts,
        on=["scenario_name", "stream", "target_period", "horizon"],
        suffixes=("_promoted", "_challenger"),
    )
    merged["june_year"] = merged["target_period"].map(june_year)
    merged["pct_delta"] = (merged["forecast_challenger"] / merged["forecast_promoted"] - 1.0) * 100.0
    fy = (
        merged[merged["june_year"].isin(IMPACT_FYS) & merged["stream"].isin(["LIGHT_RUC", "HEAVY_RUC"])]
        .groupby(["scenario_name", "stream", "june_year"])
        .agg(
            promoted=("forecast_promoted", "sum"),
            challenger=("forecast_challenger", "sum"),
        )
        .reset_index()
    )
    fy["pct_delta"] = (fy["challenger"] / fy["promoted"] - 1.0) * 100.0

    comparison_rows = [light_row] + heavy_rows
    for row in comparison_rows:
        stream = row["stream"]
        sub = fy[fy["stream"] == stream]
        row["fy2026_2030_max_abs_pct_forecast_delta"] = float(sub["pct_delta"].abs().max()) if not sub.empty else np.nan
        row["analysis_only"] = True
        row["promoted_state_modified"] = False
        row["recipe_or_hyperparameters_changed"] = False
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(out_dir / "light_heavy_refit_comparison.csv", index=False)
    fy.assign(analysis="challenger_vs_promoted_fy_activity").to_csv(
        out_dir / "light_heavy_refit_fy_forecast_deltas.csv", index=False
    )

    # --- Honest h1 evidence: promoted states' 2026Q1 predictions vs actuals ---
    committed = pd.read_csv(
        ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "revenue_chart_rows.csv", low_memory=False
    )
    h1_rows = []
    for stream, series in [("LIGHT_RUC", "light_ruc_net_km"), ("HEAVY_RUC", "heavy_ruc_net_km")]:
        quarterly_forecast = committed[
            committed["time_grain"].astype(str).eq("quarterly")
            & committed["row_type"].astype(str).eq("future_forecast")
            & committed["series_id"].astype(str).eq(series)
        ]
        first_period = min(quarterly_forecast["period"].astype(str), key=fr.quarter_sort_key)
        sub = quarterly_forecast[quarterly_forecast["period"].astype(str).eq(first_period)]
        actual = ACTUALS[stream]
        for _, row in sub.iterrows():
            predicted = float(row["value"])
            h1_rows.append(
                {
                    "stream": stream,
                    "scenario_name": row["scenario_name"],
                    "target_period": row["period"],
                    "promoted_h1_prediction": predicted,
                    "accepted_actual": actual,
                    "ape_pct": abs(predicted / actual - 1.0) * 100.0,
                    "note": (
                        "The only honest new out-of-sample evidence from one extra quarter: the "
                        "promoted state's h1 forecast of 2026Q1 (made from the 2025Q4 origin) "
                        "against the now-accepted actual. The refitted challenger trains ON "
                        "2026Q1, so it has no comparable out-of-sample observation."
                    ),
                }
            )
    pd.DataFrame(h1_rows).to_csv(out_dir / "refit_h1_backtest_evidence.csv", index=False)

    print("SHADOW_REFITS_WRITTEN")
    print(comparison[[
        "stream", "component", "promoted_train_window", "challenger_train_window",
        "fy2026_2030_max_abs_pct_forecast_delta",
    ]].to_string(index=False))
    print()
    print(pd.DataFrame(h1_rows)[["stream", "scenario_name", "promoted_h1_prediction", "accepted_actual", "ape_pct"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
