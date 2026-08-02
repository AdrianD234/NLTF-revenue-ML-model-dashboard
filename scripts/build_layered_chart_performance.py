"""Runtime cost of the layered chart: pack lookup and figure assembly.

The whole point of materialising the pack offline is that the render path does
a filter and a Plotly build, never a simulation.  This measures exactly that.

    .venv\\Scripts\\python.exe scripts\\build_layered_chart_performance.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.revenue_chart_layers import (  # noqa: E402
    BAND_50_LAYER_ID,
    BAND_80_LAYER_ID,
    VFM_ENVELOPE_LAYER_ID,
    VFM_FAST_TRACE_NAME,
    VFM_SLOW_TRACE_NAME,
    build_layer_catalogue,
)
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402

OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
FED = "Current planned path"
SERIES = "Total NLTF revenue"
TRACES = (
    "Actual", "Current finalist Base case",
    "Current finalist High population/comparison", "BEFU26 official",
)
ALL_BANDS = (BAND_80_LAYER_ID, VFM_ENVELOPE_LAYER_ID, BAND_50_LAYER_ID)
REPEATS = 20


def timed(label: str, function, repeats: int = REPEATS) -> dict:
    function()  # warm
    start = perf_counter()
    for _ in range(repeats):
        function()
    elapsed = (perf_counter() - start) * 1000.0 / repeats
    return {"stage": label, "mean_ms": round(elapsed, 3), "repeats": repeats}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    start = perf_counter()
    pack_obj = app.cached_uncertainty_pack()
    rows.append(
        {
            "stage": "uncertainty pack load (cold, once per process)",
            "mean_ms": round((perf_counter() - start) * 1000.0, 3),
            "repeats": 1,
        }
    )
    assert pack_obj.available

    rows.append(
        timed(
            "uncertainty band lookup (per series)",
            lambda: app.cached_uncertainty_band_rows("total_nltf_net_revenue", "perf"),
        )
    )

    catalogue = build_layer_catalogue(
        [*TRACES, VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME],
        default_trace_names=list(TRACES),
        uncertainty_available=True,
        envelope_available=True,
    )
    rows.append(
        timed(
            "chart layer catalogue build",
            lambda: build_layer_catalogue(
                [*TRACES, VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME],
                default_trace_names=list(TRACES),
                uncertainty_available=True,
                envelope_available=True,
            ),
        )
    )

    revenue_pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    key = RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id="BEFU26",
        long_run_transition_schedule_id="balanced_structural",
        long_run_shape_vintage_id="BEFU26",
    )
    view = app.cached_revenue_outlook_view(
        signature, SERIES, "june_year", FED, TRACES,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE, key, revenue_pack,
    )
    bands = app.cached_uncertainty_band_rows("total_nltf_net_revenue", "perf")

    rows.append(
        timed(
            "figure assembly (default: 2 bands, 4 paths)",
            lambda: app.revenue_outlook_total_path_figure(
                view["filtered_rows"], selected_series=SERIES, selected_fy="FY2030",
                cone_band=view["cone_band"], selected_official_trace="BEFU26 official",
                uncertainty_rows=bands,
                selected_band_layers=(BAND_80_LAYER_ID, BAND_50_LAYER_ID),
            ),
        )
    )
    rows.append(
        timed(
            "figure assembly (all layers: 3 bands, all paths)",
            lambda: app.revenue_outlook_total_path_figure(
                view["filtered_rows"], selected_series=SERIES, selected_fy="FY2030",
                cone_band=view["cone_band"], selected_official_trace="BEFU26 official",
                uncertainty_rows=bands, selected_band_layers=ALL_BANDS,
            ),
        )
    )
    rows.append(
        timed(
            "lookup + assembly (the whole render-path cost)",
            lambda: app.revenue_outlook_total_path_figure(
                view["filtered_rows"], selected_series=SERIES, selected_fy="FY2030",
                cone_band=view["cone_band"], selected_official_trace="BEFU26 official",
                uncertainty_rows=app.cached_uncertainty_band_rows("total_nltf_net_revenue", "perf"),
                selected_band_layers=ALL_BANDS,
            ),
        )
    )

    frame = pd.DataFrame(rows)
    frame["target_ms"] = 100.0
    frame["within_target"] = frame["mean_ms"] <= frame["target_ms"]
    frame.to_csv(OUT / "performance_timings.csv", index=False)
    print(frame.to_string(index=False))
    render_path = frame[frame["stage"].str.contains("whole render-path")]
    print(
        f"\nrender-path cost: {float(render_path['mean_ms'].iloc[0]):.1f} ms "
        f"(target <= 100 ms)"
    )


if __name__ == "__main__":
    main()
