"""Rolling-origin evaluation of the fixed finalists beyond the validated H1-H12.

The governed evidence pack stops at H12, but the Revenue Outlook is read to
FY2050. FY2029 straddles H12 and FY2030 is entirely H13-H18, so the horizons
that carry the headline MBU26 gap have never been scored. This script extends
the same rolling-origin design to H20 and reports sample size at every horizon
so the degradation can be read rather than assumed.

Design notes:

* Fixed finalists only. Component specs and ensemble weights are read from the
  committed ``fitted_model_manifest.json`` files; no model search is run.
* Actual-driver evaluation. Exogenous inputs at each target quarter are the
  observed values, so what is measured is model degradation with horizon, not
  driver-forecast error. A forecast-vintage evaluation would need archived
  driver vintages, which this repository does not hold - see the report.
* PED and Heavy RUC replay through ``pipeline.vnext_core.backtest``, which
  carries recursive predicted target lags. Light RUC replays its fixed
  OLS-plus-residual-GBR recipe, which has no target lags: its horizon
  behaviour comes only from training-window age and driver path.

Usage::

    .\\.venv\\Scripts\\python.exe scripts\\evaluate_long_horizon_rolling_origin.py \
        --max-horizon 20 --output-dir outputs\\long_horizon_validation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.forecast_runner import (  # noqa: E402
    LIGHT_RUC_BASE_FEATURES,
    LIGHT_RUC_RESIDUAL_FEATURES,
    LIGHT_RUC_WINDOW,
    MODEL_INPUT_HISTORY_DIR,
    MODEL_INPUT_HISTORY_FILES,
    _light_ruc_feature_frame,
    _ols_fit,
    _ols_predict,
    quarter_sort_key,
)
import pipeline.vnext_core as vc  # noqa: E402
from pipeline.vnext_run import ensemble_predictions  # noqa: E402


BACKTEST_SUPPORTED_MAX_HORIZON = 12
VNEXT_STREAMS = ("PED", "HEAVY_RUC")
STATE_DIRS = {
    "PED": "ped_vnext",
    "HEAVY_RUC": "heavy_ruc_vnext",
    "LIGHT_RUC": "light_ruc_vnext",
}
STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
}


def _finalist_manifest(stream: str) -> dict[str, Any]:
    path = (
        REPO_ROOT
        / "data"
        / "dashboard_evidence_pack_reproducibility"
        / STATE_DIRS[stream]
        / "fitted_model_manifest.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _member_specs(stream: str) -> tuple[list[vc.CandidateSpec], np.ndarray, str]:
    manifest = _finalist_manifest(stream)
    members = manifest.get("members") or []
    if not members:
        raise ValueError(f"{stream} finalist manifest carries no members.")
    specs: list[vc.CandidateSpec] = []
    weights: list[float] = []
    for member in members:
        specs.append(
            vc.CandidateSpec(
                stream=stream,
                name=str(member["name"]),
                model_kind=str(member["model_kind"]),
                params_json=str(member["params_json"]),
                window=(
                    int(member["window"]) if member.get("window") is not None else None
                ),
                feature_set=str(member["feature_set"]),
                include_target_lags=bool(member["include_target_lags"]),
                family_tag=str(member.get("family_tag") or "finalist_member"),
                base_feature_set=str(member.get("base_feature_set") or "schiff"),
            )
        )
        weights.append(float(member["component_weight"]))
    weight_array = np.asarray(weights, dtype=float)
    total = float(weight_array.sum())
    if not np.isclose(total, 1.0, rtol=0.0, atol=1e-6):
        raise ValueError(
            f"{stream} finalist weights sum to {total:.9f}, not 1; refusing to rescale silently."
        )
    return specs, weight_array, str(manifest["finalist_model"])


def _vnext_rolling_origin(stream: str, max_horizon: int) -> pd.DataFrame:
    specs, weights, finalist = _member_specs(stream)
    stream_data = vc.load_stream_data(REPO_ROOT, stream)
    original = vc.MAX_HORIZON
    vc.MAX_HORIZON = int(max_horizon)
    try:
        component_predictions = [
            vc.backtest(stream_data, spec).predictions for spec in specs
        ]
    finally:
        vc.MAX_HORIZON = original
    if len(component_predictions) == 1:
        out = component_predictions[0][
            ["stream", "model", "origin", "target_period", "horizon", "actual", "pred"]
        ].copy()
        out["model"] = finalist
        return out
    return ensemble_predictions(component_predictions, weights, finalist, stream)


def _light_ruc_rolling_origin(max_horizon: int) -> pd.DataFrame:
    """Replay the committed Light RUC fixed recipe at every rolling origin."""

    history = pd.read_parquet(
        REPO_ROOT / MODEL_INPUT_HISTORY_DIR / MODEL_INPUT_HISTORY_FILES["LIGHT_RUC"]
    )
    periods = [str(value) for value in history["period"].astype(str)]
    latest = max(periods, key=quarter_sort_key)
    frame = _light_ruc_feature_frame(history, pd.DataFrame(), latest)
    frame = frame[frame["sample_scope"].eq("history")].copy()
    required = ["target", *LIGHT_RUC_RESIDUAL_FEATURES]
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
    frame = frame[pd.to_numeric(frame["target"], errors="coerce").gt(0)]
    frame = frame.sort_values("period_key").reset_index(drop=True)

    from sklearn.ensemble import GradientBoostingRegressor

    records: list[dict[str, Any]] = []
    manifest = _finalist_manifest("LIGHT_RUC")
    finalist = str(manifest["finalist_model"])
    for position in range(LIGHT_RUC_WINDOW - 1, len(frame)):
        train = frame.iloc[position - LIGHT_RUC_WINDOW + 1 : position + 1]
        if len(train) < LIGHT_RUC_WINDOW:
            continue
        origin = str(train.iloc[-1]["period"])
        targets = frame.iloc[position + 1 : position + 1 + int(max_horizon)]
        if targets.empty:
            continue
        y = np.log(pd.to_numeric(train["target"], errors="coerce").to_numpy(dtype=float))
        base_x = train[LIGHT_RUC_BASE_FEATURES].to_numpy(dtype=float)
        beta = _ols_fit(base_x, y)
        residual_target = y - _ols_predict(base_x, beta)
        residual_model = GradientBoostingRegressor(
            n_estimators=150,
            max_depth=1,
            learning_rate=0.05,
            subsample=0.85,
            random_state=42,
            loss="squared_error",
        )
        residual_model.fit(
            train[LIGHT_RUC_RESIDUAL_FEATURES].to_numpy(dtype=float), residual_target
        )
        base_log = _ols_predict(
            targets[LIGHT_RUC_BASE_FEATURES].to_numpy(dtype=float), beta
        )
        residual_log = residual_model.predict(
            targets[LIGHT_RUC_RESIDUAL_FEATURES].to_numpy(dtype=float)
        )
        predictions = np.exp(base_log + residual_log)
        for offset, (_, row) in enumerate(targets.iterrows(), start=1):
            records.append(
                {
                    "stream": "LIGHT_RUC",
                    "model": finalist,
                    "origin": origin,
                    "target_period": str(row["period"]),
                    "horizon": offset,
                    "actual": float(row["target"]),
                    "pred": float(predictions[offset - 1]),
                }
            )
    return pd.DataFrame(records)


def _horizon_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (stream, horizon), group in predictions.groupby(
        ["stream", "horizon"], dropna=False
    ):
        actual = pd.to_numeric(group["actual"], errors="coerce").to_numpy(dtype=float)
        pred = pd.to_numeric(group["pred"], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(actual) & np.isfinite(pred) & (actual > 0)
        actual, pred = actual[mask], pred[mask]
        if actual.size == 0:
            continue
        error = pred - actual
        rows.append(
            {
                "stream": stream,
                "stream_label": STREAM_LABELS.get(str(stream), str(stream)),
                "horizon": int(horizon),
                "horizon_scope": (
                    "H1-H12"
                    if int(horizon) <= BACKTEST_SUPPORTED_MAX_HORIZON
                    else "H13+"
                ),
                "n_observations": int(actual.size),
                "n_origins": int(group.loc[mask, "origin"].nunique()),
                "mape_pct": float(np.mean(np.abs(error / actual)) * 100.0),
                "wape_pct": float(np.sum(np.abs(error)) / np.sum(actual) * 100.0),
                "rmse": float(np.sqrt(np.mean(error**2))),
                "signed_mean_error_pct": float(np.mean(error / actual) * 100.0),
                "signed_mean_error": float(np.mean(error)),
            }
        )
    return pd.DataFrame(rows).sort_values(["stream", "horizon"]).reset_index(drop=True)


def _june_year(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    return year + 1 if quarter >= 3 else year


def _annual_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    """June-year signed bias and cumulative error by first-horizon bucket.

    A June year is only scored when all four of its quarters were produced from
    the same origin, so a partial year cannot masquerade as an annual result.
    """

    out = predictions.copy()
    out["june_year"] = out["target_period"].map(_june_year)
    rows: list[dict[str, Any]] = []
    for (stream, origin, june_year), group in out.groupby(
        ["stream", "origin", "june_year"], dropna=False
    ):
        if len(group) != 4:
            continue
        actual = pd.to_numeric(group["actual"], errors="coerce").sum()
        pred = pd.to_numeric(group["pred"], errors="coerce").sum()
        if not np.isfinite(actual) or actual <= 0:
            continue
        rows.append(
            {
                "stream": stream,
                "origin": origin,
                "june_year": int(june_year),
                "first_horizon": int(group["horizon"].min()),
                "last_horizon": int(group["horizon"].max()),
                "actual": float(actual),
                "pred": float(pred),
                "signed_error": float(pred - actual),
                "signed_error_pct": float((pred - actual) / actual * 100.0),
                "abs_error_pct": float(abs(pred - actual) / actual * 100.0),
            }
        )
    annual = pd.DataFrame(rows)
    if annual.empty:
        return annual
    annual["horizon_scope"] = np.where(
        annual["last_horizon"] <= BACKTEST_SUPPORTED_MAX_HORIZON, "H1-H12", "H13+"
    )
    return annual.sort_values(["stream", "origin", "june_year"]).reset_index(drop=True)


def _annual_summary(annual: pd.DataFrame) -> pd.DataFrame:
    if annual.empty:
        return annual
    rows: list[dict[str, Any]] = []
    for (stream, scope), group in annual.groupby(["stream", "horizon_scope"], dropna=False):
        rows.append(
            {
                "stream": stream,
                "stream_label": STREAM_LABELS.get(str(stream), str(stream)),
                "horizon_scope": scope,
                "n_june_years": int(len(group)),
                "annual_mape_pct": float(group["abs_error_pct"].mean()),
                "annual_signed_bias_pct": float(group["signed_error_pct"].mean()),
                "cumulative_signed_error_units": float(group["signed_error"].sum()),
                "cumulative_actual_units": float(group["actual"].sum()),
                "cumulative_signed_error_pct": float(
                    group["signed_error"].sum() / group["actual"].sum() * 100.0
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["stream", "horizon_scope"]).reset_index(drop=True)


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a table without requiring the optional ``tabulate`` dependency."""

    if frame is None or frame.empty:
        return "_No rows._"
    formatted = frame.copy()
    for column in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.3f}")
        else:
            formatted[column] = formatted[column].astype(str)
    header = "| " + " | ".join(str(column) for column in formatted.columns) + " |"
    divider = "|" + "|".join("---" for _ in formatted.columns) + "|"
    body = [
        "| " + " | ".join(row) + " |"
        for row in formatted.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *body])


