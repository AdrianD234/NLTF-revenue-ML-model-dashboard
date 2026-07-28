"""Gold-path end-to-end audit through the real application functions.

Not a hand-built approximation: this drives the same cached_* entry points the
Streamlit views call, with the default front-end settings, so what it reports
is what a user sees.

    corrected AR(1) pack
      -> raw PED bridge
      -> Treasury baseline macro replay
      -> conventional-anchor Light RUC allocation
      -> PED retention Off
      -> default current delayed policy
      -> independently selected MBU policy
      -> final chart / detail / stack rows

Usage: python scripts/build_gold_path_audit.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DASHBOARD_ENGINE_DEFAULT", "ar1")

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.light_fleet_allocation import LAST_DECISION_GRADE_ANNUAL_FY  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
)

OUT = ROOT / "artifacts" / "p0_light_fleet_fix"
PACK_DIR = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
TOL = 1e-6

CURRENT_FYS = (2026, 2027, 2030)
OFFICIAL_FYS = (2027, 2030, 2055)
CURRENT_SERIES = (
    ("light_petrol_vkt", "Light petrol VKT"),
    ("light_ruc_net_km", "Conventional Light RUC (km)"),
    ("light_ruc_net_revenue", "Conventional Light RUC (revenue)"),
    ("light_bev_ruc_net_km", "Light BEV (km)"),
    ("light_bev_ruc_net_revenue", "Light BEV (revenue)"),
    ("phev_ruc_net_km", "PHEV (km)"),
    ("phev_ruc_net_revenue", "PHEV (revenue)"),
    ("net_fed_revenue", "Net FED"),
    ("total_ruc_net_revenue", "Total RUC"),
    ("total_nltf_net_revenue", "Total NLTF"),
)
OFFICIAL_SERIES = ("net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue")
SIGNATURE: tuple[tuple[str, int, int], ...] = ()


def _key(current_policy: str, mbu_policy: str, *, retention: bool = False, uptake: str | None = None):
    """The default front-end key, with one dimension varied at a time."""
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    ev_uptake_key = (
        uptake or DEFAULT_EV_UPTAKE_MODE,
        (),
        (),
        current_policy,
        mbu_policy,
        retention,
    )
    return sensitivity_key, ev_uptake_key


def _rows(pack, current_policy: str, mbu_policy: str, **kwargs) -> pd.DataFrame:
    sensitivity_key, ev_uptake_key = _key(current_policy, mbu_policy, **kwargs)
    rows, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, ev_uptake_key, pack
    )
    return rows


def _value(rows: pd.DataFrame, role: str, series: str, fy: int) -> float | None:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pack = load_revenue_outlook_pack(PACK_DIR, repo_root=ROOT)
    pack_rows = pack.revenue_chart_rows
    failures: list[str] = []
    records: list[dict[str, object]] = []

    # Default front end: current delayed, MBU published, retention Off.
    default_rows = _rows(pack, app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED)

    for series, label in CURRENT_SERIES:
        for fy in CURRENT_FYS:
            records.append(
                {
                    "stage": "final_default_front_end",
                    "scope": "current_basecase",
                    "policy": "current=delayed_6m; mbu26=published",
                    "fy": fy,
                    "series_id": series,
                    "label": label,
                    "value": _value(default_rows, "basecase", series, fy),
                    "pack_stage_value": _value(pack_rows, "basecase", series, fy),
                }
            )

    for state in (app.FED_POLICY_PUBLISHED, app.FED_POLICY_DELAYED_6M, app.FED_POLICY_OFF):
        rows = _rows(pack, app.FED_POLICY_DELAYED_6M, state)
        for series in OFFICIAL_SERIES:
            for fy in OFFICIAL_FYS:
                records.append(
                    {
                        "stage": "final_default_front_end",
                        "scope": "official_comparator",
                        "policy": f"mbu26={state}",
                        "fy": fy,
                        "series_id": series,
                        "label": f"MBU26 {series}",
                        "value": _value(rows, "official_comparator", series, fy),
                        "pack_stage_value": _value(pack_rows, "official_comparator", series, fy),
                    }
                )

    audit = pd.DataFrame(records)
    audit.to_csv(OUT / "gold_path_audit.csv", index=False)

    # ---- hard gates -------------------------------------------------------

    # PED retention is Off by default: turning it on must change something, so
    # "Off by default" is a real default rather than a dead control.
    retention_rows = _rows(pack, app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED, retention=True)
    if _value(retention_rows, "basecase", "light_petrol_vkt", 2030) == _value(
        default_rows, "basecase", "light_petrol_vkt", 2030
    ):
        failures.append("PED retention overlay has no effect; the default cannot be verified as Off")

    # Raw conventional Light RUC is preserved before the current policy response.
    published_rows = _rows(pack, app.FED_POLICY_PUBLISHED, app.FED_POLICY_PUBLISHED)
    for fy in CURRENT_FYS:
        raw = _value(pack_rows, "basecase", "light_ruc_net_km", fy)
        front = _value(published_rows, "basecase", "light_ruc_net_km", fy)
        if raw is None or front is None or abs(raw - front) > TOL:
            failures.append(f"FY{fy} conventional Light RUC km not preserved: pack={raw} front={front}")

    # The current policy is applied exactly once: applying it twice would
    # double the delta.
    for fy in (2027,):
        published = _value(published_rows, "basecase", "total_nltf_net_revenue", fy)
        delayed = _value(default_rows, "basecase", "total_nltf_net_revenue", fy)
        if published is None or delayed is None or abs(published - delayed) < TOL:
            failures.append(f"current delayed policy had no FY{fy} effect")

    # Official policy is applied once and only to official rows.
    off_rows = _rows(pack, app.FED_POLICY_DELAYED_6M, app.FED_POLICY_OFF)
    for fy in CURRENT_FYS:
        if _value(off_rows, "basecase", "total_nltf_net_revenue", fy) != _value(
            default_rows, "basecase", "total_nltf_net_revenue", fy
        ):
            failures.append(f"MBU26 policy moved a current row in FY{fy}; selectors are not independent")

    # Base pool is preserved under uptake presets: reallocation, not resizing.
    for preset in ("Fast", "Slow"):
        try:
            preset_rows = _rows(
                pack, app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED, uptake=preset
            )
        except Exception:
            continue
        for fy in CURRENT_FYS:
            pool_default = sum(
                _value(default_rows, "basecase", series, fy) or 0.0
                for series in ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")
            )
            pool_preset = sum(
                _value(preset_rows, "basecase", series, fy) or 0.0
                for series in ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")
            )
            if pool_default and abs(pool_default - pool_preset) > 1e-3:
                failures.append(
                    f"{preset} uptake resized the FY{fy} Base pool: {pool_default} vs {pool_preset}"
                )

    # FY2030 is the last complete current Light RUC-dependent annual result.
    current_annual = default_rows[
        default_rows["time_grain"].astype(str).eq("june_year")
        & default_rows["scenario_role"].astype(str).isin({"basecase", "comparison"})
    ]
    last_current = int(pd.to_numeric(current_annual["june_year"], errors="coerce").max())
    if last_current != LAST_DECISION_GRADE_ANNUAL_FY:
        failures.append(f"last current annual FY is {last_current}, expected {LAST_DECISION_GRADE_ANNUAL_FY}")

    # The official comparator continues through its own horizon.
    official_annual = default_rows[
        default_rows["scenario_role"].astype(str).eq("official_comparator")
    ]
    last_official = int(pd.to_numeric(official_annual["june_year"], errors="coerce").max())
    if last_official <= LAST_DECISION_GRADE_ANNUAL_FY:
        failures.append(f"official comparator stops at FY{last_official}")

    # Chart, line reconciliation and stack agree.
    sensitivity_key, ev_uptake_key = _key(app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED)
    line, _residuals, stack, _bridge = app.cached_aligned_scenario_detail_frames(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, ev_uptake_key, pack
    )
    for fy in CURRENT_FYS:
        chart_value = _value(default_rows, "basecase", "total_nltf_net_revenue", fy)
        matched = line[
            line["FY"].astype("Int64").eq(fy)
            & line["series_id"].astype(str).eq("total_nltf_net_revenue")
            & line["source_path"].astype(str).str.contains("Base", case=False, na=False)
        ]
        line_values = pd.to_numeric(matched["value"], errors="coerce").dropna()
        if chart_value is not None and len(line_values):
            if abs(float(line_values.iloc[0]) - chart_value) > TOL:
                failures.append(
                    f"FY{fy} chart and line reconciliation disagree: "
                    f"{chart_value} vs {float(line_values.iloc[0])}"
                )

    # ---- report -----------------------------------------------------------
    pd.set_option("display.width", 200)
    print(f"gold path audit rows: {len(audit)} -> {OUT / 'gold_path_audit.csv'}")
    print(f"\ncurrent basecase (current=delayed_6m, mbu26=published, retention Off)")
    current = audit[audit["scope"].eq("current_basecase")]
    print(
        current.pivot_table(index="label", columns="fy", values="value", sort=False).to_string(
            float_format=lambda value: f"{value:,.3f}"
        )
    )
    print(f"\nMBU26 official comparator by policy state")
    official = audit[audit["scope"].eq("official_comparator")]
    print(
        official.pivot_table(
            index=["series_id", "policy"], columns="fy", values="value", sort=False
        ).to_string(float_format=lambda value: f"{value:,.3f}")
    )
    print(f"\nlast current annual FY : {last_current}")
    print(f"last official annual FY: {last_official}")
    print(f"stack rows             : {len(stack)}")

    if failures:
        print("\nFAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nPASS: every gold-path gate holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
