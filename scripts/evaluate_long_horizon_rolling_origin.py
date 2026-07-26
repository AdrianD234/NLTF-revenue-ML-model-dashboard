"""Rolling-origin evaluation of the fixed finalists beyond the validated H1-H12.

The governed evidence pack stops at H12, but the Revenue Outlook is read to
FY2050. FY2029 straddles H12 and FY2030 sits entirely in H15-H18, so the
horizons that carry the headline MBU26 gap have never been scored. This script
extends the same rolling-origin design to H20.

What this experiment is, precisely
----------------------------------

* **Fixed finalists only.** Component specs and ensemble weights are read from
  the committed ``fitted_model_manifest.json`` files. No model search is run.
* **Actual-driver.** Exogenous inputs at each target quarter are the observed
  values. This isolates model degradation with horizon from driver-forecast
  error, and therefore *understates* real forward error. A forecast-vintage
  comparison would need archived driver vintages, which this repository does
  not hold.
* **Origin-correct refitting.** Every origin refits using only rows at or
  before that origin. PED and Heavy RUC replay through
  ``pipeline.vnext_core.backtest``, which carries recursive *predicted* target
  lags - realized future target values never enter a lagged dependent
  variable. Light RUC replays its committed OLS-plus-residual-GBR recipe,
  which has no target lags at all, so its horizon behaviour comes only from
  training-window age and the driver path.

Signed error is defined throughout as::

    signed_error_pct = (forecast - actual) / actual * 100

so a positive value is overprediction.

Two comparisons are reported, because they answer different questions:

* ``all_available`` uses every origin that has an observation at that horizon.
  Sample size falls with horizon, so the H1 and H20 rows describe different
  origin sets and mix a horizon effect with a composition effect.
* ``balanced_h20`` restricts to origins that have observations at *every*
  horizon 1..max, so H1 and H20 are computed from identical origins. If
  degradation survives here it is a horizon effect.

A 2020-2021 target exclusion is also reported, following the original
methodology's exclusion of those outcomes from forecast-accuracy tests while
retaining them in training data.

Usage::

    .\\.venv\\Scripts\\python.exe scripts\\evaluate_long_horizon_rolling_origin.py \
        --max-horizon 20 --output-dir artifacts\\long_horizon_validation
"""

from __future__ import annotations

import argparse
import hashlib
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
    FORECAST_RUNNER_VERSION,
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


