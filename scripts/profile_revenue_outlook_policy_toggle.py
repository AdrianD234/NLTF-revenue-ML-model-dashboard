"""Where the time actually goes when a reader changes the 12c policy control.

The handoff's premise was that the ~4 s overlay chain is caused by the policy
selection.  That is an assumption, not a measurement, so this script takes the
chain apart stage by stage and attributes each stage to one of three classes:

``key_independent``
    Paid once per process regardless of the selection (replay-cache load, the
    promoted-pack read, the FED factor tables).  A policy switch never re-pays
    it, so materialising it again buys nothing.

``policy_dependent``
    Re-runs on every policy change because ``current_fed_policy_state`` is part
    of the ``RevenueScenarioComputationKey`` the overlay cache is keyed on.

``display_only``
    Series / grain / trace filtering, which a policy change also invalidates
    today only because it sits downstream of the overlay cache.

Every measurement runs in a FRESH interpreter (``--worker``) so the first-touch
costs are real, and the driver replays the switch sequence the handoff named:
published -> delayed -> no uplift -> published, plus a return to a previously
selected state, for both engines.

    python scripts/profile_revenue_outlook_policy_toggle.py
    python scripts/profile_revenue_outlook_policy_toggle.py --engine ar1 --worker
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVIDENCE_DIR = REPO_ROOT / "artifacts" / "revenue_outlook_policy_runtime"
ENGINES = ("ar1", "ensemble")

# The switch sequence the handoff asked to be measured, in order. The fifth
# entry is the "repeated return to a previously selected state" case: it is the
# one a Streamlit cache should already answer, and measuring it separately is
# what tells us whether the cost is a cache MISS or a cache that is too small.
SWITCH_SEQUENCE = (
    ("published", "cold_first_selection"),
    ("delayed_6m", "published_to_delayed"),
    ("off", "delayed_to_no_uplift"),
    ("published", "no_uplift_to_published"),
    ("delayed_6m", "repeat_previously_selected"),
)

STAGE_CLASS = {
    "replay cache load": "key_independent",
    "promoted pack load": "key_independent",
    "sensitivity stage frames": "key_independent",
    "fed uplift factors": "key_independent",
    "macro overlay": "policy_dependent",
    "uptake allocation": "policy_dependent",
    "policy factor application": "policy_dependent",
    "conflict append": "policy_dependent",
    "detail alignment": "policy_dependent",
    "formula rebuild": "policy_dependent",
    "stack rebuild": "policy_dependent",
    "uncertainty lookup": "policy_dependent",
    "chart-row construction": "display_only",
}


def _stage_timer() -> tuple[list[tuple[str, float]], object]:
    stages: list[tuple[str, float]] = []

    def stage(label: str, function):
        mark = time.perf_counter()
        value = function()
        stages.append((label, (time.perf_counter() - mark) * 1000.0))
        return value

    return stages, stage


def _run_worker(engine: str) -> dict:
    """One fresh interpreter: cold load, then the five policy selections."""
    import logging
    import os

    os.environ.setdefault("REVENUE_OUTLOOK_RUNTIME_MODE", "fast")
    os.environ["REVENUE_OUTLOOK_CACHE_WARMER"] = "0"
    os.environ["DASHBOARD_ENGINE_DEFAULT"] = engine
    logging.getLogger("streamlit").setLevel(logging.ERROR)

    import pandas as pd  # noqa: PLC0415

    import app  # noqa: PLC0415
    from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: PLC0415
    from model_dashboard.revenue_outlook import (  # noqa: PLC0415
        PED_BRIDGE_DEFAULT_MODE,
        revenue_outlook_signature,
    )
    from model_dashboard.revenue_scenario_key import (  # noqa: PLC0415
        RevenueScenarioComputationKey,
    )

    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(engine)
    cold_stages, stage = _stage_timer()

    signature = stage(
        "pack signature", lambda: revenue_outlook_signature(pack_dir, REPO_ROOT)
    )
    pack = stage(
        "promoted pack load",
        lambda: app.cached_load_revenue_outlook_pack(
            str(pack_dir), str(REPO_ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
        ),
    )
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    stage(
        "replay cache load",
        lambda: (
            app.cached_treasury_baseline_macro_replay(signature, pack),
            app.cached_fuel_price_scenario_replay(signature, pack),
        ),
    )
    stage("fed uplift factors", lambda: app.cached_fed_uplift_factors(signature, pack))
    stage(
        "sensitivity stage frames",
        lambda: app.cached_sensitivity_stage_frames(
            signature, PED_BRIDGE_DEFAULT_MODE, sensitivity, pack
        ),
    )
    stage("uncertainty pack load", lambda: app.cached_uncertainty_pack())

    # The production key, not a bare one: leaving the official-vintage and
    # long-run fields empty selects a DIFFERENT scenario whose detail
    # alignment does not close (net_mvr_revenue disagrees at FY2031), so a
    # profile built on it would be timing a path no reader ever takes.
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}

    def key_for(policy: str) -> RevenueScenarioComputationKey:
        return RevenueScenarioComputationKey(
            engine=engine,
            uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
            current_fed_policy_state=policy,
            official_fed_policy_state=app.FED_POLICY_PUBLISHED,
            official_comparator_vintage_id=str(
                block.get("default_comparator_vintage_id") or "BEFU26"
            ),
            long_run_transition_schedule_id=str(
                block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
            ),
            long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
        )

    # ---------------------------------------------------------------- switches
    selections: list[dict] = []
    for policy, label in SWITCH_SEQUENCE:
        key = key_for(policy)
        mark = time.perf_counter()
        view = app.cached_revenue_outlook_view(
            signature,
            "Total NLTF revenue",
            "June-year",
            "Current planned path",
            ("Current Base",),
            sensitivity,
            PED_BRIDGE_DEFAULT_MODE,
            key,
            pack,
        )
        app.cached_aligned_scenario_detail_frames(
            signature, sensitivity, PED_BRIDGE_DEFAULT_MODE, key, pack
        )
        app.cached_uncertainty_band_rows(
            "total_nltf_net_revenue",
            str(app.cached_uncertainty_pack().manifest.get("scenario_key_digest", "")),
        )
        elapsed = (time.perf_counter() - mark) * 1000.0
        selections.append(
            {
                "policy_state": policy,
                "transition": label,
                "total_ms": elapsed,
                "chart_rows": int(len(view["chart_rows"])),
            }
        )

    # ------------------------------------------------- per-stage attribution
    # Replays the SAME chain with the Streamlit caches bypassed, so each stage
    # is measured on its own rather than inferred from a total. Uses a policy
    # state not yet computed above, so nothing is served warm by accident.
    breakdown_stages, bstage = _stage_timer()
    from model_dashboard.fuel_price_scenario import (  # noqa: PLC0415
        append_fuel_price_scenario_to_chart_rows,
        apply_treasury_macro_to_chart_rows,
    )
    from model_dashboard.mbu26_source_spine import (  # noqa: PLC0415
        revenue_formula_residual_frame,
    )
    from model_dashboard.revenue_outlook import (  # noqa: PLC0415
        revenue_stack_components_frame,
    )

    key = key_for("off")
    _, sensitivity_frames, _ = app.cached_sensitivity_stage_frames(
        signature, PED_BRIDGE_DEFAULT_MODE, sensitivity, pack
    )
    macro_replay = app.cached_treasury_baseline_macro_replay(signature, pack)
    fuel_replay = app.cached_fuel_price_scenario_replay(signature, pack)
    uplift_factors = app.cached_fed_uplift_factors(signature, pack)
    drift = app._pack_table(pack, "ev_phev_ped_light_drift_assumptions")

    rows = bstage(
        "macro overlay",
        lambda: apply_treasury_macro_to_chart_rows(
            sensitivity_frames["chart_rows"], macro_replay
        )[0],
    )
    rows = bstage(
        "uptake allocation",
        lambda: app._apply_scenario_overlays(
            rows,
            drift,
            app._resolve_ev_uptake_levers(key),
            app._resolve_eruc_levers(key),
            uplift_factors,
            adjust_ped=False,
            fed_policy_scopes=(),
            policy_pair_factors=pd.DataFrame(),
            uptake_basis=app._resolve_uptake_basis(key),
            heavy_bev_transition=app._heavy_bev_transition_enabled(key),
        )[0],
    )
    rows = bstage(
        "policy factor application",
        lambda: app._apply_scenario_overlays(
            rows,
            drift,
            None,
            None,
            uplift_factors,
            adjust_ped=False,
            fed_policy_scopes=app._fed_policy_scopes_for_key(key),
            policy_pair_factors=fuel_replay.policy_pair_factors,
        )[0],
    )
    rows = bstage(
        "conflict append",
        lambda: append_fuel_price_scenario_to_chart_rows(rows, fuel_replay)[0],
    )
    detail_frames = app.cached_revenue_outlook_detail_frames(
        signature, sensitivity, PED_BRIDGE_DEFAULT_MODE, pack
    )
    line = bstage(
        "detail alignment",
        lambda: app._align_detail_frame_to_chart_rows(
            detail_frames["line_reconciliation"],
            rows,
            fy_column="FY",
            series_column="series_id",
            value_column="value",
            source_path_column="source_path",
        ),
    )
    residuals = bstage("formula rebuild", lambda: revenue_formula_residual_frame(line))
    bstage("stack rebuild", lambda: revenue_stack_components_frame(line, residuals))
    bstage(
        "chart-row construction",
        lambda: app._filter_series_rows_with_fallback(
            rows, "Total NLTF revenue", "June-year", "Current planned path", ("Current Base",)
        ),
    )
    bstage(
        "uncertainty lookup",
        lambda: app.cached_uncertainty_band_rows(
            "total_ruc_net_revenue",
            str(app.cached_uncertainty_pack().manifest.get("scenario_key_digest", "")),
        ),
    )

    return {
        "engine": engine,
        "cold_stages": cold_stages,
        "cold_total_ms": sum(value for _, value in cold_stages),
        "selections": selections,
        "breakdown": breakdown_stages,
    }


def _fmt(value: float) -> str:
    return f"{value:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=ENGINES)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    if args.worker:
        if not args.engine:
            parser.error("--worker requires --engine")
        print("@@RESULT@@" + json.dumps(_run_worker(args.engine)))
        return 0

    records: list[dict] = []
    for engine in ENGINES:
        for index in range(args.repeats):
            print(f"  {engine} run {index + 1}/{args.repeats} ...", flush=True)
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--engine", engine, "--worker"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            line = next(
                line for line in completed.stdout.splitlines() if line.startswith("@@RESULT@@")
            )
            records.append(json.loads(line[len("@@RESULT@@") :]))

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    rows = ["engine,measurement,stage,class,median_ms,min_ms,max_ms,samples"]
    for engine in ENGINES:
        matching = [record for record in records if record["engine"] == engine]
        if not matching:
            continue
        for name in [stage for stage, _ in matching[0]["cold_stages"]]:
            values = [dict(record["cold_stages"])[name] for record in matching]
            rows.append(
                f'{engine},cold_process,"{name}",{STAGE_CLASS.get(name, "key_independent")},'
                f"{_fmt(statistics.median(values))},{_fmt(min(values))},{_fmt(max(values))},{len(values)}"
            )
        for name in [stage for stage, _ in matching[0]["breakdown"]]:
            values = [dict(record["breakdown"])[name] for record in matching]
            rows.append(
                f'{engine},stage_breakdown,"{name}",{STAGE_CLASS.get(name, "policy_dependent")},'
                f"{_fmt(statistics.median(values))},{_fmt(min(values))},{_fmt(max(values))},{len(values)}"
            )
        for index, (_policy, label) in enumerate(SWITCH_SEQUENCE):
            values = [record["selections"][index]["total_ms"] for record in matching]
            rows.append(
                f'{engine},policy_switch,"{label}",end_to_end,'
                f"{_fmt(statistics.median(values))},{_fmt(min(values))},{_fmt(max(values))},{len(values)}"
            )
    (EVIDENCE_DIR / "policy_toggle_profile_before.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    (EVIDENCE_DIR / "policy_toggle_profile_raw.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    print("\n".join(rows))
    print(f"\nwrote {(EVIDENCE_DIR / 'policy_toggle_profile_before.csv').as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
