from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "current_revenue_outlook"
SCREENSHOT_DIR = ROOT / "artifacts" / "screenshots"

SERIES = {
    "ped_vkt_per_capita": ("Revenue Outlook - PED VKT per capita", "revenue-outlook-ped-vkt-per-capita.png"),
    "gross_ped_revenue": ("Revenue Outlook - PED revenue", "revenue-outlook-ped-revenue.png"),
    "net_fed_revenue": ("Revenue Outlook - Net FED revenue", "revenue-outlook-net-fed.png"),
    "total_fed_ruc_net_revenue": ("Revenue Outlook - Total RUC+PED revenue", "revenue-outlook-total-ruc-ped.png"),
    "total_nltf_net_revenue": ("Revenue Outlook - Total NLTF revenue", "revenue-outlook-total-nltf.png"),
}

FAN_SERIES = {
    "total_nltf_net_revenue": "Total NLTF revenue",
    "ped_vkt_per_capita": "PED VKT per capita",
    "gross_ped_revenue": "PED revenue",
    "light_ruc_net_km": "Light RUC net km",
}

COMPOSITION_SOURCE_PATHS = {
    "MBU26 official": "mbu26-official",
    "Current finalist Base case": "current-finalist-base-case",
    "Current finalist High population/comparison": "current-finalist-high-population-comparison",
}

FAN_SOURCE_AUTO = "Auto / best available"
FAN_SOURCE_MBU26_ARCHIVED = "MBU26 archived forecast error"
FAN_SOURCE_CURRENT_BACKTEST = "Current finalist backtest error"
FAN_SOURCE_SCENARIO_SPREAD = "Scenario spread"
FAN_SOURCE_NONE = "None / governed gap"
FAN_SOURCE_ORDER = [
    FAN_SOURCE_AUTO,
    FAN_SOURCE_MBU26_ARCHIVED,
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_SCENARIO_SPREAD,
]
FAN_SOURCE_AUTO_PRIORITY = [
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_MBU26_ARCHIVED,
    FAN_SOURCE_SCENARIO_SPREAD,
]
FAN_SOURCE_SLUGS = {
    FAN_SOURCE_AUTO: "auto-best-available",
    FAN_SOURCE_MBU26_ARCHIVED: "mbu26-archived-forecast-error",
    FAN_SOURCE_CURRENT_BACKTEST: "current-finalist-backtest-error",
    FAN_SOURCE_SCENARIO_SPREAD: "scenario-spread",
    FAN_SOURCE_NONE: "none-governed-gap",
}
SERIES_SLUGS = {
    "total_nltf_net_revenue": "total-nltf",
    "ped_vkt_per_capita": "ped-vkt-per-capita",
    "gross_ped_revenue": "ped-revenue",
    "light_ruc_net_km": "light-ruc-net-km",
}

TRACE_ORDER = [
    "Actual",
    "MBU26 official",
    "Current finalist Base case",
    "Current finalist High population/comparison",
]
TRACE_STYLE = {
    "Actual": {"color": "#737373", "linestyle": "-", "marker": "o"},
    "MBU26 official": {"color": "#00843D", "linestyle": "--", "marker": "s"},
    "Current finalist Base case": {"color": "#006FAD", "linestyle": "-", "marker": "o"},
    "Current finalist High population/comparison": {"color": "#E56B2B", "linestyle": "-", "marker": "o"},
}