SCRIPT_VERSION = "long-horizon-rolling-origin-v2"
BACKTEST_SUPPORTED_MAX_HORIZON = 12
EXTENDED_EVIDENCE_MAX_HORIZON = 20
SIGNED_ERROR_DEFINITION = "(forecast - actual) / actual * 100; positive = overprediction"
EXCLUDED_TARGET_YEARS = (2020, 2021)
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
# Indicative revenue-equivalent conversion. A signed percentage error in
# activity is applied to the governed FY2025 revenue for the stream it drives,
# i.e. unit pass-through from activity to revenue at fixed rates and mix. It is
# a materiality scale, NOT a revenue forecast error.
REVENUE_REFERENCE_FY = 2025
REVENUE_REFERENCE_SERIES = {
    "PED": "net_fed_revenue",
    "LIGHT_RUC": "light_ruc_net_revenue",
    "HEAVY_RUC": "heavy_ruc_net_revenue",
}
REVENUE_EQUIVALENT_BASIS = (
    "signed percentage activity error applied to governed FY"
    f"{REVENUE_REFERENCE_FY} revenue for the stream, assuming unit pass-through "
    "at fixed rates and class mix; indicative materiality scale only"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finalist_manifest_path(stream: str) -> Path:
    return (
        REPO_ROOT
        / "data"
        / "dashboard_evidence_pack_reproducibility"
        / STATE_DIRS[stream]
        / "fitted_model_manifest.json"
    )


def _finalist_manifest(stream: str) -> dict[str, Any]:
    return json.loads(_finalist_manifest_path(stream).read_text(encoding="utf-8"))


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
    finalist = str(_finalist_manifest("LIGHT_RUC")["finalist_model"])
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


def _assert_no_future_target_leakage(predictions: pd.DataFrame) -> None:
    """Every scored target must lie strictly after the origin it came from."""

    origin_key = predictions["origin"].astype(str).map(quarter_sort_key)
    target_key = predictions["target_period"].astype(str).map(quarter_sort_key)
    offset = target_key - origin_key
    if not offset.gt(0).all():
        raise ValueError(
            "Rolling-origin output contains a target at or before its origin."
        )
    if not offset.eq(pd.to_numeric(predictions["horizon"], errors="coerce")).all():
        raise ValueError(
            "Horizon does not equal target-minus-origin for every row; the "
            "rolling-origin indexing cannot be trusted."
        )


def _reference_revenue() -> dict[str, float]:
    path = REPO_ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.parquet"
    rows = pd.read_parquet(path)
    rows = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(REVENUE_REFERENCE_FY)
        & rows["scenario_name"].astype(str).eq("current_basecase")
    ]
    out: dict[str, float] = {}
    for stream, series_id in REVENUE_REFERENCE_SERIES.items():
        selected = rows[rows["series_id"].astype(str).eq(series_id)]
        values = pd.to_numeric(selected["value"], errors="coerce").dropna().unique()
        if len(values) != 1:
            raise ValueError(
                f"Reference revenue for {stream} ({series_id}) is not a single "
                f"FY{REVENUE_REFERENCE_FY} value: found {list(values)}."
            )
        out[stream] = float(values[0])
    return out


def _balanced_origins(predictions: pd.DataFrame, max_horizon: int) -> pd.DataFrame:
    """Origins with an observation at every horizon 1..max_horizon."""

    counts = (
        predictions.groupby(["stream", "origin"])["horizon"]
        .nunique()
        .rename("horizons_present")
        .reset_index()
    )
    keep = counts[counts["horizons_present"].eq(int(max_horizon))][["stream", "origin"]]
    return predictions.merge(keep, on=["stream", "origin"], how="inner")


