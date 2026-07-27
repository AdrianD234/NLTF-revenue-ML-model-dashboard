"""Enumerate every GDP sign-guard binding in the governed scenario replay.

The structural overlay caps the fitted GDP factor in two cases: an identity GDP
input must produce an identity factor, and a positive activity response to
lower GDP is capped at identity. Both are governance overlays on a fitted
model, not re-estimation, so the question that matters is whether they are
merely precautionary or doing substantial work.

This script answers that by listing every binding with its raw factor, guarded
factor, clip amount, reason, forecast delta and revenue-equivalent impact, and
by applying the governed acceptance rules:

* **Base** - no binding should be possible. Base is the reference the overlay
  is built from; a binding there means the reference itself was clipped.
* **Low** - zero unexpected bindings. Any Low binding needs an economic
  explanation before closure.
* **Medium / High** - bindings may be retained as governed protection, but
  repeated or material clipping must be disclosed and quantified.

Usage::

    .\\.venv\\Scripts\\python.exe scripts\\audit_gdp_sign_guard_bindings.py
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

from model_dashboard.conflict_fuel_paths import (  # noqa: E402
    BASE_SCENARIO_ID,
    CONFLICT_FUEL_SCENARIO_LEVELS,
)
from model_dashboard.fuel_price_scenario import (  # noqa: E402
    run_fuel_price_scenario_replay,
)

# Same documented basis as the long-horizon evidence: a percentage activity
# change is applied to governed FY2025 revenue for the stream it drives.
REVENUE_REFERENCE_FY = 2025
REVENUE_REFERENCE_SERIES = {
    "PED": "net_fed_revenue",
    "LIGHT_RUC": "light_ruc_net_revenue",
    "HEAVY_RUC": "heavy_ruc_net_revenue",
}
REVENUE_EQUIVALENT_BASIS = (
    "guard-induced percentage change in stream activity applied to governed "
    f"FY{REVENUE_REFERENCE_FY} revenue for that stream; indicative materiality "
    "scale, not a revenue forecast"
)
MATERIAL_CLIP_PCT = 0.5


def _severity_of(scenario_name: str) -> str:
    text = str(scenario_name)
    if text == BASE_SCENARIO_ID or text.startswith(f"{BASE_SCENARIO_ID}_"):
        return "base"
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        if text.startswith(f"middle_east_{level}"):
            return level
    return "unknown"


def _reference_revenue() -> dict[str, float]:
    rows = pd.read_parquet(
        REPO_ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.parquet"
    )
    rows = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(REVENUE_REFERENCE_FY)
        & rows["scenario_name"].astype(str).eq("current_basecase")
    ]
    out: dict[str, float] = {}
    for stream, series_id in REVENUE_REFERENCE_SERIES.items():
        values = (
            pd.to_numeric(
                rows.loc[rows["series_id"].astype(str).eq(series_id), "value"],
                errors="coerce",
            )
            .dropna()
            .unique()
        )
        if len(values) != 1:
            raise ValueError(
                f"Reference revenue for {stream} is not a single FY"
                f"{REVENUE_REFERENCE_FY} value: {list(values)}."
            )
        out[stream] = float(values[0])
    return out


def build_guard_binding_table(replay: Any) -> pd.DataFrame:
    """One row per scenario/stream/quarter where a GDP sign guard bound."""

    forecasts = replay.future_forecasts
    if forecasts is None or forecasts.empty:
        return pd.DataFrame()
    applied = forecasts["demand_gdp_sign_guard_applied"].fillna(False).astype(bool)
    bound = forecasts.loc[applied].copy()
    if bound.empty:
        return pd.DataFrame()

    reference_revenue = _reference_revenue()
    reference = pd.to_numeric(bound["demand_reference_forecast"], errors="coerce")
    ratio = pd.to_numeric(bound["demand_price_ratio"], errors="coerce")
    elasticity = pd.to_numeric(bound["demand_elasticity"], errors="coerce")
    price_response = pd.Series(
        np.power(ratio.to_numpy(dtype=float), elasticity.to_numpy(dtype=float)),
        index=bound.index,
    )
    raw_factor = pd.to_numeric(bound["demand_gdp_model_factor_raw"], errors="coerce")
    guarded_factor = pd.to_numeric(bound["demand_gdp_model_factor"], errors="coerce")
    guarded_forecast = pd.to_numeric(bound["forecast"], errors="coerce")
    unguarded_forecast = reference * price_response * raw_factor
    forecast_delta = guarded_forecast - unguarded_forecast
    forecast_delta_pct = np.where(
        unguarded_forecast.abs().gt(0.0),
        forecast_delta / unguarded_forecast * 100.0,
        np.nan,
    )
    stream = bound["stream"].astype(str)

    out = pd.DataFrame(
        {
            "scenario_name": bound["scenario_name"].astype(str).to_numpy(),
            "severity": bound["scenario_name"].astype(str).map(_severity_of).to_numpy(),
            "stream": stream.to_numpy(),
            "quarter": bound["target_period"].astype(str).to_numpy(),
            "raw_gdp_model_factor": raw_factor.to_numpy(dtype=float),
            "guarded_gdp_model_factor": guarded_factor.to_numpy(dtype=float),
            "clip_amount": pd.to_numeric(
                bound["demand_gdp_guard_clip_amount"], errors="coerce"
            ).to_numpy(dtype=float),
            "guard_reason": bound["demand_gdp_guard_reason"].astype(str).to_numpy(),
            "identity_guard": bound["demand_gdp_identity_guard_applied"]
            .fillna(False)
            .astype(bool)
            .to_numpy(),
            "downside_guard": bound["demand_gdp_downside_sign_guard_applied"]
            .fillna(False)
            .astype(bool)
            .to_numpy(),
            "unguarded_forecast": unguarded_forecast.to_numpy(dtype=float),
            "guarded_forecast": guarded_forecast.to_numpy(dtype=float),
            "forecast_delta": forecast_delta.to_numpy(dtype=float),
            "forecast_delta_pct": np.asarray(forecast_delta_pct, dtype=float),
        }
    )
    # Economic monotonicity: for a downside GDP input the guarded activity must
    # not exceed the same-price Base activity. The guard caps at identity, so
    # equality is the expected outcome and anything above it is a failure.
    base_at_same_price = reference * price_response
    out["input_gdp_level_factor"] = pd.to_numeric(
        bound["demand_gdp_input_level_factor"], errors="coerce"
    ).to_numpy(dtype=float)
    out["price_response_factor"] = price_response.to_numpy(dtype=float)
    out["base_reference_forecast"] = reference.to_numpy(dtype=float)
    out["base_at_same_price_forecast"] = base_at_same_price.to_numpy(dtype=float)
    out["gdp_factor_source_scenario"] = (
        bound["demand_gdp_factor_source_scenario_name"].astype(str).to_numpy()
        if "demand_gdp_factor_source_scenario_name" in bound.columns
        else ""
    )
    out["responding_model"] = stream.map(_finalist_model_by_stream()).to_numpy()
    tolerance = 1e-9 + 1e-12 * base_at_same_price.abs()
    out["monotonicity_holds"] = (
        guarded_forecast <= base_at_same_price + tolerance
    ).to_numpy()
    out["base_vs_scenario_direction"] = np.where(
        out["guarded_forecast"] < out["base_at_same_price_forecast"] - 1e-9,
        "scenario_below_base",
        np.where(
            out["guarded_forecast"] > out["base_at_same_price_forecast"] + 1e-9,
            "scenario_above_base",
            "scenario_equals_base_at_identity",
        ),
    )
    out["revenue_equivalent_delta_nzd_m"] = out.apply(
        lambda row: row["forecast_delta_pct"] / 100.0
        * reference_revenue.get(str(row["stream"]), float("nan")),
        axis=1,
    )
    out["revenue_equivalent_basis"] = REVENUE_EQUIVALENT_BASIS
    # The two guard types have different acceptance conditions.
    #
    # An identity guard restores a definition the scenario requires, so it may
    # legitimately clip in either direction - the raw factor can sit either side
    # of 1 - and is accepted when the guarded factor is exactly 1.
    #
    # A downside guard corrects a wrong-sign response, so it must clip DOWNWARD
    # and the guarded result must satisfy economic monotonicity. Anything else
    # stays unresolved rather than being quietly absorbed.
    identity_restored = out["identity_guard"] & np.isclose(
        out["guarded_gdp_model_factor"], 1.0, rtol=0.0, atol=1e-12
    )
    downside_accepted = (
        out["downside_guard"] & out["monotonicity_holds"] & (out["clip_amount"] <= 1e-15)
    )
    out["disposition"] = np.where(
        identity_restored,
        "accepted_definitional_restoration",
        np.where(downside_accepted, "accepted_expected_guard", "unresolved"),
    )
    return out.sort_values(
        ["severity", "scenario_name", "stream", "quarter"], kind="stable"
    ).reset_index(drop=True)


def _finalist_model_by_stream() -> dict[str, str]:
    import json

    out: dict[str, str] = {}
    for stream, directory in (
        ("PED", "ped_vnext"),
        ("LIGHT_RUC", "light_ruc_vnext"),
        ("HEAVY_RUC", "heavy_ruc_vnext"),
    ):
        path = (
            REPO_ROOT
            / "data"
            / "dashboard_evidence_pack_reproducibility"
            / directory
            / "fitted_model_manifest.json"
        )
        if path.exists():
            out[stream] = str(
                json.loads(path.read_text(encoding="utf-8")).get("finalist_model", "")
            )
    return out


def summarise_bindings(bindings: pd.DataFrame) -> pd.DataFrame:
    if bindings.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (severity, stream, reason), group in bindings.groupby(
        ["severity", "stream", "guard_reason"], dropna=False
    ):
        rows.append(
            {
                "severity": severity,
                "stream": stream,
                "guard_reason": reason,
                "n_bindings": int(len(group)),
                "first_quarter": group["quarter"].min(),
                "last_quarter": group["quarter"].max(),
                "max_abs_clip_amount": float(group["clip_amount"].abs().max()),
                "max_abs_forecast_delta_pct": float(
                    group["forecast_delta_pct"].abs().max()
                ),
                "cumulative_revenue_equivalent_nzd_m": float(
                    group["revenue_equivalent_delta_nzd_m"].sum()
                ),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["severity", "stream", "guard_reason"])
        .reset_index(drop=True)
    )


IDENTITY_GUARD_EXPLANATION = (
    "Definitional, not a model pathology. The scenario requires that where a "
    "quarter's GDP input equals Base, the GDP factor is exactly 1. The fitted "
    "replay carries recursive lag persistence from earlier stressed quarters, so "
    "its ratio drifts off 1 after the conflict path has already converged back "
    "to Base. The guard restores the identity the scenario definition demands."
)
DOWNSIDE_GUARD_EXPLANATION = (
    "Model pathology correction. A lower GDP input produced a HIGHER fitted "
    "activity factor - a wrong-sign out-of-distribution response. The guard caps "
    "it at no-change rather than reversing it, so the overlay never lets a "
    "downside scenario mechanically raise activity."
)


def evaluate_acceptance(bindings: pd.DataFrame) -> pd.DataFrame:
    """Apply the governed acceptance rules per severity.

    Identity and downside guards are judged separately because they mean
    different things: one enforces a definition the scenario requires, the
    other corrects a wrong-sign fitted response.
    """

    rows: list[dict[str, Any]] = []

    def subset(severity: str, *, downside: bool | None = None) -> pd.DataFrame:
        if bindings.empty:
            return bindings
        out = bindings[bindings["severity"].astype(str).eq(severity)]
        if downside is None or out.empty:
            return out
        return out[out["downside_guard"].astype(bool).eq(downside)]

    base = subset("base")
    rows.append(
        {
            "severity": "base",
            "guard_type": "any",
            "rule": "no binding should be possible",
            "n_bindings": int(len(base)),
            "max_abs_forecast_delta_pct": (
                0.0 if base.empty else float(base["forecast_delta_pct"].abs().max())
            ),
            "status": "passed" if base.empty else "failed",
            "detail": (
                "Base is the reference the overlay is built from; a binding "
                "there would mean the reference itself was clipped."
                if base.empty
                else "Base bindings present - the overlay reference was clipped."
            ),
        }
    )

    low_identity = subset("low", downside=False)
    rows.append(
        {
            "severity": "low",
            "guard_type": "identity",
            "rule": "explained or zero",
            "n_bindings": int(len(low_identity)),
            "max_abs_forecast_delta_pct": (
                0.0
                if low_identity.empty
                else float(low_identity["forecast_delta_pct"].abs().max())
            ),
            "status": "explained" if not low_identity.empty else "passed",
            "detail": IDENTITY_GUARD_EXPLANATION,
        }
    )
    low_downside = subset("low", downside=True)
    if low_downside.empty:
        low_status, low_detail = "passed", "No wrong-sign responses in the Low path."
    else:
        accepted = low_downside["disposition"].astype(str).eq("accepted_expected_guard")
        low_status = "accepted_expected_guard" if accepted.all() else "unresolved"
        low_detail = (
            f"{len(low_downside)} wrong-sign bindings inside the Low stress "
            f"window ({low_downside['quarter'].min()}-{low_downside['quarter'].max()}), "
            f"maximum impact {float(low_downside['forecast_delta_pct'].abs().max()):.4f}%, "
            f"cumulative revenue-equivalent "
            f"{float(low_downside['revenue_equivalent_delta_nzd_m'].sum()):.2f} $m. "
            f"{int(accepted.sum())}/{len(low_downside)} satisfy the economic "
            "monotonicity invariant after guarding. " + DOWNSIDE_GUARD_EXPLANATION
        )
    rows.append(
        {
            "severity": "low",
            "guard_type": "downside_sign",
            "rule": "zero unexpected bindings; each explicitly disposed",
            "n_bindings": int(len(low_downside)),
            "max_abs_forecast_delta_pct": (
                0.0
                if low_downside.empty
                else float(low_downside["forecast_delta_pct"].abs().max())
            ),
            "status": low_status,
            "detail": low_detail,
        }
    )

    for severity in ("medium", "high"):
        group = subset(severity)
        material = (
            group[group["forecast_delta_pct"].abs().ge(MATERIAL_CLIP_PCT)]
            if not group.empty
            else group
        )
        rows.append(
            {
                "severity": severity,
                "guard_type": "any",
                "rule": "retained as governed protection; disclose and quantify",
                "n_bindings": int(len(group)),
                "max_abs_forecast_delta_pct": (
                    0.0
                    if group.empty
                    else float(group["forecast_delta_pct"].abs().max())
                ),
                "status": "disclosed",
                "detail": (
                    "No bindings."
                    if group.empty
                    else (
                        f"{len(group)} bindings, of which "
                        f"{int(group['downside_guard'].astype(bool).sum())} are "
                        f"wrong-sign; {len(material)} move the forecast by at "
                        f"least {MATERIAL_CLIP_PCT}%; maximum "
                        f"{float(group['forecast_delta_pct'].abs().max()):.4f}%; "
                        "cumulative revenue-equivalent "
                        f"{float(group['revenue_equivalent_delta_nzd_m'].sum()):.1f} $m."
                    )
                ),
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return "_No rows._"
    formatted = frame.copy()
    for column in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda value: f"{value:.6g}")
        else:
            formatted[column] = formatted[column].astype(str)
    header = "| " + " | ".join(str(column) for column in formatted.columns) + " |"
    divider = "|" + "|".join("---" for _ in formatted.columns) + "|"
    body = [
        "| " + " | ".join(row) + " |"
        for row in formatted.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *body])


_DETAIL_COLUMNS = [
    "severity",
    "scenario_name",
    "stream",
    "quarter",
    "raw_gdp_model_factor",
    "guarded_gdp_model_factor",
    "clip_amount",
    "guard_reason",
    "forecast_delta",
    "forecast_delta_pct",
    "revenue_equivalent_delta_nzd_m",
    "disposition",
]
_LOW_DOWNSIDE_COLUMNS = [
    "scenario_name",
    "stream",
    "quarter",
    "responding_model",
    "input_gdp_level_factor",
    "price_response_factor",
    "raw_gdp_model_factor",
    "guarded_gdp_model_factor",
    "clip_amount",
    "base_at_same_price_forecast",
    "guarded_forecast",
    "base_vs_scenario_direction",
    "monotonicity_holds",
    "forecast_delta_pct",
    "revenue_equivalent_delta_nzd_m",
    "disposition",
]


def build_report(
    bindings: pd.DataFrame, summary: pd.DataFrame, acceptance: pd.DataFrame
) -> str:
    lines = [
        "# GDP sign-guard binding register",
        "",
        "Every quarter where the governed structural overlay clipped the fitted",
        "GDP factor. The guards are a governance overlay on a fitted model, not a",
        "re-estimation, so what matters is whether they are precautionary or",
        "doing substantial work.",
        "",
        "## Acceptance",
        "",
        _markdown_table(acceptance),
        "",
        "## Summary by severity, stream and reason",
        "",
        _markdown_table(summary),
        "",
        f"Total bindings: {0 if bindings.empty else len(bindings)}.",
        "",
        "## Low wrong-sign bindings, individually disposed",
        "",
        "These are the bindings that indicate the fitted model responding with the",
        "wrong sign, as distinct from the definitional identity restorations. Each",
        "is listed in full with its disposition.",
        "",
        _markdown_table(
            bindings[
                bindings["severity"].astype(str).eq("low")
                & bindings["downside_guard"].astype(bool)
            ][_LOW_DOWNSIDE_COLUMNS]
            if not bindings.empty
            else bindings
        ),
        "",
        "## Every binding",
        "",
        _markdown_table(
            bindings[_DETAIL_COLUMNS] if not bindings.empty else bindings
        ),
        "",
        "## The two guard types mean different things",
        "",
        "**`identity_gdp_input_forces_identity_factor`** - " + IDENTITY_GUARD_EXPLANATION,
        "",
        "**`positive_response_to_lower_gdp_capped_at_identity`** - "
        + DOWNSIDE_GUARD_EXPLANATION,
        "",
        "The identity guard binding often is therefore expected behaviour once a",
        "conflict path converges back to Base, and its frequency tracks how long",
        "the fitted lag structure carries persistence. The wrong-sign guard is the",
        "one that indicates the fitted model being used outside its estimation",
        "range, and it is the count worth watching.",
        "",
        "Revenue-equivalent figures use " + REVENUE_EQUIVALENT_BASIS + ".",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "gdp_sign_guard_audit",
    )
    parser.add_argument("--engine", default="ensemble")
    parser.add_argument(
        "--scenario-inputs",
        type=Path,
        default=REPO_ROOT
        / "data"
        / "current_revenue_outlook"
        / "scenario_inputs"
        / "scenario_input_wide.parquet",
    )
    args = parser.parse_args(argv)

    print("[guard-audit] running governed scenario replay ...", flush=True)
    replay = run_fuel_price_scenario_replay(
        pd.read_parquet(args.scenario_inputs),
        repo_root=REPO_ROOT,
        engine=args.engine,
    )
    bindings = build_guard_binding_table(replay)
    summary = summarise_bindings(bindings)
    acceptance = evaluate_acceptance(bindings)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bindings.to_csv(output_dir / "gdp_sign_guard_bindings.csv", index=False)
    summary.to_csv(output_dir / "gdp_sign_guard_summary.csv", index=False)
    acceptance.to_csv(output_dir / "gdp_sign_guard_acceptance.csv", index=False)
    (output_dir / "gdp_sign_guard_report.md").write_text(
        build_report(bindings, summary, acceptance), encoding="utf-8"
    )

    print()
    print(acceptance.to_string(index=False))
    print()
    if not summary.empty:
        print(summary.to_string(index=False))
    print()
    print(f"Written to {output_dir}")

    failed = acceptance[acceptance["status"].astype(str).eq("failed")]
    return 1 if not failed.empty else 0


if __name__ == "__main__":
    raise SystemExit(main())