def main() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    rows = pd.read_csv(PACK_DIR / "revenue_chart_rows.csv")
    rows = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["plot_allowed"].astype(str).str.lower().isin(["true", "1"])
    ].copy()
    rows["year"] = pd.to_numeric(rows["june_year"], errors="coerce")
    rows["value_numeric"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows[rows["year"].notna() & rows["value_numeric"].notna()].copy()

    manifest = []
    for series_id, (title, filename) in SERIES.items():
        frame = rows[rows["series_id"].astype(str).eq(series_id)].copy()
        frame = frame[
            frame["trace_role"].astype(str).ne("in_house_current_finalist")
            | frame["fed_path"].astype(str).eq("Current planned path")
        ].copy()
        fig, ax = plt.subplots(figsize=(11.5, 6.2), dpi=150)
        for trace_name in TRACE_ORDER:
            group = frame[frame["trace_name"].astype(str).eq(trace_name)].copy()
            if group.empty:
                continue
            group = group.sort_values(["year", "scenario_name"], kind="stable").drop_duplicates(
                ["year", "trace_name", "scenario_name"],
                keep="last",
            )
            style = TRACE_STYLE.get(trace_name, {})
            ax.plot(
                group["year"],
                group["value_numeric"],
                label=trace_name,
                linewidth=2.0,
                markersize=4.5,
                **style,
            )
        ax.axvline(2025, color="#94A3B8", linewidth=1.0)
        ax.text(2025.05, ax.get_ylim()[1], "FY2025 actual anchor", va="top", ha="left", fontsize=8, color="#475569")
        ax.set_title(title, loc="left", fontsize=14, weight="bold")
        ax.set_xlabel("June year")
        unit = frame["value_unit"].dropna().astype(str).iloc[0] if not frame.empty else "$m nominal ex GST"
        ax.set_ylabel(unit)
        ax.grid(True, axis="y", color="#E2E8F0", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left", frameon=False, fontsize=8)
        fig.tight_layout()
        path = SCREENSHOT_DIR / filename
        fig.savefig(path)
        plt.close(fig)
        manifest.append(
            {
                "series_id": series_id,
                "title": title,
                "repo_relative_path": path.relative_to(ROOT).as_posix(),
                "rows": int(len(frame)),
            }
        )

    manifest.extend(_write_fan_screenshots())
    manifest.extend(_write_composition_screenshots())

    reconciliation_path, reconciliation_rows = _write_reconciliation_table_screenshot()
    manifest.append(
        {
            "series_id": "revenue_line_reconciliation",
            "title": "Revenue Outlook - revenue line reconciliation",
            "repo_relative_path": reconciliation_path.relative_to(ROOT).as_posix(),
            "rows": reconciliation_rows,
        }
    )
    alias_path, alias_rows = _write_alias_audit_screenshot()
    manifest.append(
        {
            "series_id": "series_alias_audit",
            "title": "Revenue Outlook - series alias audit",
            "repo_relative_path": alias_path.relative_to(ROOT).as_posix(),
            "rows": alias_rows,
        }
    )

    manifest_path = ROOT / "artifacts" / "revenue_outlook_series_screenshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for item in manifest:
        print(f"WROTE {item['repo_relative_path']} rows={item['rows']}")


def _write_fan_screenshots() -> list[dict[str, object]]:
    availability_path = PACK_DIR / "fan_availability.csv"
    bands_path = PACK_DIR / "fan_band_rows.csv"
    if not availability_path.exists() or not bands_path.exists():
        return []

    availability = pd.read_csv(availability_path)
    bands = pd.read_csv(bands_path)
    manifest: list[dict[str, object]] = []
    for series_id, series_label in FAN_SERIES.items():
        for selected_source in FAN_SOURCE_ORDER:
            if not _fan_source_available(availability, series_id, selected_source):
                continue
            resolved_source = _resolve_fan_source(availability, series_id, selected_source)
            frame = bands[
                bands["series_id"].astype(str).eq(series_id)
                & bands["fan_source"].astype(str).eq(resolved_source)
            ].copy()
            if frame.empty:
                continue
            title = f"Revenue Outlook fan - {series_label}"
            if selected_source == FAN_SOURCE_AUTO and resolved_source != selected_source:
                title = f"{title} - Auto ({resolved_source})"
            else:
                title = f"{title} - {selected_source}"
            filename = (
                f"revenue-outlook-fan-{SERIES_SLUGS[series_id]}-"
                f"{FAN_SOURCE_SLUGS[selected_source]}.png"
            )
            path = _write_fan_screenshot(frame, title, filename)
            manifest.append(
                {
                    "series_id": series_id,
                    "title": title,
                    "fan_source": selected_source,
                    "resolved_fan_source": resolved_source,
                    "repo_relative_path": path.relative_to(ROOT).as_posix(),
                    "rows": int(len(frame)),
                }
            )
    return manifest


def _fan_source_available(availability: pd.DataFrame, series_id: str, fan_source: str) -> bool:
    rows = availability[
        availability["series_id"].astype(str).eq(series_id)
        & availability["fan_source"].astype(str).eq(fan_source)
    ]
    if rows.empty:
        return False
    return str(rows.iloc[0]["available"]).lower() in {"true", "1"}


def _resolve_fan_source(availability: pd.DataFrame, series_id: str, fan_source: str) -> str:
    if fan_source != FAN_SOURCE_AUTO:
        return fan_source
    for candidate in FAN_SOURCE_AUTO_PRIORITY:
        if _fan_source_available(availability, series_id, candidate):
            return candidate
    return FAN_SOURCE_NONE


def _write_fan_screenshot(frame: pd.DataFrame, title: str, filename: str) -> Path:
    frame = frame.copy()
    frame["year"] = pd.to_numeric(frame["FY"], errors="coerce")
    frame["central"] = pd.to_numeric(frame["central"], errors="coerce")
    for column in ["lower50", "upper50", "lower80", "upper80"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["year", "central", "lower50", "upper50", "lower80", "upper80"])
    frame = frame.sort_values(["year", "scenario_name"], kind="stable").drop_duplicates(["year"], keep="last")

    fig, ax = plt.subplots(figsize=(11.5, 6.2), dpi=150)
    x = frame["year"].to_numpy(dtype=float)
    ax.fill_between(
        x,
        frame["lower80"].to_numpy(dtype=float),
        frame["upper80"].to_numpy(dtype=float),
        color="#BFDBFE",
        alpha=0.55,
        label="80% band" if "scenario_spread" not in str(frame["method"].iloc[0]) else "Outer scenario range",
    )
    ax.fill_between(
        x,
        frame["lower50"].to_numpy(dtype=float),
        frame["upper50"].to_numpy(dtype=float),
        color="#60A5FA",
        alpha=0.45,
        label="50% band" if "scenario_spread" not in str(frame["method"].iloc[0]) else "Inner scenario range",
    )
    ax.plot(x, frame["central"].to_numpy(dtype=float), color="#0F172A", linewidth=2.1, label="Central path")
    ax.axvline(2025, color="#94A3B8", linewidth=1.0)
    ax.set_title(title, loc="left", fontsize=14, weight="bold")
    ax.set_xlabel("June year")
    unit = frame["unit"].dropna().astype(str).iloc[0] if not frame.empty else "$m nominal ex GST"
    ax.set_ylabel(unit)
    interpretation = frame["interpretation"].dropna().astype(str).iloc[0] if not frame.empty else ""
    if interpretation:
        ax.text(
            0,
            -0.16,
            interpretation[:165],
            transform=ax.transAxes,
            fontsize=8,
            color="#475569",
            va="top",
            ha="left",
            wrap=True,
        )
    ax.grid(True, axis="y", color="#E2E8F0", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    fig.tight_layout()
    path = SCREENSHOT_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def _write_composition_screenshots() -> list[dict[str, object]]:
    stack_path = PACK_DIR / "revenue_stack_components.csv"
    if not stack_path.exists():
        return []
    stack = pd.read_csv(stack_path)
    manifest: list[dict[str, object]] = []
    for source_path, slug in COMPOSITION_SOURCE_PATHS.items():
        frame = stack[
            stack["source_path"].astype(str).eq(source_path)
            & (
                (
                    stack["stack_role"].astype(str).isin(["component_positive", "component_negative"])
                    & stack["section"].astype(str).isin(["RUC", "FED", "MVR", "TUC"])
                )
                | stack["series_id"].astype(str).eq("total_nltf_net_revenue")
            )
        ].copy()
        if frame.empty:
            continue
        frame["FY_numeric"] = pd.to_numeric(frame["FY"], errors="coerce")
        frame["stack_value_numeric"] = pd.to_numeric(frame["stack_value"], errors="coerce")
        frame = frame[
            frame["FY_numeric"].between(2025, 2035, inclusive="both")
            & frame["stack_value_numeric"].notna()
        ].copy()
        if frame.empty:
            continue
        title = f"Revenue Outlook composition - {source_path}"
        filename = f"revenue-outlook-composition-{slug}.png"
        path = _write_composition_screenshot(frame, title, filename)
        manifest.append(
            {
                "series_id": "revenue_stack_components",
                "title": title,
                "source_path": source_path,
                "repo_relative_path": path.relative_to(ROOT).as_posix(),
                "rows": int(len(frame)),
            }
        )
    return manifest


def _write_composition_screenshot(frame: pd.DataFrame, title: str, filename: str) -> Path:
    years = sorted(int(value) for value in frame["FY_numeric"].dropna().unique())
    stack_frame = frame[frame["stack_role"].astype(str).isin(["component_positive", "component_negative"])].copy()
    labels = (
        stack_frame[["line_label", "section_order", "line_order"]]
        .drop_duplicates()
        .sort_values(["section_order", "line_order", "line_label"], kind="stable")
    )
    fig, ax = plt.subplots(figsize=(12.5, 6.4), dpi=150)
    positive_bottom = pd.Series(0.0, index=years)
    negative_bottom = pd.Series(0.0, index=years)
    colors = [
        "#006FAD",
        "#00843D",
        "#6B4E71",
        "#E56B2B",
        "#3B7080",
        "#7A7D00",
        "#6A5ACD",
        "#C44900",
        "#287D8E",
        "#5B6770",
        "#B7791F",
        "#C2410C",
        "#9A3412",
        "#92400E",
    ]
    for index, row in labels.reset_index(drop=True).iterrows():
        label = str(row["line_label"])
        values = (
            stack_frame[stack_frame["line_label"].astype(str).eq(label)]
            .set_index("FY_numeric")["stack_value_numeric"]
            .reindex(years)
            .fillna(0.0)
        )
        bottom = positive_bottom.where(values >= 0, negative_bottom)
        ax.bar(years, values, bottom=bottom, label=label, color=colors[index % len(colors)], width=0.72)
        positive_bottom = positive_bottom + values.clip(lower=0)
        negative_bottom = negative_bottom + values.clip(upper=0)

    overlays = frame[frame["series_id"].astype(str).eq("total_nltf_net_revenue")] if "series_id" in frame.columns else pd.DataFrame()
    if not overlays.empty:
        overlay = overlays.drop_duplicates("FY_numeric", keep="last").sort_values("FY_numeric")
        ax.plot(overlay["FY_numeric"], overlay["value"], color="#0F172A", linewidth=2.2, marker="D", label="Total NLTF overlay")
    ax.axhline(0, color="#52616B", linewidth=1.0)
    ax.set_title(title, loc="left", fontsize=14, weight="bold")
    ax.set_xlabel("June year")
    ax.set_ylabel("$m nominal ex GST")
    ax.grid(True, axis="y", color="#E2E8F0", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=7)
    fig.tight_layout()
    path = SCREENSHOT_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def _write_reconciliation_table_screenshot() -> tuple[Path, int]:
    line = pd.read_csv(PACK_DIR / "revenue_line_reconciliation.csv")
    keep_lines = [
        "RUC net admin/refunds",
        "Gross PED",
        "Gross FED",
        "Net FED",
        "Total NLTF revenue",
    ]
    view = line[
        line["FY"].eq(2026)
        & line["source_path"].isin(["MBU26 official", "Current finalist Base case"])
        & line["line_label"].isin(keep_lines)
    ].copy()
    view["value"] = pd.to_numeric(view["value"], errors="coerce").map(lambda value: f"{value:,.2f}")
    view = view[["source_path", "section", "line_label", "value", "unit", "quarter_composition"]].rename(
        columns={
            "source_path": "Source path",
            "section": "Section",
            "line_label": "Line",
            "value": "Value",
            "unit": "Unit",
            "quarter_composition": "Quarter composition",
        }
    )
    fig, ax = plt.subplots(figsize=(13.5, 4.8), dpi=150)
    ax.axis("off")
    ax.set_title("Revenue Outlook - FY2026 revenue line reconciliation", loc="left", fontsize=14, weight="bold")
    table = ax.table(
        cellText=view.values,
        colLabels=view.columns,
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)
    for (row, _col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold", color="#0F172A")
            cell.set_facecolor("#E2E8F0")
        else:
            cell.set_facecolor("#FFFFFF" if row % 2 else "#F8FAFC")
    fig.tight_layout()
    path = SCREENSHOT_DIR / "revenue-outlook-reconciliation-table.png"
    fig.savefig(path)
    plt.close(fig)
    return path, int(len(view))


def _write_alias_audit_screenshot() -> tuple[Path, int]:
    alias = pd.read_csv(PACK_DIR / "series_alias_audit.csv")
    view = alias[["source_label", "source_series_id", "runtime_series_id", "dashboard_label", "source_cell", "status"]].rename(
        columns={
            "source_label": "Source label",
            "source_series_id": "Source series ID",
            "runtime_series_id": "Runtime series ID",
            "dashboard_label": "Dashboard label",
            "source_cell": "Source cell",
            "status": "Status",
        }
    )
    fig, ax = plt.subplots(figsize=(14.5, 5.2), dpi=150)
    ax.axis("off")
    ax.set_title("Revenue Outlook - series alias audit", loc="left", fontsize=14, weight="bold")
    table = ax.table(
        cellText=view.values,
        colLabels=view.columns,
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.2)
    table.scale(1, 1.32)
    for (row, _col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold", color="#0F172A")
            cell.set_facecolor("#E2E8F0")
        else:
            cell.set_facecolor("#FFFFFF" if row % 2 else "#F8FAFC")
    fig.tight_layout()
    path = SCREENSHOT_DIR / "revenue-outlook-series-alias-audit.png"
    fig.savefig(path)
    plt.close(fig)
    return path, int(len(view))


if __name__ == "__main__":
    main()
