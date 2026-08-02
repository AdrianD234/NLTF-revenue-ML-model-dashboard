"""Gate B (revised): the horizon shape of forecast error, from H1-H20 evidence.

Supersedes the repository-wide conclusion of the first Gate B pass, which read
only ``annual_predictions.parquet`` (58 finalist rows, H1-H3) and missed the
committed rolling-origin pack in ``artifacts/long_horizon_validation/``.  That
pack carries 1 990 raw quarterly forecast/actual rows to H20 with per-cell
samples an order of magnitude larger.

What each source measures is NOT the same thing, and the difference decides
what each may be used for:

  annual_predictions.parquet      annual finalist backtest, H1-H3. Includes
                                  model error only; driver inputs are the
                                  realised values. Small n.
  long_horizon_predictions.csv    rolling-origin, H1-H20 quarters, origin-
                                  correct refits. ACTUAL-DRIVER: exogenous
                                  inputs at each target are observed values,
                                  so it isolates model degradation with
                                  horizon and UNDERSTATES true forward error,
                                  which also carries driver-forecast error.
  MBU26 archived forecast error   a real published forecast's realised error,
                                  so it DOES include driver error, but for the
                                  official model, not the current finalists.

Because the long-horizon pack is actual-driver, it is used here for the SHAPE
of the horizon curve, not for the absolute level. Mixing a shape from one
concept with a level from another is an explicit, named assumption.

    .venv\\Scripts\\python.exe scripts\\build_uncertainty_method_evidence.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LONG_HORIZON = ROOT / "artifacts" / "long_horizon_validation"
OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"

# Deterministic: the bootstrap must not move between runs or platforms.
BOOTSTRAP_SEED = 20260801
BOOTSTRAP_DRAWS = 2000

# The last complete actual June year. FY -> June-year horizon -> quarter horizon.
LAST_ACTUAL_FY = 2025
QUARTERS_PER_YEAR = 4
MAX_SUPPORTED_QUARTER_HORIZON = 20
POOL_BUCKETS = ((1, 4), (5, 8), (9, 12), (13, 16), (17, 20))


def june_year_horizon(fy: int) -> int:
    return int(fy) - LAST_ACTUAL_FY


def quarter_horizon(fy: int) -> int:
    """The LAST quarter horizon inside that June year."""
    return june_year_horizon(fy) * QUARTERS_PER_YEAR


def load_predictions() -> pd.DataFrame:
    frame = pd.read_csv(LONG_HORIZON / "long_horizon_predictions.csv")
    frame["horizon"] = pd.to_numeric(frame["horizon"], errors="coerce").astype("Int64")
    frame["actual"] = pd.to_numeric(frame["actual"], errors="coerce")
    frame["pred"] = pd.to_numeric(frame["pred"], errors="coerce")
    frame = frame.dropna(subset=["horizon", "actual", "pred"])
    frame = frame[(frame["actual"] > 0) & (frame["pred"] > 0)]
    # log(actual/pred): positive = the forecast was too low.
    frame["log_error"] = np.log(frame["actual"] / frame["pred"])
    frame["target_year"] = frame["target_period"].astype(str).str.slice(0, 4).astype(int)
    frame["excl_2020_2021"] = ~frame["target_year"].isin((2020, 2021))
    # A balanced cohort: only origins that reach the full H20, so a horizon
    # effect is not confounded with a changing origin set.
    reach = frame.groupby(["stream", "origin"])["horizon"].max()
    balanced = set(reach[reach >= MAX_SUPPORTED_QUARTER_HORIZON].index)
    frame["balanced_h20"] = [
        (row.stream, row.origin) in balanced for row in frame.itertuples()
    ]
    return frame


def width_quantiles(values: np.ndarray) -> dict[str, float]:
    if len(values) == 0:
        return {}
    q10, q25, q50, q75, q90 = np.quantile(values, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "q10": q10,
        "q25": q25,
        "median": q50,
        "q75": q75,
        "q90": q90,
        # Relative widths in ratio space, which is what a band multiplies by.
        "width50_pct": 100.0 * (np.exp(q75) - np.exp(q25)),
        "width80_pct": 100.0 * (np.exp(q90) - np.exp(q10)),
    }


def bootstrap_width_interval(values: np.ndarray, level: str) -> tuple[float, float]:
    """Percentile bootstrap around the relative width. Seeded."""
    if len(values) < 3:
        return (float("nan"), float("nan"))
    generator = np.random.default_rng(BOOTSTRAP_SEED)
    low_q, high_q = (0.25, 0.75) if level == "50" else (0.10, 0.90)
    widths = np.empty(BOOTSTRAP_DRAWS)
    for draw in range(BOOTSTRAP_DRAWS):
        sample = generator.choice(values, size=len(values), replace=True)
        low, high = np.quantile(sample, [low_q, high_q])
        widths[draw] = 100.0 * (np.exp(high) - np.exp(low))
    return tuple(np.quantile(widths, [0.05, 0.95]))


def horizon_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort in ("all_available", "balanced_h20"):
        cohort_frame = frame if cohort == "all_available" else frame[frame["balanced_h20"]]
        for window in ("all_targets", "excl_2020_2021"):
            window_frame = (
                cohort_frame if window == "all_targets" else cohort_frame[cohort_frame["excl_2020_2021"]]
            )
            for stream, stream_frame in window_frame.groupby("stream"):
                for horizon, cell in stream_frame.groupby("horizon"):
                    values = cell["log_error"].to_numpy()
                    record = {
                        "cohort": cohort,
                        "target_window": window,
                        "stream": stream,
                        "horizon": int(horizon),
                        "horizon_support_state": "H1-H12" if int(horizon) <= 12 else "H13-H20",
                        "n": len(values),
                        **width_quantiles(values),
                    }
                    lo50, hi50 = bootstrap_width_interval(values, "50")
                    lo80, hi80 = bootstrap_width_interval(values, "80")
                    record.update(
                        {
                            "width50_boot_p05": lo50,
                            "width50_boot_p95": hi50,
                            "width80_boot_p05": lo80,
                            "width80_boot_p95": hi80,
                        }
                    )
                    rows.append(record)
    return pd.DataFrame(rows)


def pooled_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort in ("all_available", "balanced_h20"):
        cohort_frame = frame if cohort == "all_available" else frame[frame["balanced_h20"]]
        for window in ("all_targets", "excl_2020_2021"):
            window_frame = (
                cohort_frame if window == "all_targets" else cohort_frame[cohort_frame["excl_2020_2021"]]
            )
            for stream, stream_frame in window_frame.groupby("stream"):
                for low, high in POOL_BUCKETS:
                    cell = stream_frame[
                        stream_frame["horizon"].between(low, high)
                    ]
                    values = cell["log_error"].to_numpy()
                    if len(values) == 0:
                        continue
                    record = {
                        "cohort": cohort,
                        "target_window": window,
                        "stream": stream,
                        "bucket": f"H{low}-H{high}",
                        "bucket_mid_horizon": (low + high) / 2.0,
                        "horizon_support_state": "H1-H12" if high <= 12 else "H13-H20",
                        "n": len(values),
                        **width_quantiles(values),
                    }
                    lo50, hi50 = bootstrap_width_interval(values, "50")
                    lo80, hi80 = bootstrap_width_interval(values, "80")
                    record.update(
                        {
                            "width50_boot_p05": lo50,
                            "width50_boot_p95": hi50,
                            "width80_boot_p05": lo80,
                            "width80_boot_p95": hi80,
                        }
                    )
                    rows.append(record)
    return pd.DataFrame(rows)


def isotonic(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Monotone non-decreasing fit. Uncertainty must not shrink with horizon."""
    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(increasing=True, out_of_bounds="clip")
    return model.fit_transform(x, y)


