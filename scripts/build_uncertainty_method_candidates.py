"""Gate B (revised): H21+ continuation candidates and the series-tier contract.

Consumes the horizon shape estimated by
``scripts/build_uncertainty_method_evidence.py`` and answers the two questions
the owner has to decide:

  1. what happens beyond the evidence (FY2031-FY2050);
  2. which series get direct evidence, which derive it, and which need a proxy.

Horizon mapping. The last complete actual June year is FY2025, and the
long-horizon pack runs to quarter H20, i.e. five June years. So:

    FY2026  June-year H1   quarters H1-H4    backtest-supported
    FY2027  June-year H2   quarters H5-H8    backtest-supported
    FY2028  June-year H3   quarters H9-H12   backtest-supported
    FY2029  June-year H4   quarters H13-H16  extended conditional
    FY2030  June-year H5   quarters H17-H20  extended conditional
    FY2031+                quarters H21+     inferred, no evaluation evidence

The evidence reaches EXACTLY to FY2030, which is also where the empirical fan
already stops. FY2031-FY2050 is genuinely inferred, and the candidates below
differ only there.

    .venv\\Scripts\\python.exe scripts\\build_uncertainty_method_candidates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402

OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
LAST_ACTUAL_FY = 2025
QUARTERS_PER_YEAR = 4
LAST_SUPPORTED_QUARTER_HORIZON = 20
LAST_SUPPORTED_FY = LAST_ACTUAL_FY + LAST_SUPPORTED_QUARTER_HORIZON // QUARTERS_PER_YEAR  # FY2030
REPORT_FYS = (2027, 2030, 2031, 2040, 2050)
EXAMPLE_FYS = tuple(range(2026, 2051))

# The legacy comparator: the pooled H1-H3 annual constant the first Gate B pass
# anchored on, kept so the owner can see what the current fan implies.
LEGACY_POOLED_H1_H3_WIDTH80 = {"PED": 4.4471, "LIGHT_RUC": 4.5527, "HEAVY_RUC": 4.9383}

# Which model stream carries the direct evidence for each chartable series, and
# how the series is reached from it.
SERIES_CONTRACT = (
    # series_id, display, kind, tier, parent stream, derivation
    ("ped_vkt_per_capita", "PED VKT per capita", "activity", 1, "PED",
     "direct rolling-origin evidence for the PED finalist"),
    ("ped_volume", "PED volume", "activity", 3, "PED",
     "uncertain PED activity through the governed PED bridge"),
    ("light_ruc_net_km", "Light RUC net km", "activity", 1, "LIGHT_RUC",
     "direct rolling-origin evidence for the Light RUC finalist (the pool)"),
    ("light_bev_ruc_net_km", "Light BEV RUC net km", "activity", 3, "LIGHT_RUC",
     "uncertain Light pool x selected exact VFM BEV share"),
    ("phev_ruc_net_km", "PHEV RUC net km", "activity", 3, "LIGHT_RUC",
     "uncertain Light pool x selected exact VFM PHEV share"),
    ("heavy_ruc_net_km", "Heavy RUC net km", "activity", 1, "HEAVY_RUC",
     "direct rolling-origin evidence for the Heavy RUC finalist"),
    ("heavy_bev_ruc_net_km", "Heavy BEV RUC net km", "activity", 5, "",
     "fixed MBU26 component under HEAVY_RUC: not_reclassified; no direct evidence"),
    ("gross_ped_revenue", "PED revenue", "revenue", 3, "PED",
     "uncertain PED volume x governed FED rate"),
    ("gross_fed_revenue", "Gross FED revenue", "revenue", 3, "PED",
     "FORMULA_DEFINITIONS from uncertain PED/LPG/CNG leaves"),
    ("net_fed_revenue", "Net FED revenue", "revenue", 3, "PED",
     "FORMULA_DEFINITIONS: gross_fed_revenue - fed_refunds"),
    ("light_ruc_net_revenue", "Light RUC revenue", "revenue", 3, "LIGHT_RUC",
     "uncertain conventional Light km x governed class rate"),
    ("light_bev_ruc_net_revenue", "Light BEV RUC net revenue", "revenue", 3, "LIGHT_RUC",
     "uncertain Light BEV km x governed class rate"),
    ("phev_ruc_net_revenue", "PHEV RUC net revenue", "revenue", 3, "LIGHT_RUC",
     "uncertain PHEV km x governed class rate"),
    ("heavy_ruc_net_revenue", "Heavy RUC revenue", "revenue", 3, "HEAVY_RUC",
     "uncertain Heavy km x governed class rate"),
    ("heavy_bev_ruc_net_revenue", "Heavy BEV RUC net revenue", "revenue", 5, "",
     "fixed MBU26 component; inherits the Heavy BEV km proxy"),
    ("total_ruc_net_revenue", "Total RUC all classes", "revenue", 3, "",
     "FORMULA_DEFINITIONS draw-level rollup of every RUC class"),
    ("total_fed_ruc_net_revenue", "Total RUC+PED revenue", "revenue", 3, "",
     "FORMULA_DEFINITIONS: net_fed_revenue + total_ruc_net_revenue"),
    ("total_nltf_net_revenue", "Total NLTF revenue", "revenue", 3, "",
     "FORMULA_DEFINITIONS draw-level rollup of every stream"),
    ("net_mvr_revenue", "Net MVR revenue", "revenue", 5, "",
     "no committed out-of-sample evidence; governed conservative proxy required"),
    ("tuc_net_revenue", "TUC net revenue", "revenue", 5, "",
     "no committed out-of-sample evidence; governed conservative proxy required"),
)


def quarter_horizon_for_fy(fy: int) -> int:
    """The last quarter horizon inside that June year."""
    return (int(fy) - LAST_ACTUAL_FY) * QUARTERS_PER_YEAR


def continuation_widths(shape: pd.DataFrame, stream: str, level: str) -> dict[str, dict[int, float]]:
    """Relative width by FY for every H21+ candidate, per stream and level."""
    cell = shape[shape["stream"].eq(stream) & shape["level"].eq(level)].sort_values("horizon")
    if cell.empty:
        return {}
    smoothed = dict(zip(cell["horizon"].astype(int), cell["B_isotonic_width_pct"]))
    saturating = dict(zip(cell["horizon"].astype(int), cell["D_saturating_width_pct"]))
    w20 = float(smoothed[LAST_SUPPORTED_QUARTER_HORIZON])

    fit = FITS[(stream, level)]
    out = {name: {} for name in ("plateau", "saturating", "sqrt_stress", "legacy_constant")}
    for fy in EXAMPLE_FYS:
        horizon = quarter_horizon_for_fy(fy)
        if horizon <= LAST_SUPPORTED_QUARTER_HORIZON:
            # Inside the evidence every candidate is the same smoothed curve.
            supported = float(smoothed[horizon])
            for name in out:
                out[name][fy] = supported
            out["legacy_constant"][fy] = LEGACY_POOLED_H1_H3_WIDTH80.get(stream, np.nan) * (
                1.0 if level == "80" else 0.55
            )
            continue
        out["plateau"][fy] = w20
        out["saturating"][fy] = (
            float(fit["w_inf_pct"] - (fit["w_inf_pct"] - fit["w1_pct"]) * np.exp(-fit["k"] * (horizon - 1)))
            if bool(fit.get("fit_ok"))
            else np.nan
        )
        out["sqrt_stress"][fy] = w20 * float(np.sqrt(horizon / LAST_SUPPORTED_QUARTER_HORIZON))
        out["legacy_constant"][fy] = LEGACY_POOLED_H1_H3_WIDTH80.get(stream, np.nan) * (
            1.0 if level == "80" else 0.55
        )
    return out


def central_values() -> pd.DataFrame:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    block = pack.manifest.get("official_vintages", {})
    key = RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id=str(block.get("default_comparator_vintage_id") or "BEFU26"),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )
    rows, *_ = app.cached_scenario_overlay_rows(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        key,
        pack,
    )
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq("basecase")
    ].copy()
    selected["FY"] = pd.to_numeric(selected["june_year"], errors="coerce")
    selected["central"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "central"])
    return (
        selected.groupby(["series_id", "FY"], as_index=False)["central"]
        .first()
        .astype({"FY": int})
    )


FITS: dict[tuple[str, str], dict] = {}


def main() -> None:
    global FITS
    shape = pd.read_csv(OUT / "horizon_shape_candidates.csv")
    fit_frame = pd.read_csv(OUT / "saturating_fit_parameters.csv")
    # level round-trips through CSV as an int; the lookups key on text.
    shape["level"] = shape["level"].astype(str)
    fit_frame["level"] = fit_frame["level"].astype(str)
    FITS = {
        (str(row["stream"]), str(row["level"])): row.to_dict()
        for _index, row in fit_frame.iterrows()
    }

    # ------------------------------------------------- candidate width table
    candidate_rows: list[dict] = []
    for stream in sorted(shape["stream"].unique()):
        for level in ("50", "80"):
            widths = continuation_widths(shape, stream, level)
            if not widths:
                continue
            for candidate, by_fy in widths.items():
                for fy, width in by_fy.items():
                    horizon = quarter_horizon_for_fy(fy)
                    candidate_rows.append(
                        {
                            "stream": stream,
                            "level": level,
                            "candidate": candidate,
                            "FY": fy,
                            "quarter_horizon": horizon,
                            "evidence_state": (
                                "backtest_supported"
                                if horizon <= 12
                                else "extended_conditional"
                                if horizon <= LAST_SUPPORTED_QUARTER_HORIZON
                                else "inferred_long_run"
                            ),
                            "relative_width_pct": width,
                        }
                    )
    candidates = pd.DataFrame(candidate_rows)
    candidates.to_csv(OUT / "long_run_method_candidates.csv", index=False)

    # ------------------------------------------------------- example bands
    central = central_values()
    contract = pd.DataFrame(
        SERIES_CONTRACT,
        columns=["series_id", "display_name", "kind", "tier", "parent_stream", "derivation"],
    )
    example_rows: list[dict] = []
    for _index, series in contract.iterrows():
        stream = str(series["parent_stream"])
        if not stream:
            continue
        for level in ("50", "80"):
            widths = continuation_widths(shape, stream, level)
            if not widths:
                continue
            for candidate, by_fy in widths.items():
                for fy in REPORT_FYS:
                    width = by_fy.get(fy)
                    match = central[
                        central["series_id"].eq(series["series_id"]) & central["FY"].eq(fy)
                    ]
                    if width is None or match.empty:
                        continue
                    value = float(match["central"].iloc[0])
                    half = value * (width / 100.0) / 2.0
                    example_rows.append(
                        {
                            "series_id": series["series_id"],
                            "display_name": series["display_name"],
                            "tier": int(series["tier"]),
                            "parent_stream": stream,
                            "level": level,
                            "candidate": candidate,
                            "FY": fy,
                            "central": value,
                            "relative_width_pct": width,
                            "lower": value - half,
                            "upper": value + half,
                        }
                    )
    # ------------------------------------------- indicative aggregate bands
    # A real aggregate band needs draw-level propagation with cross-stream
    # dependence, which is deliberately NOT built at this gate. What can be
    # shown now is the BRACKET the simulation must land inside: independence
    # (quadrature) at one end, perfect correlation (linear) at the other.
    # MVR and TUC carry no width yet, so both ends understate.
    aggregate_parts = {
        "total_ruc_net_revenue": (
            ("light_ruc_net_revenue", "LIGHT_RUC"),
            ("light_bev_ruc_net_revenue", "LIGHT_RUC"),
            ("phev_ruc_net_revenue", "LIGHT_RUC"),
            ("heavy_ruc_net_revenue", "HEAVY_RUC"),
        ),
        "total_fed_ruc_net_revenue": (
            ("net_fed_revenue", "PED"),
            ("light_ruc_net_revenue", "LIGHT_RUC"),
            ("light_bev_ruc_net_revenue", "LIGHT_RUC"),
            ("phev_ruc_net_revenue", "LIGHT_RUC"),
            ("heavy_ruc_net_revenue", "HEAVY_RUC"),
        ),
        "total_nltf_net_revenue": (
            ("net_fed_revenue", "PED"),
            ("light_ruc_net_revenue", "LIGHT_RUC"),
            ("light_bev_ruc_net_revenue", "LIGHT_RUC"),
            ("phev_ruc_net_revenue", "LIGHT_RUC"),
            ("heavy_ruc_net_revenue", "HEAVY_RUC"),
        ),
    }
    for aggregate, parts in aggregate_parts.items():
        for level in ("50", "80"):
            for candidate in ("plateau", "saturating", "sqrt_stress", "legacy_constant"):
                for fy in REPORT_FYS:
                    total = central[
                        central["series_id"].eq(aggregate) & central["FY"].eq(fy)
                    ]
                    if total.empty:
                        continue
                    total_value = float(total["central"].iloc[0])
                    halves: list[float] = []
                    for part_id, stream in parts:
                        widths = continuation_widths(shape, stream, level)
                        width = widths.get(candidate, {}).get(fy)
                        match = central[
                            central["series_id"].eq(part_id) & central["FY"].eq(fy)
                        ]
                        if width is None or match.empty:
                            continue
                        halves.append(float(match["central"].iloc[0]) * (width / 100.0) / 2.0)
                    if not halves:
                        continue
                    independent = float(np.sqrt(np.sum(np.square(halves))))
                    comonotonic = float(np.sum(halves))
                    for basis, half in (
                        ("indicative_independent", independent),
                        ("indicative_comonotonic", comonotonic),
                    ):
                        example_rows.append(
                            {
                                "series_id": aggregate,
                                "display_name": f"{aggregate} ({basis})",
                                "tier": 3,
                                "parent_stream": basis,
                                "level": level,
                                "candidate": candidate,
                                "FY": fy,
                                "central": total_value,
                                "relative_width_pct": 100.0 * 2.0 * half / total_value,
                                "lower": total_value - half,
                                "upper": total_value + half,
                            }
                        )

    examples = pd.DataFrame(example_rows)
    examples.to_csv(OUT / "uncertainty_design_examples.csv", index=False)

    # -------------------------------------------------- series-tier contract
    contract["direct_evidence_source"] = contract["parent_stream"].map(
        lambda stream: "long_horizon_predictions.csv (H1-H20 rolling origin)" if stream else ""
    )
    contract["empirical_horizon_quarters"] = contract["parent_stream"].map(
        lambda stream: LAST_SUPPORTED_QUARTER_HORIZON if stream else 0
    )
    contract["supported_to_fy"] = contract["parent_stream"].map(
        lambda stream: LAST_SUPPORTED_FY if stream else None
    )
    contract["proxy_flag"] = contract["tier"].ge(4)
    contract["probabilistic"] = True
    contract["limitation"] = contract.apply(
        lambda row: (
            "No committed out-of-sample evidence; needs an explicit governed proxy."
            if row["tier"] >= 4
            else "Actual-driver evidence: isolates model degradation, understates driver-forecast error."
            if row["tier"] == 1
            else "Derived by draw-level propagation through the governed identity from an uncertain parent."
        ),
        axis=1,
    )
    contract.to_csv(OUT / "uncertainty_series_contract_draft.csv", index=False)

    # ------------------------------------------------------------- reporting
    print("=== H21+ candidate 80% relative widths, by FY ===")
    view = candidates[candidates["level"].eq("80") & candidates["FY"].isin(REPORT_FYS)]
    print(
        view.pivot_table(
            index=["stream", "candidate"], columns="FY", values="relative_width_pct"
        )
        .round(2)
        .to_string()
    )
    print("\n=== tier counts ===")
    print(contract.groupby("tier").size().to_string())
    print("\n=== example Total NLTF revenue 80% band ===")
    total = examples[
        examples["series_id"].eq("total_nltf_net_revenue") & examples["level"].eq("80")
    ]
    print(
        total.pivot_table(index="candidate", columns="FY", values="relative_width_pct")
        .round(2)
        .to_string()
    )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
