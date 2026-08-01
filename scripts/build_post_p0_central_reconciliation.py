"""Gate A: is the corrected central path internally consistent after P0?

The Heavy-BEV key collision moved the DISPLAYED Heavy RUC leaf while leaving
its dependent totals alone, so the pre-fix chart could show a Heavy line that
disagreed with the Total RUC and Total NLTF built on top of it.  Removing the
collision should restore agreement rather than move the totals.

This proves it, for both engines and every governed Current scenario, by
comparing four independent views of the same number:

    chart rows              what the Total path chart plots
    line reconciliation     the governed per-line source spine
    stack components        the composition surface
    formula recomputation   FORMULA_DEFINITIONS evaluated from its own leaves

Nothing is force-balanced. A residual that survives is reported as a finding.

    .venv\\Scripts\\python.exe scripts\\build_post_p0_central_reconciliation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402

OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
ENGINES = (
    ("ensemble", Path(CURRENT_REVENUE_OUTLOOK_DIR)),
    ("ar1", Path("data") / "engine_ar1" / "current_revenue_outlook"),
)
FY_RANGE = range(2026, 2051)
# The governed tolerance the pack's own formula audit already uses.
TOLERANCE = 1e-6

# Every series the brief names, plus the leaves the Heavy identities depend on.
TRACKED_SERIES = (
    "heavy_ruc_net_km",
    "heavy_bev_ruc_net_km",
    "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_revenue",
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
)
CURRENT_ROLES = ("basecase", "comparison")


def production_key(vintage: str, schedule: str, shape_vintage: str) -> RevenueScenarioComputationKey:
    """Exactly what render_revenue_outlook_page builds, post-P0."""
    return RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        ped_retention_sensitivity=False,
        heavy_bev_transition=False,
        official_comparator_vintage_id=vintage,
        long_run_transition_schedule_id=schedule,
        long_run_shape_vintage_id=shape_vintage,
    )


def _annual(frame: pd.DataFrame, fy_column: str, value_column: str = "value") -> pd.DataFrame:
    out = frame.copy()
    out["_fy"] = pd.to_numeric(out.get(fy_column), errors="coerce")
    out["_value"] = pd.to_numeric(out.get(value_column), errors="coerce")
    return out.dropna(subset=["_fy", "_value"])


def chart_values(rows: pd.DataFrame) -> dict[tuple[str, str, int], float]:
    selected = rows[rows.get("time_grain", pd.Series(dtype=str)).astype(str).eq("june_year")]
    selected = selected[
        selected.get("scenario_role", pd.Series(dtype=str)).astype(str).isin(CURRENT_ROLES)
    ]
    selected = _annual(selected, "june_year")
    values: dict[tuple[str, str, int], float] = {}
    for _, row in selected.iterrows():
        key = (str(row["scenario_name"]), str(row["series_id"]), int(row["_fy"]))
        values.setdefault(key, float(row["_value"]))
    return values


def spine_values(frame: pd.DataFrame, scenario_name: str) -> dict[tuple[str, int], float]:
    """Keyed on scenario_name, the vocabulary the chart rows also use.

    source_path carries the DISPLAY trace name ("Current finalist Base case"),
    not the scenario id, so joining on it silently matches nothing.
    """
    if frame is None or frame.empty or "scenario_name" not in frame.columns:
        return {}
    selected = frame[frame["scenario_name"].astype(str).eq(scenario_name)]
    selected = _annual(selected, "FY")
    values: dict[tuple[str, int], float] = {}
    for _, row in selected.iterrows():
        values.setdefault((str(row["series_id"]), int(row["_fy"])), float(row["_value"]))
    return values


def recompute_formulas(leaves: dict[tuple[str, int], float]) -> dict[tuple[str, int], float]:
    """Evaluate FORMULA_DEFINITIONS in registry order from its own leaves."""
    computed = dict(leaves)
    for definition in FORMULA_DEFINITIONS:
        output = str(definition["output_series_id"])
        for fy in FY_RANGE:
            total = 0.0
            complete = True
            for term, sign in definition["terms"]:
                value = computed.get((str(term), fy))
                if value is None:
                    complete = False
                    break
                total += float(sign) * float(value)
            if complete:
                computed[(output, fy)] = total
    return {key: value for key, value in computed.items() if key not in leaves}


def reconcile(engine: str, pack, signature, key) -> list[dict]:
    """Every tracked series under one scenario key, across all four views."""
    records: list[dict] = []
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    rows, *_ = app.cached_scenario_overlay_rows(
        signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    line_frame, _residuals, stack_frame, _bridge = app.cached_aligned_scenario_detail_frames(
        signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    chart = chart_values(rows)
    for scenario in sorted({scenario for scenario, _series, _fy in chart}):
        line = spine_values(line_frame, scenario)
        stack = spine_values(stack_frame, scenario)
        leaves = {
            (series, fy): value
            for (series, fy), value in line.items()
            if not any(
                str(definition["output_series_id"]) == series
                for definition in FORMULA_DEFINITIONS
            )
        }
        recomputed = recompute_formulas(leaves)
        for series in TRACKED_SERIES:
            for fy in FY_RANGE:
                record = {
                    "engine": engine,
                    "heavy_bev_transition": key.heavy_bev_transition,
                    "scenario_name": scenario,
                    "series_id": series,
                    "FY": fy,
                    "chart_value": chart.get((scenario, series, fy)),
                    "line_reconciliation_value": line.get((series, fy)),
                    "stack_component_value": stack.get((series, fy)),
                    "formula_recomputed_value": recomputed.get((series, fy)),
                }
                present = [
                    value
                    for name, value in record.items()
                    if name.endswith("_value") and value is not None
                ]
                record["sources_present"] = len(present)
                record["max_abs_residual"] = max(present) - min(present) if len(present) > 1 else 0.0
                record["within_tolerance"] = (
                    record["max_abs_residual"] <= TOLERANCE if len(present) > 1 else None
                )
                records.append(record)
    return records


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    pre_fix_records: list[dict] = []
    official_records: list[dict] = []

    for engine, relative in ENGINES:
        directory = ROOT / relative
        if not directory.exists():
            continue
        pack = load_revenue_outlook_pack(directory, repo_root=ROOT)
        signature = revenue_outlook_signature(directory, ROOT)
        block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
        key = production_key(
            str(block.get("default_comparator_vintage_id") or "BEFU26"),
            str(block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID),
            str(block.get("long_run_shape_vintage_id") or ""),
        )
        records.extend(reconcile(engine, pack, signature, key))
        # The SAME check under the pre-fix reading, so "it closes" is a real
        # result rather than a check that would have passed either way.
        pre_fix_records.extend(
            reconcile(engine, pack, signature, key.replace(heavy_bev_transition=True))
        )

        # Official published rows must be untouched by any of this.
        committed = pd.read_csv(directory / "revenue_chart_rows.csv")
        rows, *_ = app.cached_scenario_overlay_rows(
            signature,
            app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
            PED_BRIDGE_DEFAULT_MODE,
            key,
            pack,
        )
        for vintage in ("BEFU26", "MBU26"):
            trace = f"{vintage} official"
            live = _annual(
                rows[rows.get("trace_name", pd.Series(dtype=str)).astype(str).eq(trace)],
                "june_year",
            )
            frozen = _annual(
                committed[committed.get("trace_name", pd.Series(dtype=str)).astype(str).eq(trace)],
                "june_year",
            )
            official_records.append(
                {
                    "engine": engine,
                    "official_vintage": vintage,
                    "rows_live": len(live),
                    "rows_committed": len(frozen),
                    "row_count_matches": len(live) == len(frozen),
                    "value_sum_live": round(float(live["_value"].sum()), 6),
                    "value_sum_committed": round(float(frozen["_value"].sum()), 6),
                    "unchanged": bool(
                        len(live) == len(frozen)
                        and abs(float(live["_value"].sum()) - float(frozen["_value"].sum())) <= TOLERANCE
                    ),
                }
            )

    frame = pd.DataFrame(records)
    frame.to_csv(OUT / "post_p0_central_reconciliation.csv", index=False)

    comparable = frame[frame["sources_present"] > 1]
    print(f"rows: {len(frame)}   comparable (>1 source): {len(comparable)}")
    assert not comparable.empty, "vacuous: nothing could be cross-checked"

    print("\nsource coverage by series:")
    coverage = frame.groupby("series_id")[
        ["chart_value", "line_reconciliation_value", "stack_component_value", "formula_recomputed_value"]
    ].count()
    print(coverage.to_string())

    failures = comparable[~comparable["within_tolerance"].fillna(True)]
    print(f"\nresiduals above {TOLERANCE}: {len(failures)}")
    if not failures.empty:
        summary = (
            failures.groupby(["engine", "series_id"])["max_abs_residual"]
            .agg(["count", "max"])
            .sort_values("max", ascending=False)
        )
        print(summary.to_string())
        print("\nworst rows:")
        print(
            failures.nlargest(10, "max_abs_residual")[
                ["engine", "scenario_name", "series_id", "FY", "chart_value",
                 "line_reconciliation_value", "formula_recomputed_value", "max_abs_residual"]
            ].to_string(index=False)
        )
    else:
        print("every comparable row agrees across all available sources")

    # ------------------------------------------------ the pre-fix comparison
    pre_fix = pd.DataFrame(pre_fix_records)
    pre_fix.to_csv(OUT / "pre_p0_central_reconciliation.csv", index=False)
    pre_fix_comparable = pre_fix[pre_fix["sources_present"] > 1]
    pre_fix_failures = pre_fix_comparable[~pre_fix_comparable["within_tolerance"].fillna(True)]
    print(
        f"\nsame check under the PRE-FIX reading (heavy_bev_transition=True): "
        f"{len(pre_fix_failures)} residuals above {TOLERANCE}"
    )
    if not pre_fix_failures.empty:
        print(
            pre_fix_failures.groupby("series_id")["max_abs_residual"]
            .agg(["count", "max"])
            .to_string()
        )

    # ------------------------------------------------------- official rows
    official = pd.DataFrame(official_records)
    official.to_csv(OUT / "official_rows_unchanged_audit.csv", index=False)
    print("\nofficial published rows:")
    print(official.to_string(index=False))

    verdict = {
        "post_p0_closes": bool(failures.empty),
        "pre_p0_closed": bool(pre_fix_failures.empty),
        "official_rows_unchanged": bool(official["unchanged"].all()) if len(official) else None,
        "comparable_rows": int(len(comparable)),
    }
    print("\nverdict:", verdict)
    if not verdict["post_p0_closes"]:
        raise SystemExit(1)
    if not verdict["official_rows_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
