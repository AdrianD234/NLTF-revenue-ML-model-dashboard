"""Evidence for the missing BEFU26 Light petrol VKT official trace.

The dashboard offers ``Light petrol VKT`` in the Revenue Outlook series
selector, but no official comparator line ever draws for it. This script
traces the four hops between the published workbook and the plotted trace

    official-vintage source
        -> materialised official annual rows
        -> runtime chart rows
        -> selected-series vocabulary

and writes the per-hop evidence so the break can be located rather than
guessed at. It reads committed packs only; nothing here loads a workbook.

    .venv\\Scripts\\python.exe scripts\\build_revenue_outlook_series_coverage_diagnosis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.official_vintage import (  # noqa: E402
    load_official_vintage,
    official_vintage_choices,
)
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    DISPLAY_SERIES_ORDER,
)

OUT = ROOT / "artifacts" / "revenue_outlook_series_coverage"

# The Revenue Outlook selector's preferred ordering, mirrored from
# ``app._revenue_outlook_stream_options``. Copied rather than imported: this
# script must be able to report that the app and the pack disagree, which it
# cannot do if it derives both sides from the same call.
SELECTOR_PREFERRED_LABELS = (
    "Light petrol VKT",
    "PED VKT per capita",
    "PED volume",
    "Light RUC net km",
    "Heavy RUC net km",
    "PED revenue",
    "Light RUC revenue",
    "Heavy RUC revenue",
    "Gross FED revenue",
    "Net FED revenue",
    "Total RUC all classes",
    "Net MVR revenue",
    "Total RUC+PED revenue",
    "Total NLTF revenue",
    "Light RUC volume",
    "Heavy RUC volume",
)
# The selector adds this label unconditionally once its two PED companions are
# present, because the annual row is materialised at runtime from the PED
# bridge audit rather than shipped in the chart-row pack.
SELECTOR_RUNTIME_ADDED_LABEL = "Light petrol VKT"


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame.get(column), errors="coerce")


def official_series_inventory(chart_rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (vintage, series): what the source has and where it stops."""

    pack_series = set(chart_rows["series_id"].astype(str))
    pack_labels = {
        str(series_id): str(label)
        for series_id, label in chart_rows[["series_id", "series_label"]]
        .drop_duplicates()
        .itertuples(index=False)
    }
    records: list[dict[str, object]] = []
    for vintage_id, _display in official_vintage_choices(ROOT):
        pack = load_official_vintage(vintage_id, repo_root=ROOT)
        annual = pack.official_annual.copy()
        annual["_fy"] = _numeric(annual, "FY")
        annual["_value"] = _numeric(annual, "value")
        for series_id, group in annual.groupby("series_id", dropna=False):
            valued = group[group["_value"].notna()]
            selector_label = pack_labels.get(str(series_id), "")
            if not selector_label and str(series_id) == "light_petrol_vkt":
                selector_label = SELECTOR_RUNTIME_ADDED_LABEL
            traced = chart_rows[
                chart_rows["series_id"].astype(str).eq(str(series_id))
                & chart_rows["trace_name"].astype(str).eq(f"{vintage_id} official")
            ]
            records.append(
                {
                    "vintage_id": vintage_id,
                    "series_id": str(series_id),
                    "display_name": str(group["display_name"].iloc[0]),
                    "source_series_id": str(group["source_series_id"].iloc[0]),
                    "source_label": str(group["source_label"].iloc[0]),
                    "unit": str(group["unit"].iloc[0]),
                    "metric_type": str(group["metric_type"].iloc[0]),
                    "section": str(group["section"].iloc[0]),
                    "row_role": str(group["row_role"].iloc[0]),
                    "source_rows": int(len(group)),
                    "valued_rows": int(len(valued)),
                    "first_fy": int(group["_fy"].min()),
                    "last_fy": int(group["_fy"].max()),
                    "first_valued_fy": int(valued["_fy"].min()) if len(valued) else "",
                    "last_valued_fy": int(valued["_fy"].max()) if len(valued) else "",
                    "in_display_series_order": str(series_id) in set(DISPLAY_SERIES_ORDER),
                    "in_runtime_chart_pack": str(series_id) in pack_series,
                    "runtime_official_rows": int(len(traced)),
                    "selector_label": selector_label,
                    "selectable": bool(selector_label),
                    "coverage_status": _coverage_status(
                        str(series_id), bool(selector_label), len(traced)
                    ),
                }
            )
    return pd.DataFrame.from_records(records).sort_values(
        ["series_id", "vintage_id"], kind="stable"
    )


