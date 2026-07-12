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

MBU26_SOURCE = "MBU26 official (MoT baseline)"
DASHBOARD_SOURCE = "Dashboard pack (AR(1) engine, base case)"
VFM_SOURCES = {
    "VFM 202405 - Base scenario": "Base_EV",
    "VFM 202405 - Fast scenario": "Fast_EV",
    "VFM 202405 - Slow scenario": "Slow_EV",
}
SOURCE_OPTIONS = [MBU26_SOURCE, *VFM_SOURCES.keys(), DASHBOARD_SOURCE]

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


def _spine(repo_root: Path) -> pd.DataFrame:
    path = repo_root / "data" / "revenue_model_source_pack" / "mbu26_annual_spine" / "mbu26_official_annual.csv"
    return pd.read_csv(path)


def load_mbu26_frame(repo_root: Path) -> pd.DataFrame:
    spine = _spine(repo_root)
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


def load_dashboard_frame(repo_root: Path) -> pd.DataFrame:
    """Committed AR(1) pack, base case. Petrol comes from the pack's own
    migration audit (the post-allocation petrol pool); heavy BEV is the
    MBU26-fixed line the pack carries verbatim."""
    from model_dashboard.engine import engine_revenue_outlook_dir

    pack_dir = repo_root / engine_revenue_outlook_dir("ar1")
    rows = pd.read_csv(pack_dir / "revenue_chart_rows.csv")
    annual = rows[(rows["time_grain"] == "june_year") & (rows["scenario_role"] == "basecase")
                  & (rows["row_type"] == "future_forecast")]
    packed = {}
    for key in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km", "heavy_ruc_net_km"]:
        g = annual[annual["series_id"] == key]
        packed[key] = {int(str(p).replace("FY", "")[:4]): float(v)
                       for p, v in zip(g["period"], g["value"], strict=False)}
    drift = pd.read_csv(pack_dir / "ev_phev_ped_light_drift_assumptions.csv")
    opt = drift[(drift["lambda_mode"] == "optimized") & (drift["scenario_role"] == "basecase")]
    petrol = dict(zip(opt["FY"].astype(int), opt["current_PED_light_petrol_km"].astype(float), strict=False))

    mbu = load_mbu26_frame(repo_root)["heavy_bev_ruc_net_km"]
    fys = sorted(set(packed["light_ruc_net_km"]) & set(petrol))
    frame = pd.DataFrame(index=pd.Index(fys, name="FY"))
    frame["light_petrol_vkt"] = [petrol[fy] for fy in fys]
    for key in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km", "heavy_ruc_net_km"]:
        frame[key] = [packed[key].get(fy) for fy in fys]
    frame["heavy_bev_ruc_net_km"] = [float(mbu.get(fy, 0.0)) for fy in fys]
    return frame[ROW_KEYS].astype(float)


def load_source_frame(repo_root: Path, source: str) -> pd.DataFrame:
    if source == MBU26_SOURCE:
        return load_mbu26_frame(repo_root)
    if source == DASHBOARD_SOURCE:
        return load_dashboard_frame(repo_root)
    return load_vfm_frame(repo_root, VFM_SOURCES[source])


def share_frame(frame: pd.DataFrame, denominator: str) -> pd.DataFrame:
    keys = DENOMINATORS[denominator]
    denom = frame[keys].sum(axis=1)
    return frame[keys].div(denom, axis=0)


def yoy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.pct_change() * 100.0


def denominator_example(repo_root: Path, fy: int = 2025) -> dict[str, float]:
    """The FY2025 predicament, computed live: same BEV km, three ratios."""
    row = load_mbu26_frame(repo_root).loc[fy]
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
         "'Petrol' + 'Hybrid petrol' VKT for LPV+LCV", "light_petrol_vkt (from PED VKT/capita x population)"),
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