def _horizon_metrics(
    predictions: pd.DataFrame,
    reference_revenue: dict[str, float],
    *,
    cohort: str,
    target_window: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (stream, horizon), group in predictions.groupby(
        ["stream", "horizon"], dropna=False
    ):
        actual = pd.to_numeric(group["actual"], errors="coerce").to_numpy(dtype=float)
        pred = pd.to_numeric(group["pred"], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(actual) & np.isfinite(pred) & (actual > 0)
        if not mask.any():
            continue
        selected = group.loc[mask]
        actual, pred = actual[mask], pred[mask]
        error = pred - actual
        signed_pct = float(np.mean(error / actual) * 100.0)
        target_periods = sorted(selected["target_period"].astype(str).unique())
        origins = sorted(selected["origin"].astype(str).unique())
        rows.append(
            {
                "cohort": cohort,
                "target_window": target_window,
                "stream": stream,
                "stream_label": STREAM_LABELS.get(str(stream), str(stream)),
                "horizon": int(horizon),
                "horizon_support_state": (
                    "H1-H12"
                    if int(horizon) <= BACKTEST_SUPPORTED_MAX_HORIZON
                    else (
                        "H13-H20"
                        if int(horizon) <= EXTENDED_EVIDENCE_MAX_HORIZON
                        else "H21+"
                    )
                ),
                "n_observations": int(actual.size),
                "n_origins": len(origins),
                "n_target_quarters": len(target_periods),
                "first_origin": origins[0],
                "last_origin": origins[-1],
                "first_target_period": target_periods[0],
                "last_target_period": target_periods[-1],
                "mape_pct": float(np.mean(np.abs(error / actual)) * 100.0),
                "wape_pct": float(np.sum(np.abs(error)) / np.sum(actual) * 100.0),
                "rmse": float(np.sqrt(np.mean(error**2))),
                "signed_mean_error_pct": signed_pct,
                "signed_mean_error": float(np.mean(error)),
                "revenue_equivalent_signed_error_nzd_m": (
                    signed_pct / 100.0 * reference_revenue[str(stream)]
                ),
                "signed_error_definition": SIGNED_ERROR_DEFINITION,
                "revenue_equivalent_basis": REVENUE_EQUIVALENT_BASIS,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["cohort", "target_window", "stream", "horizon"])
        .reset_index(drop=True)
    )


def _june_year(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    return year + 1 if quarter >= 3 else year


def _annual_errors(
    predictions: pd.DataFrame, *, cohort: str, target_window: str
) -> pd.DataFrame:
    """June-year error, scored only where all four quarters share an origin."""

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
                "cohort": cohort,
                "target_window": target_window,
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
    annual["horizon_support_state"] = np.where(
        annual["last_horizon"] <= BACKTEST_SUPPORTED_MAX_HORIZON,
        "H1-H12",
        np.where(
            annual["last_horizon"] <= EXTENDED_EVIDENCE_MAX_HORIZON, "H13-H20", "H21+"
        ),
    )
    return annual.sort_values(["stream", "origin", "june_year"]).reset_index(drop=True)


def _annual_summary(
    annual: pd.DataFrame, reference_revenue: dict[str, float]
) -> pd.DataFrame:
    if annual.empty:
        return annual
    rows: list[dict[str, Any]] = []
    for (cohort, window, stream, state), group in annual.groupby(
        ["cohort", "target_window", "stream", "horizon_support_state"], dropna=False
    ):
        cumulative_pct = float(
            group["signed_error"].sum() / group["actual"].sum() * 100.0
        )
        rows.append(
            {
                "cohort": cohort,
                "target_window": window,
                "stream": stream,
                "stream_label": STREAM_LABELS.get(str(stream), str(stream)),
                "horizon_support_state": state,
                "n_june_years": int(len(group)),
                "annual_mape_pct": float(group["abs_error_pct"].mean()),
                "annual_signed_bias_pct": float(group["signed_error_pct"].mean()),
                "cumulative_signed_error_units": float(group["signed_error"].sum()),
                "cumulative_actual_units": float(group["actual"].sum()),
                "cumulative_signed_error_pct": cumulative_pct,
                "cumulative_revenue_equivalent_error_nzd_m": (
                    cumulative_pct / 100.0 * reference_revenue[str(stream)]
                ),
                "revenue_equivalent_basis": REVENUE_EQUIVALENT_BASIS,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["cohort", "target_window", "stream", "horizon_support_state"])
        .reset_index(drop=True)
    )


def _provenance(max_horizon: int, reference_revenue: dict[str, float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stream in STATE_DIRS:
        manifest_path = _finalist_manifest_path(stream)
        history_path = (
            REPO_ROOT / MODEL_INPUT_HISTORY_DIR / MODEL_INPUT_HISTORY_FILES[stream]
        )
        manifest = _finalist_manifest(stream)
        rows.append(
            {
                "stream": stream,
                "stream_label": STREAM_LABELS[stream],
                "finalist_model": manifest.get("finalist_model"),
                "pipeline_version": manifest.get("pipeline_version"),
                "scorer_version": SCRIPT_VERSION,
                "forecast_runner_version": FORECAST_RUNNER_VERSION,
                "max_horizon": int(max_horizon),
                "backtest_supported_max_horizon": BACKTEST_SUPPORTED_MAX_HORIZON,
                "extended_evidence_max_horizon": EXTENDED_EVIDENCE_MAX_HORIZON,
                "signed_error_definition": SIGNED_ERROR_DEFINITION,
                "driver_basis": "actual_observed_drivers",
                "target_lag_basis": (
                    "recursive_predicted_target_lags"
                    if stream in VNEXT_STREAMS
                    else "no_target_lags_in_recipe"
                ),
                "fitted_model_manifest_path": str(
                    manifest_path.relative_to(REPO_ROOT)
                ).replace("\\", "/"),
                "fitted_model_manifest_sha256": _sha256(manifest_path),
                "input_history_path": str(history_path.relative_to(REPO_ROOT)).replace(
                    "\\", "/"
                ),
                "input_history_sha256": _sha256(history_path),
                "reference_revenue_fy": REVENUE_REFERENCE_FY,
                "reference_revenue_series": REVENUE_REFERENCE_SERIES[stream],
                "reference_revenue_nzd_m": reference_revenue[stream],
                "prediction_interval_coverage": (
                    "unavailable_no_governed_interval_from_production_scorer"
                ),
            }
        )
    return pd.DataFrame(rows)


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


_REPORT_COLUMNS = [
    "stream",
    "horizon",
    "horizon_support_state",
    "n_observations",
    "n_origins",
    "first_target_period",
    "last_target_period",
    "mape_pct",
    "wape_pct",
    "rmse",
    "signed_mean_error_pct",
    "revenue_equivalent_signed_error_nzd_m",
]


def _report(
    metrics: pd.DataFrame,
    annual_summary: pd.DataFrame,
    provenance: pd.DataFrame,
    max_horizon: int,
) -> str:
    def slice_of(cohort: str, window: str) -> pd.DataFrame:
        selected = metrics[
            metrics["cohort"].eq(cohort) & metrics["target_window"].eq(window)
        ]
        return selected[_REPORT_COLUMNS]

    lines = [
        "# Long-horizon rolling-origin evaluation",
        "",
        f"Fixed finalists scored to H{max_horizon} on the committed input history.",
        "",
        "## What this is",
        "",
        "* Actual-driver: exogenous inputs at each target quarter are the observed",
        "  values, so this isolates model degradation with horizon and understates",
        "  real forward error, which also carries driver-forecast error.",
        "* Origin-correct: every origin refits on rows at or before that origin.",
        "  PED and Heavy RUC use recursive predicted target lags; Light RUC has no",
        "  target lags. Realized future target values never enter a lagged",
        "  dependent variable. Origin/target ordering is asserted, not assumed -",
        "  see `_assert_no_future_target_leakage`.",
        f"* Signed error: `{SIGNED_ERROR_DEFINITION}`.",
        "* Prediction-interval coverage is not reported: the production scorer",
        "  publishes no governed interval, and manufacturing one would be worse",
        "  than its absence.",
        "",
        "## Governed horizon support states",
        "",
        "| State | Meaning |",
        "|---|---|",
        "| H1-H12 | Backtest-supported range of the committed evidence pack. |",
        "| H13-H20 | Extended conditional evidence from this script; thinner samples, not validated to the short-term standard. |",
        "| H21+ | No extended evaluation evidence; unvalidated long-range extrapolation. |",
        "",
        "## All available origins, all targets",
        "",
        "Sample size falls with horizon, so H1 and H20 describe different origin",
        "sets. This mixes a horizon effect with a composition effect - read the",
        "balanced cohort below before concluding.",
        "",
        _markdown_table(slice_of("all_available", "all_targets")),
        "",
        "## Balanced cohort: identical origins at every horizon",
        "",
        f"Restricted to origins observed at every horizon 1..{max_horizon}. H1 and",
        "H20 are computed from the same origins, so surviving degradation is a",
        "horizon effect rather than a change in which periods are scored.",
        "",
        _markdown_table(slice_of("balanced_h20", "all_targets")),
        "",
        "## Balanced cohort excluding 2020-2021 targets",
        "",
        "The original methodology excluded 2020-2021 outcomes from",
        "forecast-accuracy tests while retaining them in training data, on the",
        "grounds that they were not realistically forecastable.",
        "",
        _markdown_table(slice_of("balanced_h20", "excl_2020_2021")),
        "",
        "## June-year error by support state",
        "",
        "Only June years whose four quarters all come from one origin are scored.",
        "",
        (
            _markdown_table(annual_summary)
            if not annual_summary.empty
            else "_No complete June years available._"
        ),
        "",
        "## Provenance",
        "",
        _markdown_table(provenance),
        "",
        "## What this does and does not establish",
        "",
        "The H13-H20 actual-driver evaluation shows material error growth,",
        "especially for Light RUC, and historical average signed error is",
        "positive. This weakens a systematic downward conditional-model-bias",
        "explanation for the current MBU26 gap. Because this is not a",
        "forecast-vintage comparison, it does not identify the source of the gap.",
        "The common-input decomposition is therefore the next diagnostic",
        "workstream. A structural long-term bridge remains open as a",
        "forecast-governance project.",
        "",
        "Specifically, this evaluation does **not** distinguish between input",
        "vintage, MBU26 assumptions, migration and class definitions,",
        "path-specific model dynamics, and judgmental overlays. A positive",
        "historical model bias is compatible with a model path below MBU26 - for",
        "instance if MBU26 is itself high relative to eventual outcomes, or if the",
        "two forecasts share direction but differ in long-run level.",
        "",
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
    parser.add_argument(
        "--streams", nargs="*", default=["PED", "LIGHT_RUC", "HEAVY_RUC"]
    )
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
    _assert_no_future_target_leakage(predictions)
    reference_revenue = _reference_revenue()

    balanced = _balanced_origins(predictions, args.max_horizon)
    target_year = predictions["target_period"].astype(str).str[:4].astype(int)
    balanced_year = balanced["target_period"].astype(str).str[:4].astype(int)
    excluded = list(EXCLUDED_TARGET_YEARS)
    cohorts = [
        ("all_available", "all_targets", predictions),
        ("all_available", "excl_2020_2021", predictions[~target_year.isin(excluded)]),
        ("balanced_h20", "all_targets", balanced),
        ("balanced_h20", "excl_2020_2021", balanced[~balanced_year.isin(excluded)]),
    ]

    metric_frames: list[pd.DataFrame] = []
    annual_frames: list[pd.DataFrame] = []
    for cohort, window, frame in cohorts:
        if frame.empty:
            continue
        metric_frames.append(
            _horizon_metrics(
                frame, reference_revenue, cohort=cohort, target_window=window
            )
        )
        annual = _annual_errors(frame, cohort=cohort, target_window=window)
        if not annual.empty:
            annual_frames.append(annual)

    metrics = pd.concat(metric_frames, ignore_index=True, sort=False)
    annual = (
        pd.concat(annual_frames, ignore_index=True, sort=False)
        if annual_frames
        else pd.DataFrame()
    )
    annual_summary = _annual_summary(annual, reference_revenue)
    provenance = _provenance(args.max_horizon, reference_revenue)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_dir / "long_horizon_predictions.csv", index=False)
    metrics.to_csv(output_dir / "long_horizon_metrics_by_horizon.csv", index=False)
    annual.to_csv(output_dir / "long_horizon_june_year_errors.csv", index=False)
    annual_summary.to_csv(output_dir / "long_horizon_june_year_summary.csv", index=False)
    provenance.to_csv(output_dir / "long_horizon_provenance.csv", index=False)
    (output_dir / "long_horizon_report.md").write_text(
        _report(metrics, annual_summary, provenance, args.max_horizon), encoding="utf-8"
    )

    print()
    for cohort, window in [
        ("all_available", "all_targets"),
        ("balanced_h20", "all_targets"),
        ("balanced_h20", "excl_2020_2021"),
    ]:
        selected = metrics[
            metrics["cohort"].eq(cohort) & metrics["target_window"].eq(window)
        ]
        if selected.empty:
            continue
        print(f"--- {cohort} / {window}")
        print(
            selected[
                [
                    "stream",
                    "horizon",
                    "n_observations",
                    "mape_pct",
                    "signed_mean_error_pct",
                ]
            ]
            .query("horizon in [1, 12, 20]")
            .to_string(index=False)
        )
        print()
    print(f"Written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
