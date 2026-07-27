"""Before/after impact of loading the promoted Light RUC state instead of refitting.

Light RUC used to refit its OLS base and residual GBM at score time, which made
it the only stream whose governed forecast depended on the machine running it.
This script quantifies what changes when the promoted fitted state is loaded
instead, across every scenario and fiscal year, so the change is reviewed on
evidence rather than accepted on principle.

"Before" is reconstructed by refitting the recipe on this machine - exactly what
the removed code did - and injecting it in place of the promoted state. "After"
is the promoted state. Both are then run through the same governed replay, so
the comparison covers the full bridge, not just the model output.

The promoted state is NOT selected for closeness to MBU26; MBU26 does not enter
this script at all.

Usage::

    python scripts/light_ruc_promoted_state_impact.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard import forecast_runner as fr  # noqa: E402

SCENARIO_INPUTS = (
    REPO_ROOT
    / "data"
    / "current_revenue_outlook"
    / "scenario_inputs"
    / "scenario_input_wide.parquet"
)
# Platform envelope measured between the former Windows and Linux refits.
PLATFORM_ENVELOPE_PCT = 0.48


def _refit_state() -> fr.LightRucPromotedState:
    """Reconstruct what the removed runtime refit produced on this machine."""

    from sklearn.ensemble import GradientBoostingRegressor

    history = pd.read_parquet(
        REPO_ROOT / fr.MODEL_INPUT_HISTORY_DIR / fr.MODEL_INPUT_HISTORY_FILES["LIGHT_RUC"]
    )
    latest = fr.latest_known_actual_period(REPO_ROOT)
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
    return fr.LightRucPromotedState(
        ols_beta=beta,
        base_features=tuple(fr.LIGHT_RUC_BASE_FEATURES),
        residual_model=residual_model,
        residual_features=tuple(fr.LIGHT_RUC_RESIDUAL_FEATURES),
        window=fr.LIGHT_RUC_WINDOW,
        random_state=42,
        recipe="runtime refit reconstruction (former behaviour)",
        sha256="runtime_refit_not_promoted",
        train_window_start=str(train.iloc[0]["period"]),
        train_window_end=str(train.iloc[-1]["period"]),
        train_rows=len(train),
        max_training_fit_replay_delta=float("nan"),
    )


def _annual_bridge(state: fr.LightRucPromotedState | None) -> pd.DataFrame:
    """Run the governed replay, optionally with an injected Light RUC state."""

    from model_dashboard.fuel_price_scenario import run_fuel_price_scenario_replay

    original = fr.load_light_ruc_promoted_state
    if state is not None:
        fr.load_light_ruc_promoted_state = lambda *args, **kwargs: state  # noqa: ARG005
    try:
        replay = run_fuel_price_scenario_replay(
            pd.read_parquet(SCENARIO_INPUTS), repo_root=REPO_ROOT, engine="ensemble"
        )
    finally:
        fr.load_light_ruc_promoted_state = original
    return replay.annual_bridge.copy()


def _compare(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    keys = [
        key
        for key in ("scenario_name", "fed_path", "series_id", "FY")
        if key in before.columns
    ]
    merged = before.merge(after, on=keys, suffixes=("_before", "_after"), how="outer")
    a = pd.to_numeric(merged["value_before"], errors="coerce")
    b = pd.to_numeric(merged["value_after"], errors="coerce")
    merged["abs_change"] = b - a
    merged["pct_change"] = np.where(a.abs() > 0, (b - a) / a.abs() * 100.0, np.nan)
    return merged[keys + ["value_before", "value_after", "abs_change", "pct_change"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "artifacts" / "light_ruc_promoted_state_impact",
    )
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    print("[impact] running replay with the former runtime refit ...", flush=True)
    before = _annual_bridge(_refit_state())
    print("[impact] running replay with the promoted fitted state ...", flush=True)
    after = _annual_bridge(None)

    comparison = _compare(before, after)
    comparison.to_csv(output / "annual_bridge_before_after.csv", index=False)

    focus = comparison[
        comparison["series_id"].astype(str).isin(
            [
                "light_ruc_net_km",
                "light_ruc_net_revenue",
                "total_ruc_net_revenue",
                "total_nltf_net_revenue",
                "net_fed_revenue",
                "net_mvr_revenue",
            ]
        )
        & pd.to_numeric(comparison["FY"], errors="coerce").between(2026, 2030)
    ].copy()
    focus.to_csv(output / "fy2026_fy2030_focus.csv", index=False)

    summary = (
        comparison.assign(abs_pct=comparison["pct_change"].abs())
        .groupby("series_id", dropna=False)["abs_pct"]
        .agg(["count", "max", "mean"])
        .sort_values("max", ascending=False)
        .reset_index()
    )
    summary.to_csv(output / "impact_by_series.csv", index=False)

    worst = float(comparison["pct_change"].abs().max())
    print()
    print(summary.head(15).to_string(index=False))
    print()
    print(f"max |pct change| across every series and year: {worst:.4f}%")
    print(f"platform envelope between the former refits:   {PLATFORM_ENVELOPE_PCT:.2f}%")
    if worst > PLATFORM_ENVELOPE_PCT:
        print(
            "\nSTOP CONDITION: the promoted state moves values by more than the "
            "platform envelope. Investigate state lineage or training basis "
            "before promoting."
        )
        return 1
    print("\nWithin the platform envelope: no stop condition triggered.")
    print(f"Written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