def saturating_fit(horizons: np.ndarray, widths: np.ndarray) -> dict[str, float]:
    """w(H) = w_inf - (w_inf - w1) * exp(-k (H-1)), fitted by least squares.

    Constrained: w_inf >= max observed width, k > 0, so the curve is
    non-decreasing and saturates rather than diverging.
    """
    from scipy.optimize import curve_fit

    def model(h, w_inf, w1, k):
        return w_inf - (w_inf - w1) * np.exp(-k * (h - 1.0))

    try:
        popt, _ = curve_fit(
            model,
            horizons.astype(float),
            widths.astype(float),
            p0=[float(widths.max()) * 1.2, float(widths[0]), 0.15],
            bounds=(
                [float(widths.max()), 0.0, 1e-4],
                [float(widths.max()) * 6.0, float(widths.max()), 2.0],
            ),
            maxfev=20000,
        )
    except Exception as error:  # pragma: no cover - reported, not raised
        return {"fit_ok": False, "reason": str(error)[:160]}
    w_inf, w1, k = (float(value) for value in popt)
    fitted = model(horizons.astype(float), w_inf, w1, k)
    residual = float(np.sqrt(np.mean((fitted - widths) ** 2)))
    return {
        "fit_ok": True,
        "w_inf_pct": w_inf,
        "w1_pct": w1,
        "k": k,
        "rmse_pct": residual,
        "half_life_horizons": float(np.log(2.0) / k),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    predictions = load_predictions()

    per_horizon = horizon_table(predictions)
    per_horizon.to_csv(OUT / "long_horizon_error_quantiles.csv", index=False)

    pooled = pooled_table(predictions)
    pooled.to_csv(OUT / "long_horizon_error_quantiles_pooled.csv", index=False)

    # June-year distributions from the committed annual error file.
    june = pd.read_csv(LONG_HORIZON / "long_horizon_june_year_errors.csv")
    june["log_error"] = np.log(
        pd.to_numeric(june["actual"], errors="coerce")
        / pd.to_numeric(june["pred"], errors="coerce")
    )
    june = june.replace([np.inf, -np.inf], np.nan).dropna(subset=["log_error"])
    june["june_year_horizon"] = (
        (pd.to_numeric(june["first_horizon"], errors="coerce") + 3) / QUARTERS_PER_YEAR
    ).round().astype(int)
    june_rows: list[dict] = []
    for (cohort, window, stream, horizon), cell in june.groupby(
        ["cohort", "target_window", "stream", "june_year_horizon"]
    ):
        values = cell["log_error"].to_numpy()
        june_rows.append(
            {
                "cohort": cohort,
                "target_window": window,
                "stream": stream,
                "june_year_horizon": int(horizon),
                "n": len(values),
                **width_quantiles(values),
            }
        )
    june_table = pd.DataFrame(june_rows)
    june_table.to_csv(OUT / "long_horizon_june_year_quantiles.csv", index=False)

    # ------------------------------------------------------- horizon shape
    shape_rows: list[dict] = []
    fits: list[dict] = []
    headline = per_horizon[
        per_horizon["cohort"].eq("all_available")
        & per_horizon["target_window"].eq("all_targets")
    ]
    for stream, cell in headline.groupby("stream"):
        cell = cell.sort_values("horizon")
        horizons = cell["horizon"].to_numpy()
        for level in ("50", "80"):
            raw = cell[f"width{level}_pct"].to_numpy()
            smooth = isotonic(horizons.astype(float), raw)
            pooled_cell = pooled[
                pooled["cohort"].eq("all_available")
                & pooled["target_window"].eq("all_targets")
                & pooled["stream"].eq(stream)
            ].sort_values("bucket_mid_horizon")
            pooled_smooth = np.interp(
                horizons.astype(float),
                pooled_cell["bucket_mid_horizon"].to_numpy(),
                isotonic(
                    pooled_cell["bucket_mid_horizon"].to_numpy(),
                    pooled_cell[f"width{level}_pct"].to_numpy(),
                ),
            )
            fit = saturating_fit(horizons, smooth)
            fit.update({"stream": stream, "level": level})
            fits.append(fit)
            for index, horizon in enumerate(horizons):
                shape_rows.append(
                    {
                        "stream": stream,
                        "level": level,
                        "horizon": int(horizon),
                        "A_raw_width_pct": raw[index],
                        "B_isotonic_width_pct": smooth[index],
                        "C_pooled_isotonic_width_pct": pooled_smooth[index],
                        "D_saturating_width_pct": (
                            fit["w_inf_pct"]
                            - (fit["w_inf_pct"] - fit["w1_pct"]) * np.exp(-fit["k"] * (horizon - 1))
                            if fit.get("fit_ok")
                            else np.nan
                        ),
                    }
                )
    shape = pd.DataFrame(shape_rows)
    shape.to_csv(OUT / "horizon_shape_candidates.csv", index=False)
    fit_frame = pd.DataFrame(fits)
    fit_frame.to_csv(OUT / "saturating_fit_parameters.csv", index=False)

    print("=== per-horizon sample sizes (all_available, all_targets) ===")
    print(
        headline.pivot_table(index="stream", columns="horizon", values="n", aggfunc="first")
        .astype("Int64")
        .to_string()
    )
    print("\n=== 80% relative width by horizon (all_available, all_targets) ===")
    print(
        headline.pivot_table(
            index="stream", columns="horizon", values="width80_pct", aggfunc="first"
        )
        .round(2)
        .to_string()
    )
    print("\n=== pooled buckets, 80% width ===")
    print(
        pooled[pooled["cohort"].eq("all_available") & pooled["target_window"].eq("all_targets")]
        .pivot_table(index="stream", columns="bucket", values="width80_pct", aggfunc="first")
        .round(2)
        .to_string()
    )
    print("\n=== saturating fit parameters ===")
    print(fit_frame.round(4).to_string(index=False))
    print("\n=== horizon shape at H1, H12, H20 (80%) ===")
    print(
        shape[shape["level"].eq("80") & shape["horizon"].isin((1, 12, 20))]
        .round(3)
        .to_string(index=False)
    )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
