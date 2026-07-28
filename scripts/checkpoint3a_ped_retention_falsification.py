"""Checkpoint 3A: does the VFM petrol-retention overlay improve PED forecasts?

The corrected Checkpoint 2 established that the decision-facing PED path is
    raw AR(1) VKT per capita  x  one prospective VFM retention curve
with lambda fully removed by the raw bridge. What is not established is whether
that single overlay adds genuine fleet-transition information, or duplicates a
decline already carried by the AR(1) trend, post-2011 slope and post-2020
controls.

P0  raw AR(1) recursive forecast, no overlay.
P1  the same forecast x an origin-normalised VFM retention curve.

Both use identical origins, identical driver paths and identical actuals, so
the only difference is the overlay.

IMPORTANT - P1 IS A STRUCTURAL HINDCAST, NOT A REAL-TIME FORECAST TEST.
data/vfm_202405 is a single May 2024 vintage. No historical VFM vintages exist
in this repository, so at every origin before 2024Q2 the retention curve embeds
information that was not available at that origin. P1 therefore enjoys an
information advantage that a real-time forecaster would not have had. If P1
fails to beat P0 even with that advantage, the finding is strong.

Investigation only. Writes only to artifacts/fleet_allocation_semantics/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.ev_uptake_levers import (  # noqa: E402
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_PRESETS,
    solve_logistic_from_levers,
)

OUT = ROOT / "artifacts" / "fleet_allocation_semantics"
OUT.mkdir(parents=True, exist_ok=True)

AR1_PREDICTIONS = (
    ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "ped_ar1" / "validation_predictions.parquet"
)
LONG_HORIZON_PREDICTIONS = ROOT / "artifacts" / "long_horizon_validation" / "long_horizon_predictions.csv"
COVID_TARGET_YEARS = (2020, 2021)


def june_year(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    return year + 1 if quarter >= 3 else year


def retention_ratio(origin_fy: pd.Series, target_fy: pd.Series) -> pd.Series:
    """VFM petrol retention between two June years, normalised to 1 at origin.

    retention(origin -> target) = (1 - d(target)) / (1 - d(origin))

    where d is the logistic displacement implied by the MoT VFM base levers.
    This is the same curve ped_retention_curve() applies in the runtime; only
    the normalisation origin moves, from FY2025 to each backtest origin.
    """
    levers = EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]
    smax, k = solve_logistic_from_levers(
        levers.ped_disp_speed_pp, levers.ped_disp_midpoint, levers.ped_disp_2050
    )
    mid = float(levers.ped_disp_midpoint)

    def displacement(years: pd.Series) -> pd.Series:
        return smax / (1.0 + np.exp(-k * (years.astype(float) - mid)))

    ratio = (1.0 - displacement(target_fy)) / (1.0 - displacement(origin_fy))
    return ratio.clip(lower=0.0, upper=1.0)


def load_predictions() -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if AR1_PREDICTIONS.exists():
        ar1 = pd.read_parquet(AR1_PREDICTIONS)
        out["ar1_production_h1_h12"] = ar1[ar1["stream"].eq("PED")].copy()
    if LONG_HORIZON_PREDICTIONS.exists():
        long_h = pd.read_csv(LONG_HORIZON_PREDICTIONS)
        out["vnext_ensemble_h1_h20"] = long_h[long_h["stream"].eq("PED")].copy()
    return out


def build_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["origin_june_year"] = out["origin"].map(june_year)
    out["target_june_year"] = out["target_period"].map(june_year)
    out["retention_ratio"] = retention_ratio(out["origin_june_year"], out["target_june_year"])
    out["pred_P0"] = out["pred"].astype(float)
    out["pred_P1"] = out["pred"].astype(float) * out["retention_ratio"]
    for variant in ["P0", "P1"]:
        out[f"error_{variant}"] = out[f"pred_{variant}"] - out["actual"].astype(float)
        out[f"abs_error_{variant}"] = out[f"error_{variant}"].abs()
        out[f"pct_error_{variant}"] = 100.0 * out[f"error_{variant}"] / out["actual"].astype(float)
    return out


def assert_no_leakage(pairs: pd.DataFrame) -> None:
    """The overlay must never look past the origin."""
    assert (pairs["target_june_year"] >= pairs["origin_june_year"]).all()
    # Retention is 1.0 when target and origin share a June year, and weakly
    # decreasing thereafter: it is a function of horizon only, not of outcomes.
    same_year = pairs[pairs["target_june_year"].eq(pairs["origin_june_year"])]
    assert np.allclose(same_year["retention_ratio"], 1.0, atol=1e-12)
    assert (pairs["retention_ratio"] <= 1.0 + 1e-12).all()


def metrics(frame: pd.DataFrame, variant: str) -> dict[str, float]:
    actual = frame["actual"].astype(float)
    err = frame[f"error_{variant}"]
    return {
        "n": int(len(frame)),
        "mape": float((err.abs() / actual).mean() * 100.0),
        "wape": float(err.abs().sum() / actual.sum() * 100.0),
        "rmse": float(np.sqrt((err**2).mean())),
        "signed_error_pct": float((err / actual).mean() * 100.0),
        "mean_abs_error": float(err.abs().mean()),
    }


def balanced_origins(frame: pd.DataFrame) -> pd.DataFrame:
    """Origins observed at every horizon, so horizons share one origin set."""
    horizons = set(frame["horizon"].unique())
    keep = [
        origin
        for origin, rows in frame.groupby("origin")
        if set(rows["horizon"].unique()) >= horizons
    ]
    return frame[frame["origin"].isin(keep)]


def covid_masks(pairs: pd.DataFrame) -> dict[str, pd.Series]:
    """Three COVID definitions, kept distinct and labelled.

    The production specification defines the COVID control on *calendar*
    quarters 2020Q1-2021Q4 (see deliverables/PED-VKT-model-review, covid2020).
    An earlier version of this script excluded June years FY2020-FY2021, which
    is the window 2019Q3-2021Q2 - a different set. All three are reported.
    """
    period = pairs["target_period"].astype(str)
    calendar_year = period.str.slice(0, 4).astype(int)
    return {
        # primary: the stated specification window, by calendar quarter
        "ex_covid_2020Q1_2021Q4": ~period.between("2020Q1", "2021Q4"),
        # secondary: calendar years 2020 and 2021
        "ex_covid_calendar_2020_2021": ~calendar_year.isin((2020, 2021)),
        # relabelled original: June years FY2020-FY2021 = 2019Q3-2021Q2
        "ex_covid_june_years_fy2020_fy2021": ~pairs["target_june_year"].isin(COVID_TARGET_YEARS),
    }


def cohort_frames(pairs: pd.DataFrame) -> dict[str, pd.DataFrame]:
    frames = {
        "all_available": pairs,
        "balanced": balanced_origins(pairs),
    }
    for label, mask in covid_masks(pairs).items():
        subset = pairs[mask]
        frames[f"all_available_{label}"] = subset
        # Balancing is recomputed inside each exclusion so that P0 and P1 always
        # share an identical origin grid within a sensitivity.
        frames[f"balanced_{label}"] = balanced_origins(subset)
    return frames


def main() -> int:
    sources = load_predictions()
    if not sources:
        print("No committed rolling-origin predictions found.")
        return 1

    all_pairs = []
    horizon_rows = []
    annual_rows = []
    summary_rows = []

    for source, frame in sources.items():
        pairs = build_pairs(frame)
        assert_no_leakage(pairs)
        pairs["source"] = source
        pairs["vfm_vintage_status"] = "structural_hindcast_single_202405_vintage"
        all_pairs.append(pairs)

        for cohort, cohort_frame in cohort_frames(pairs).items():
            if cohort_frame.empty:
                continue
            # by horizon
            for horizon, rows in cohort_frame.groupby("horizon"):
                record = {"source": source, "cohort": cohort, "horizon": int(horizon)}
                for variant in ["P0", "P1"]:
                    for key, value in metrics(rows, variant).items():
                        record[f"{variant}_{key}"] = value
                record["wape_improvement_pct"] = (
                    100.0 * (record["P0_wape"] - record["P1_wape"]) / record["P0_wape"]
                )
                record["mape_improvement_pct"] = (
                    100.0 * (record["P0_mape"] - record["P1_mape"]) / record["P0_mape"]
                )
                horizon_rows.append(record)

            # pooled over horizons, and over H1-H12 specifically
            for label, subset in [
                ("all_horizons", cohort_frame),
                ("h1_h12", cohort_frame[cohort_frame["horizon"].le(12)]),
                ("h13_h20", cohort_frame[cohort_frame["horizon"].ge(13)]),
            ]:
                if subset.empty:
                    continue
                record = {"source": source, "cohort": cohort, "horizon_band": label, "n_origins": int(subset["origin"].nunique()), "n_predictions": int(len(subset))}
                for variant in ["P0", "P1"]:
                    for key, value in metrics(subset, variant).items():
                        record[f"{variant}_{key}"] = value
                record["wape_improvement_pct"] = (
                    100.0 * (record["P0_wape"] - record["P1_wape"]) / record["P0_wape"]
                )
                record["mape_improvement_pct"] = (
                    100.0 * (record["P0_mape"] - record["P1_mape"]) / record["P0_mape"]
                )
                record["signed_bias_change"] = record["P1_signed_error_pct"] - record["P0_signed_error_pct"]
                summary_rows.append(record)

            # June-year aggregation: sum the four quarters of each FY per origin
            annual = (
                cohort_frame.groupby(["origin", "target_june_year"])
                .agg(
                    quarters=("actual", "size"),
                    actual=("actual", "sum"),
                    pred_P0=("pred_P0", "sum"),
                    pred_P1=("pred_P1", "sum"),
                )
                .reset_index()
            )
            annual = annual[annual["quarters"].eq(4)]
            if annual.empty:
                continue
            for variant in ["P0", "P1"]:
                annual[f"error_{variant}"] = annual[f"pred_{variant}"] - annual["actual"]
            record = {"source": source, "cohort": cohort, "n_annual": int(len(annual))}
            for variant in ["P0", "P1"]:
                err = annual[f"error_{variant}"]
                record[f"{variant}_annual_mape"] = float((err.abs() / annual["actual"]).mean() * 100.0)
                record[f"{variant}_annual_wape"] = float(err.abs().sum() / annual["actual"].sum() * 100.0)
                record[f"{variant}_annual_signed_pct"] = float((err / annual["actual"]).mean() * 100.0)
            record["annual_wape_improvement_pct"] = (
                100.0
                * (record["P0_annual_wape"] - record["P1_annual_wape"])
                / record["P0_annual_wape"]
            )
            annual_rows.append(record)

    predictions = pd.concat(all_pairs, ignore_index=True)
    horizon_metrics = pd.DataFrame(horizon_rows)
    annual_metrics = pd.DataFrame(annual_rows)
    summary = pd.DataFrame(summary_rows)

    predictions.round(9).to_csv(OUT / "ped_retention_rolling_predictions.csv", index=False)
    horizon_metrics.round(6).to_csv(OUT / "ped_retention_horizon_metrics.csv", index=False)
    annual_metrics.round(6).to_csv(OUT / "ped_retention_annual_metrics.csv", index=False)
    summary.round(6).to_csv(OUT / "ped_retention_band_summary.csv", index=False)

    # ---- decision gate ---------------------------------------------------
    primary = summary[
        summary["source"].eq("ar1_production_h1_h12")
        & summary["cohort"].eq("balanced")
        & summary["horizon_band"].eq("h1_h12")
    ]
    verdict = {"gate_evaluated": False}
    if not primary.empty:
        row = primary.iloc[0]
        wape_gain = float(row["wape_improvement_pct"])
        mape_gain = float(row["mape_improvement_pct"])
        bias_change = abs(float(row["signed_bias_change"]))
        base_bias = abs(float(row["P0_signed_error_pct"]))
        consistent = []
        for cohort in ["balanced", "balanced_ex_covid_2020Q1_2021Q4", "all_available", "all_available_ex_covid_2020Q1_2021Q4"]:
            sub = summary[
                summary["source"].eq("ar1_production_h1_h12")
                & summary["cohort"].eq(cohort)
                & summary["horizon_band"].eq("h1_h12")
            ]
            if not sub.empty:
                consistent.append(float(sub.iloc[0]["wape_improvement_pct"]) > 0.0)
        annual_gain = annual_metrics[
            annual_metrics["source"].eq("ar1_production_h1_h12")
            & annual_metrics["cohort"].eq("balanced")
        ]
        verdict = {
            "gate_evaluated": True,
            "balanced_h1_h12_wape_improvement_pct": wape_gain,
            "balanced_h1_h12_mape_improvement_pct": mape_gain,
            "signed_bias_change_pp": float(row["signed_bias_change"]),
            "P0_signed_bias_pct": float(row["P0_signed_error_pct"]),
            "P1_signed_bias_pct": float(row["P1_signed_error_pct"]),
            "annual_wape_improvement_pct": (
                float(annual_gain.iloc[0]["annual_wape_improvement_pct"]) if not annual_gain.empty else float("nan")
            ),
            "improvement_consistent_across_cohorts": bool(consistent) and all(consistent),
            "gate_a_five_pct_wape_or_mape": bool(max(wape_gain, mape_gain) >= 5.0),
            "gate_b_consistent_smaller_improvement": bool(
                bool(consistent) and all(consistent) and max(wape_gain, mape_gain) > 0.0
            ),
            "bias_materially_worse": bool(bias_change > 0.5 and abs(float(row["P1_signed_error_pct"])) > base_bias),
        }
        verdict["adopt_P1_as_production_baseline"] = bool(
            (verdict["gate_a_five_pct_wape_or_mape"] or verdict["gate_b_consistent_smaller_improvement"])
            and not verdict["bias_materially_worse"]
        )
    pd.DataFrame([verdict]).to_csv(OUT / "ped_retention_decision_gate.csv", index=False)

    # ---- console ---------------------------------------------------------
    print("=== sources ===")
    for source, frame in sources.items():
        print(f"  {source}: {len(frame)} rows, horizons {frame.horizon.min()}-{frame.horizon.max()}, "
              f"{frame.origin.nunique()} origins, model {frame.model.unique()[0]}")
    print("\nP1 is a STRUCTURAL HINDCAST: VFM 202405 is a single May-2024 vintage,")
    print("so origins before 2024Q2 use information unavailable at the time.\n")

    print("=== pooled band summary ===")
    cols = [
        "source", "cohort", "horizon_band", "P0_n", "P0_wape", "P1_wape",
        "wape_improvement_pct", "P0_mape", "P1_mape", "mape_improvement_pct",
        "P0_signed_error_pct", "P1_signed_error_pct",
    ]
    print(summary[cols].round(3).to_string(index=False))

    print("\n=== June-year annual metrics ===")
    print(annual_metrics.round(3).to_string(index=False))

    print("\n=== AR(1) production, balanced cohort, by horizon ===")
    sel = horizon_metrics[
        horizon_metrics["source"].eq("ar1_production_h1_h12") & horizon_metrics["cohort"].eq("balanced")
    ]
    print(
        sel[["horizon", "P0_n", "P0_wape", "P1_wape", "wape_improvement_pct",
             "P0_signed_error_pct", "P1_signed_error_pct"]].round(3).to_string(index=False)
    )

    print("\n=== decision gate ===")
    for key, value in verdict.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
