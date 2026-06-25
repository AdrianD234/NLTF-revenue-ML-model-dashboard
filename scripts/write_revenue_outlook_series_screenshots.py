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
    "gross_ped_revenue": ("Revenue Outlook - PED revenue", "revenue-outlook-ped-revenue.png"),
    "net_fed_revenue": ("Revenue Outlook - Net FED revenue", "revenue-outlook-net-fed.png"),
    "total_fed_ruc_net_revenue": ("Revenue Outlook - Total RUC+PED revenue", "revenue-outlook-total-ruc-ped.png"),
    "total_nltf_net_revenue": ("Revenue Outlook - Total NLTF revenue", "revenue-outlook-total-nltf.png"),
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

    reconciliation_path = _write_reconciliation_table_screenshot()
    manifest.append(
        {
            "series_id": "revenue_line_reconciliation",
            "title": "Revenue Outlook - revenue line reconciliation",
            "repo_relative_path": reconciliation_path.relative_to(ROOT).as_posix(),
            "rows": 0,
        }
    )

    manifest_path = ROOT / "artifacts" / "revenue_outlook_series_screenshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for item in manifest:
        print(f"WROTE {item['repo_relative_path']} rows={item['rows']}")


def _write_reconciliation_table_screenshot() -> Path:
    line = pd.read_csv(PACK_DIR / "revenue_line_reconciliation.csv")
    keep_lines = [
        "Total RUC all classes",
        "PED revenue",
        "Gross FED revenue",
        "Net FED revenue",
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
    return path


if __name__ == "__main__":
    main()
