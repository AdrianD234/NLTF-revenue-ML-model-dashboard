"""Fleet mix explorer: MoT's six volume rows, side by side across sources.

The six rows are MBU26's own taxonomy (the model's class split works ON these,
so every comparison should come back TO these):

    light petrol VKT | light RUC (conventional) | light BEV RUC | PHEV RUC
    | heavy RUC (conventional) | heavy BEV RUC

Sources: the MBU26 official baseline (spine), the MoT VFM 202405 scenarios
(vendored extract, June-year averaged), and the committed dashboard pack
(AR(1) engine, base case). All volumes in million km.

The module also owns the "which denominator?" arithmetic: the same BEV
kilometres are 1.7% of all road travel, 1.8% of all light travel, and 6.1%
of the light RUC pool in FY2025 - three legitimate ratios that must never be
mixed silently.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# key, MBU26 spine series_id, display label, colour
SIX_ROWS = [
    ("light_petrol_vkt", "light_petrol_vkt", "Light petrol (pays fuel excise)", "#00843D"),
    ("light_ruc_net_km", "light_ruc_net_km", "Light RUC - conventional diesel", "#006FAD"),
    ("light_bev_ruc_net_km", "light_bev_ruc_net_km", "Light RUC - battery-electric", "#4CA7D8"),
    ("phev_ruc_net_km", "phev_ruc_net_km", "Light RUC - plug-in hybrid", "#9CCBE8"),
    ("heavy_ruc_net_km", "heavy_ruc_net_km", "Heavy RUC - conventional", "#102A43"),
    ("heavy_bev_ruc_net_km", "heavy_bev_ruc_net_km", "Heavy RUC - battery-electric", "#94A3B8"),
]
ROW_KEYS = [key for key, *_ in SIX_ROWS]
ROW_LABELS = {key: label for key, _, label, _ in SIX_ROWS}
ROW_COLORS = {key: colour for key, _, _, colour in SIX_ROWS}

DASHBOARD_SOURCE = "Dashboard pack (AR(1) engine, base case)"
VFM_SOURCES = {
    "VFM 202405 - Base scenario": "Base_EV",
    "VFM 202405 - Fast scenario": "Fast_EV",
    "VFM 202405 - Slow scenario": "Slow_EV",
}


def official_source_label(bridge_vintage_id: str) -> str:
    """MoT baseline option label for the bridge vintage actually in use.

    Generated rather than hard-coded so the visible label can never claim a
    vintage the underlying frame was not read from.
    """
    return f"{bridge_vintage_id} official (MoT baseline)"


def source_options(bridge_vintage_id: str) -> list[str]:
    return [official_source_label(bridge_vintage_id), *VFM_SOURCES.keys(), DASHBOARD_SOURCE]


def is_official_source(source: str, bridge_vintage_id: str) -> bool:
    return str(source) == official_source_label(bridge_vintage_id)

DENOMINATORS = {
    "All road travel (all six rows)": ROW_KEYS,
    "All light travel (incl. petrol)": ["light_petrol_vkt", "light_ruc_net_km",
                                        "light_bev_ruc_net_km", "phev_ruc_net_km"],
    "Light RUC pool (conventional + BEV + PHEV)": ["light_ruc_net_km", "light_bev_ruc_net_km",
                                                   "phev_ruc_net_km"],
}

METRIC_KM = "Million km (stacked)"
METRIC_SHARE = "Share of a chosen total"
METRIC_YOY = "Year-on-year change (%)"
METRIC_OPTIONS = [METRIC_KM, METRIC_SHARE, METRIC_YOY]


def _spine(repo_root: Path, bridge_vintage_id: str | None = None) -> pd.DataFrame:
    """Official annual rows of the bridge-assumption vintage in use.

    ``bridge_vintage_id`` must come from the loaded runtime pack's manifest so
    the explorer describes the same vintage that produced the pack. It falls
    back to the registry default only when no pack-specific bridge is given.
    """
    from .official_vintage import default_bridge_vintage_id, official_vintage_entry

    vid = str(bridge_vintage_id or default_bridge_vintage_id(repo_root))
    entry = official_vintage_entry(vid, repo_root)
    stems = entry.get("file_stems") or {}
    stem = str(stems.get("official_annual", "official_annual"))
    path = repo_root / str(entry["source_pack_path"]) / f"{stem}.csv"
    return pd.read_csv(path)


def load_official_frame(repo_root: Path, bridge_vintage_id: str | None = None) -> pd.DataFrame:
    return load_mbu26_frame(repo_root, bridge_vintage_id)


def load_mbu26_frame(repo_root: Path, bridge_vintage_id: str | None = None) -> pd.DataFrame:
    spine = _spine(repo_root, bridge_vintage_id)
    frame = (
        spine[spine["source_series_id"].isin(ROW_KEYS)]
        .pivot_table(index="FY", columns="source_series_id", values="value", aggfunc="first")
        .reindex(columns=ROW_KEYS)
    )
    # FY2001-02 lack the petrol row, which would silently distort any share
    # denominator; only years with all six rows are comparable. Clip to the
    # published FY2050 horizon shared by every other source.
    frame = frame.dropna(how="any")
    return frame.loc[frame.index <= 2050].astype(float)


def load_vfm_frame(repo_root: Path, scenario: str) -> pd.DataFrame:
    shares = pd.read_csv(repo_root / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
    block = shares[shares["scenario"] == scenario].set_index("june_year")
    frame = pd.DataFrame({
        "light_petrol_vkt": block["light_petrol_vkt_million_km"],
        "light_ruc_net_km": block["light_ruc_conventional_million_km"],
        "light_bev_ruc_net_km": block["light_ruc_bev_million_km"],
        "phev_ruc_net_km": block["light_ruc_phev_million_km"],
        "heavy_ruc_net_km": block["heavy_total_million_km"] - block["heavy_bev_million_km"],
        "heavy_bev_ruc_net_km": block["heavy_bev_million_km"],
    })
    frame.index.name = "FY"
    return frame.astype(float)


def load_dashboard_frame(repo_root: Path, bridge_vintage_id: str | None = None) -> pd.DataFrame:
    """Default dashboard Base path after its governed macro and VFM overlays.

    This deliberately uses the same pipeline as Revenue Outlook: select the
    raw PED bridge first, apply the Treasury BEFU26 baseline macro replay,
    then apply the default MoT VFM Base retention and class-mix overlay.
    Petrol VKT therefore reconciles to the macro-adjusted PED litres at the
    governed litres/100 km intensity instead of falling back to the optimized
    migration series carried in the underlying replay pack.
    """
    from model_dashboard.engine import engine_revenue_outlook_dir
    from model_dashboard.ev_uptake_levers import (
        DEFAULT_EV_UPTAKE_MODE,
        EV_UPTAKE_PRESETS,
        apply_uptake_levers_to_chart_rows,
    )
    from model_dashboard.fuel_price_scenario import (
        apply_treasury_macro_to_chart_rows,
        run_direct_treasury_scenario_replay,
    )
    from model_dashboard.revenue_outlook import (
        PED_BRIDGE_DEFAULT_MODE,
        apply_ped_bridge_mode_layer,
        load_revenue_outlook_pack,
    )

    pack_dir = repo_root / engine_revenue_outlook_dir("ar1")
    pack = load_revenue_outlook_pack(pack_dir, repo_root=repo_root)
    if pack is None:
        raise FileNotFoundError(f"Revenue Outlook pack is unavailable: {pack_dir}")
    bridge = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        include_derived_frames=False,
        include_selected_ped_audit=False,
    )
    scenario_input_path = (
        pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    )
    if not scenario_input_path.exists():
        raise FileNotFoundError(
            "Treasury macro replay inputs are unavailable for the dashboard "
            f"fleet-mix path: {scenario_input_path}"
        )
    # P1.2: per-scenario factors, so the comparison never borrows Base's.
    macro_replay = run_direct_treasury_scenario_replay(
        pd.read_parquet(scenario_input_path),
        repo_root=repo_root,
        engine="ar1",
    )
    bridge_rows, _ = apply_treasury_macro_to_chart_rows(
        bridge["chart_rows"],
        macro_replay,
    )
    rows, _ = apply_uptake_levers_to_chart_rows(
        bridge_rows,
        pack.ev_phev_ped_light_drift_assumptions,
        EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE],
        adjust_ped=True,
    )

    def annual_values(frame: pd.DataFrame, key: str) -> dict[int, float]:
        annual = frame[
            frame["time_grain"].astype(str).eq("june_year")
            & frame["scenario_role"].astype(str).eq("basecase")
            & frame["row_type"].astype(str).eq("future_forecast")
            & frame["series_id"].astype(str).eq(key)
        ].copy()
        return {
            int(fy): float(value)
            for fy, value in zip(
                pd.to_numeric(annual["june_year"], errors="coerce"),
                pd.to_numeric(annual["value"], errors="coerce"),
                strict=False,
            )
            if pd.notna(fy) and pd.notna(value)
        }

    packed = {
        key: annual_values(rows, key)
        for key in (
            "light_petrol_vkt",
            "light_ruc_net_km",
            "light_bev_ruc_net_km",
            "phev_ruc_net_km",
            "heavy_ruc_net_km",
        )
    }
    heavy_before_uptake = annual_values(bridge_rows, "heavy_ruc_net_km")
    common_years = [set(values) for values in packed.values()]
    common_years.append(set(heavy_before_uptake))
    fys = sorted(set.intersection(*common_years)) if common_years else []
    if not fys:
        raise ValueError("The dashboard fleet-mix bridge has no complete forecast years.")

    frame = pd.DataFrame(index=pd.Index(fys, name="FY"))
    for key in (
        "light_petrol_vkt",
        "light_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "heavy_ruc_net_km",
    ):
        frame[key] = [packed[key][fy] for fy in fys]
    frame["heavy_bev_ruc_net_km"] = [
        max(float(heavy_before_uptake[fy]) - float(packed["heavy_ruc_net_km"][fy]), 0.0)
        for fy in fys
    ]
    # The governed PED bridge begins in FY2026. Retain the common FY2025
    # actual anchor used by the pack and by MBU26 so the explorer still spans
    # the full actual-to-forecast junction.
    if 2025 not in frame.index:
        actual_anchor = load_mbu26_frame(repo_root, bridge_vintage_id).loc[[2025], ROW_KEYS]
        frame = pd.concat([actual_anchor, frame], axis=0).sort_index()
    return frame[ROW_KEYS].astype(float)


def load_source_frame(
    repo_root: Path, source: str, bridge_vintage_id: str | None = None
) -> pd.DataFrame:
    from .official_vintage import default_bridge_vintage_id

    vid = str(bridge_vintage_id or default_bridge_vintage_id(repo_root))
    if is_official_source(source, vid):
        return load_mbu26_frame(repo_root, vid)
    if source == DASHBOARD_SOURCE:
        return load_dashboard_frame(repo_root, vid)
    return load_vfm_frame(repo_root, VFM_SOURCES[source])


def share_frame(frame: pd.DataFrame, denominator: str) -> pd.DataFrame:
    keys = DENOMINATORS[denominator]
    denom = frame[keys].sum(axis=1)
    return frame[keys].div(denom, axis=0)


def yoy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.pct_change() * 100.0


def denominator_example(
    repo_root: Path, fy: int = 2025, bridge_vintage_id: str | None = None
) -> dict[str, float]:
    """The FY2025 predicament, computed live: same BEV km, three ratios."""
    row = load_mbu26_frame(repo_root, bridge_vintage_id).loc[fy]
    bev_all = row["light_bev_ruc_net_km"] + row["heavy_bev_ruc_net_km"]
    total = row[ROW_KEYS].sum()
    light_all = row[DENOMINATORS["All light travel (incl. petrol)"]].sum()
    pool = row[DENOMINATORS["Light RUC pool (conventional + BEV + PHEV)"]].sum()
    return {
        "fy": fy,
        "bev_km": float(bev_all),
        "light_bev_km": float(row["light_bev_ruc_net_km"]),
        "total_km": float(total),
        "light_all_km": float(light_all),
        "pool_km": float(pool),
        "share_all": float(bev_all / total),
        "share_light": float(row["light_bev_ruc_net_km"] / light_all),
        "share_pool": float(row["light_bev_ruc_net_km"] / pool),
    }


def definitions_table() -> pd.DataFrame:
    """The six MBU26 rows mapped to VFM and dashboard terms."""
    rows = [
        ("Light petrol VKT", "MBU26 row 16", "Petrol + petrol-hybrid cars and vans (pay fuel excise, not RUC)",
         "'Petrol' + 'Hybrid petrol' VKT for LPV+LCV",
         "light_petrol_vkt (selected raw PED bridge x MoT VFM Base petrol-retention curve)"),
        ("Light RUC net km", "MBU26 row 10", "Conventional light RUC vehicles - diesel and diesel-hybrid ONLY; "
         "BEV and PHEV are separate rows", "'Diesel' + 'Hybrid diesel' VKT for LPV+LCV", "light_ruc_net_km"),
        ("Light BEV RUC net km", "MBU26 row 12", "Battery-electric cars and vans (pay light RUC)",
         "'Electric' VKT for LPV+LCV", "light_bev_ruc_net_km"),
        ("PHEV RUC net km", "MBU26 row 14", "Plug-in hybrids (pay a reduced RUC rate)",
         "'Petrol plug-in' VKT for LPV+LCV", "phev_ruc_net_km"),
        ("Heavy RUC net km", "MBU26 row 11", "Trucks and buses on conventional power",
         "M Truck + H Truck VKT less electric", "heavy_ruc_net_km"),
        ("Heavy BEV RUC net km", "MBU26 row 13", "Electric trucks (same per-km RUC as conventional heavy, "
         "so electrification is revenue-neutral in the heavy block)", "'Electric' M+H Truck VKT",
         "heavy_bev_ruc_net_km (MBU26 carries 0 across the horizon)"),
    ]
    return pd.DataFrame(rows, columns=["MBU26 row", "Source row", "What it contains",
                                       "VFM 202405 equivalent", "Dashboard series"])