def _coverage_status(series_id: str, selectable: bool, runtime_rows: int) -> str:
    if runtime_rows > 0:
        return "official_trace_materialised"
    if not selectable:
        return "not_selectable_official_trace_not_required"
    if series_id not in set(DISPLAY_SERIES_ORDER):
        return "selectable_but_omitted_from_display_series_order"
    return "selectable_but_official_rows_absent"


def series_alias_audit(chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Every declared alias, plus what the runtime vocabulary does with it."""

    pack_series = set(chart_rows["series_id"].astype(str))
    records: list[dict[str, object]] = []
    for vintage_id, _display in official_vintage_choices(ROOT):
        pack = load_official_vintage(vintage_id, repo_root=ROOT)
        source_ids = set(pack.official_annual["series_id"].astype(str))
        for row in pack.series_alias_audit.to_dict("records"):
            runtime_id = str(row.get("runtime_series_id") or "")
            records.append(
                {
                    "vintage_id": vintage_id,
                    "source_label": str(row.get("source_label") or ""),
                    "source_series_id": str(row.get("source_series_id") or ""),
                    "runtime_series_id": runtime_id,
                    "dashboard_label": str(row.get("dashboard_label") or ""),
                    "unit": str(row.get("unit") or ""),
                    "alias_reason": str(row.get("alias_reason") or ""),
                    "status": str(row.get("status") or ""),
                    # Does the alias land on a row the vintage actually
                    # materialises? A dangling target is the only alias fault
                    # that could hide a series; the two columns below are
                    # downstream facts, not alias faults.
                    "alias_target_materialised_in_source": runtime_id in source_ids,
                    "runtime_series_in_chart_pack": runtime_id in pack_series,
                    "runtime_series_in_display_order": runtime_id in set(DISPLAY_SERIES_ORDER),
                    "alias_is_the_defect": runtime_id not in source_ids,
                }
            )
    return pd.DataFrame.from_records(records).sort_values(
        ["source_series_id", "vintage_id"], kind="stable"
    )


def selector_vocabulary(chart_rows: pd.DataFrame) -> list[str]:
    available = set(chart_rows["series_label"].dropna().astype(str))
    if {"PED VKT per capita", "PED volume"}.issubset(available):
        available.add(SELECTOR_RUNTIME_ADDED_LABEL)
    ordered = [label for label in SELECTOR_PREFERRED_LABELS if label in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


def diagnosis_markdown(
    inventory: pd.DataFrame,
    alias: pd.DataFrame,
    chart_rows: pd.DataFrame,
    selectable: list[str],
) -> str:
    lp_inventory = inventory[inventory["series_id"].eq("light_petrol_vkt")]
    befu = lp_inventory[lp_inventory["vintage_id"].eq("BEFU26")].iloc[0]
    mbu = lp_inventory[lp_inventory["vintage_id"].eq("MBU26")].iloc[0]
    lp_rows = chart_rows[chart_rows["series_id"].eq("light_petrol_vkt")]
    official_traces = sorted(
        chart_rows[chart_rows["scenario_role"].astype(str).eq("official_comparator")][
            "trace_name"
        ]
        .astype(str)
        .unique()
    )
    alias_defects = alias[alias["alias_is_the_defect"]]
    lines = [
        "# BEFU26 Light petrol VKT: why the official trace never draws",
        "",
        "Generated by `scripts/build_revenue_outlook_series_coverage_diagnosis.py`",
        "from committed packs only.",
        "",
        "## Verdict",
        "",
        "The BEFU26 source is complete. The break is a **runtime materialisation**",
        "omission, not a missing source, a wrong alias, a unit mismatch or a grain",
        "mismatch: `light_petrol_vkt` is absent from `DISPLAY_SERIES_ORDER`, which is",
        "the single membership filter every runtime chart-row builder in",
        "`model_dashboard/revenue_outlook.py` applies before emitting a row.",
        "",
        "## Identity",
        "",
        "| Fact | Value |",
        "| --- | --- |",
        "| UI display label | `Light petrol VKT` |",
        "| Selector source | `app._revenue_outlook_stream_options`, added unconditionally once `PED VKT per capita` and `PED volume` are present |",
        "| Runtime `series_id` | `light_petrol_vkt` |",
        f"| BEFU26 source `series_id` | `{befu['source_series_id']}` |",
        f"| BEFU26 source label | `{befu['source_label']}` |",
        f"| BEFU26 unit | `{befu['unit']}` |",
        f"| BEFU26 `row_role` | `{befu['row_role']}` |",
        f"| BEFU26 source FY span | FY{befu['first_fy']}-FY{befu['last_fy']} ({befu['source_rows']} rows) |",
        f"| BEFU26 valued FY span | FY{befu['first_valued_fy']}-FY{befu['last_valued_fy']} ({befu['valued_rows']} values) |",
        f"| MBU26 valued FY span | FY{mbu['first_valued_fy']}-FY{mbu['last_valued_fy']} ({mbu['valued_rows']} values) |",
        "",
        "FY2001 and FY2002 are blank in both vintages. That is declared, not lost:",
        "the registry carries an explicit `allowed_missing` entry for",
        "`light_petrol_vkt` at those two June years.",
        "",
        "## Hop-by-hop trace",
        "",
        "### 1. Official-vintage source - PRESENT",
        "",
        "`data/revenue_model_source_pack/official_vintages/befu26/official_annual.parquet`",
        f"carries {befu['source_rows']} `light_petrol_vkt` rows, {befu['valued_rows']} of them valued,",
        f"under `series_id=light_petrol_vkt`, `unit={befu['unit']}`, `metric_type={befu['metric_type']}`,",
        f"`section={befu['section']}`. The canonical definition lives in",
        "`official_vintage.CANONICAL_SERIES_DEFINITIONS` and maps source label",
        f"`{befu['source_label']}` to that id directly.",
        "",
        "### 2. Alias contract - NOT THE DEFECT",
        "",
        f"{len(alias)} alias rows were audited across the registered vintages.",
        f"Rows whose `runtime_series_id` lands on no materialised source row: {len(alias_defects)}.",
        "",
        "`light_petrol_vkt` does not appear as an alias source at all - it is a",
        "direct canonical id. The one nearby alias is a different series:",
        "`light_petrol_vkt_per_capita` -> `ped_vkt_per_capita`, which resolves",
        "correctly and is published. So the failure is not a wrong canonical alias,",
        "and adding an alias would be the wrong fix.",
        "",
        "### 3. Materialised official annual rows - PRESENT",
        "",
        "The pack loader returns the rows unfiltered; `OfficialVintagePack.official_annual`",
        "includes `light_petrol_vkt` for both registered vintages, with BEFU26 and",
        "MBU26 carrying materially different forecast levels (they are not a relabel",
        "of one another).",
        "",
        "### 4. Runtime chart rows - THE BREAK",
        "",
        "`_runtime_mbu26_official_rows`, `_runtime_mbu26_actual_rows`,",
        "`_runtime_release_rows`, `_runtime_current_rows`, `_runtime_bridge_components`",
        "and `_runtime_future_revenue_forecasts` all open with the same membership",
        "test:",
        "",
        "```python",
        "data = frame[frame['series_id'].astype(str).isin(DISPLAY_SERIES_ORDER)]",
        "```",
        "",
        f"`DISPLAY_SERIES_ORDER` holds {len(DISPLAY_SERIES_ORDER)} ids and",
        "`light_petrol_vkt` is not one of them. Every official row for the series is",
        "therefore dropped before it can become a chart row - for BEFU26 and for",
        f"MBU26 alike. Official traces materialised in the pack: {', '.join(official_traces)}.",
        f"Runtime chart rows carrying `series_id=light_petrol_vkt`: {len(lp_rows)}.",
        "",
        "### 5. Selected-series vocabulary - the series is still offered",
        "",
        f"The selector publishes {len(selectable)} labels, `Light petrol VKT` among",
        "them. Its annual line is reconstructed at runtime by",
        "`_append_selected_light_petrol_vkt_rows`, which reads the PED bridge impact",
        "audit. That audit is keyed by `(source_path, scenario_name, fed_path)` and",
        "only ever covers current-model scenarios, so the reconstruction can produce",
        "a Current line and can never produce an official one.",
        "",
        "## Why the official line is missing but other series' are not",
        "",
        "Every other selectable series is in `DISPLAY_SERIES_ORDER`, so its official",
        "rows survive the filter. `Light petrol VKT` is the only selectable label",
        "whose id is not, and it is offered anyway because the selector adds it by",
        "hand. Selectability and materialisation are governed in two different",
        "places and they disagree.",
        "",
        "## Resolution taken",
        "",
        "Preference order B: materialise an existing BEFU26 source row that is",
        "currently omitted. No value is invented, copied from MBU26, substituted",
        "from the Current model, interpolated or extrapolated - the published",
        "annual values are carried through unchanged, in their source unit, over",
        "their own source horizon.",
        "",
        "The membership list itself is deliberately NOT edited. Adding",
        "`light_petrol_vkt` to `DISPLAY_SERIES_ORDER` would also route the series",
        "through `_runtime_current_rows` (changing the Current line from the",
        "PED-bridge-selected values to raw pack values), `_fan_availability_frame`",
        "(new fan-gap rows), `_runtime_future_revenue_forecasts`,",
        "`_runtime_bridge_components` and `_series_order_index`. Those touch the",
        "current-model path and chart presentation, which this branch does not own.",
        "The official rows are instead materialised additively through",
        "`model_dashboard/revenue_outlook_series_coverage.official_rows_for_series`",
        "in the governed runtime chart-row schema, leaving every existing row",
        "byte-identical.",
        "",
        "## Checks the resolution must satisfy",
        "",
        "- official value and unit reconcile to the source row (identity, not a transform);",
        "- BEFU26 and MBU26 stay distinct;",
        "- no other official value moves;",
        "- lineage records the source pack, its manifest hash and the source cell;",
        "- nothing is emitted beyond each vintage's own source horizon.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chart_rows = pd.read_parquet(
        ROOT / CURRENT_REVENUE_OUTLOOK_DIR / "revenue_chart_rows.parquet"
    )
    inventory = official_series_inventory(chart_rows)
    alias = series_alias_audit(chart_rows)
    selectable = selector_vocabulary(chart_rows)

    inventory.to_csv(OUT / "official_series_inventory.csv", index=False, lineterminator="\n")
    alias.to_csv(OUT / "series_alias_audit.csv", index=False, lineterminator="\n")
    (OUT / "befu26_light_petrol_diagnosis.md").write_text(
        diagnosis_markdown(inventory, alias, chart_rows, selectable),
        encoding="utf-8",
        newline="\n",
    )
    print(f"official_series_inventory.csv  {len(inventory)} rows")
    print(f"series_alias_audit.csv         {len(alias)} rows")
    print(f"selectable series              {len(selectable)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