def _report(
    metrics: pd.DataFrame,
    annual_summary: pd.DataFrame,
    max_horizon: int,
) -> str:
    lines = [
        "# Long-horizon rolling-origin evaluation",
        "",
        f"Fixed finalists scored to H{max_horizon} on the committed input history.",
        "Actual-driver evaluation: exogenous inputs at each target quarter are the",
        "observed values, so this measures model degradation with horizon, not",
        "driver-forecast error. Sample size falls with horizon because each extra",
        "horizon costs one origin at the end of the sample - read `n_observations`",
        "before drawing conclusions from the tail.",
        "",
        "## Quarterly metrics by horizon",
        "",
        _markdown_table(metrics),
        "",
        "## June-year metrics by horizon scope",
        "",
        "Only June years whose four quarters all come from one origin are scored.",
        "",
        (
            _markdown_table(annual_summary)
            if not annual_summary.empty
            else "_No complete June years available._"
        ),
        "",
        "## Reading guidance",
        "",
        "* H1-H12 reproduces the governed evidence grid's supported range.",
        "* H13+ is the zone the Revenue Outlook relies on for FY2029 onward and",
        "  which the committed evidence pack does not score.",
        "* A forecast-vintage evaluation is not possible from this repository:",
        "  archived driver vintages are not held, so real forward error will be",
        "  at least this large once driver-forecast error is added.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-horizon", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "long_horizon_validation",
    )
    parser.add_argument("--streams", nargs="*", default=["PED", "LIGHT_RUC", "HEAVY_RUC"])
    args = parser.parse_args(argv)

    if args.max_horizon <= BACKTEST_SUPPORTED_MAX_HORIZON:
        raise SystemExit(
            f"--max-horizon must exceed the validated H{BACKTEST_SUPPORTED_MAX_HORIZON}."
        )

    frames: list[pd.DataFrame] = []
    for stream in args.streams:
        print(f"[rolling-origin] {stream} to H{args.max_horizon} ...", flush=True)
        if stream in VNEXT_STREAMS:
            frames.append(_vnext_rolling_origin(stream, args.max_horizon))
        elif stream == "LIGHT_RUC":
            frames.append(_light_ruc_rolling_origin(args.max_horizon))
        else:
            raise SystemExit(f"Unknown stream {stream!r}.")

    predictions = pd.concat(frames, ignore_index=True, sort=False)
    metrics = _horizon_metrics(predictions)
    annual = _annual_metrics(predictions)
    annual_summary = _annual_summary(annual)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_dir / "long_horizon_predictions.csv", index=False)
    metrics.to_csv(output_dir / "long_horizon_metrics_by_horizon.csv", index=False)
    annual.to_csv(output_dir / "long_horizon_june_year_errors.csv", index=False)
    annual_summary.to_csv(output_dir / "long_horizon_june_year_summary.csv", index=False)
    (output_dir / "long_horizon_report.md").write_text(
        _report(metrics, annual_summary, args.max_horizon), encoding="utf-8"
    )

    print()
    print(metrics.to_string(index=False))
    print()
    if not annual_summary.empty:
        print(annual_summary.to_string(index=False))
    print()
    print(f"Written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
