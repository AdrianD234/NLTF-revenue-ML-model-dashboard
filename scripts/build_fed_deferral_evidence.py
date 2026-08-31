"""Build the committed evidence pack for the 6-36 month 12c deferral feature.

Writes, under artifacts/fed_deferral_duration/:
  * policy_state_registry.csv    - the canonical registry, one row per state;
  * quarterly_rate_paths.csv     - the governed quarterly schedule, all states;
  * scenario_matrix_inventory.csv - the 52 public paths with full metadata;
  * interaction_test_matrix.csv  - representative multi-lever combinations
    run through the production overlay chain, with the gates each satisfied;
  * source_manifest.json         - SHA, generator and source hashes.

Run from the repository root with the development venv:
    python scripts/build_fed_deferral_evidence.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "artifacts" / "fed_deferral_duration"


def build_registry_csv() -> pd.DataFrame:
    from model_dashboard.fed_policy_states import FED_POLICY_SPECS

    rows = []
    for spec in FED_POLICY_SPECS:
        rows.append(
            {
                "state_id": spec.state_id,
                "calculation_state_id": spec.calculation_state_id,
                "label": spec.label,
                "delay_months": spec.delay_months,
                "delay_quarters": spec.delay_quarters,
                "start_period": spec.start_period,
                "display_order": spec.display_order,
                "is_published": spec.is_published,
                "is_no_uplift": spec.is_no_uplift,
                "is_bespoke": spec.is_bespoke,
                "schedule_kind": spec.schedule_kind,
                "schedule_column": spec.schedule_column,
                "path_suffix": spec.path_suffix,
                "pair_state_suffix": spec.pair_state_suffix,
                "timing_id": spec.timing_id,
                "timing_label": spec.timing_label,
                "direct_affected_quarters": (
                    ";".join(spec.direct_affected_quarters())
                    if spec.is_finite_deferral
                    else (
                        "2027Q1_onward"
                        if spec.is_no_uplift
                        else ("derived_from_governed_schedule" if spec.is_bespoke else "")
                    )
                ),
                "note": spec.note,
            }
        )
    return pd.DataFrame(rows)


def build_quarterly_csv() -> pd.DataFrame:
    from model_dashboard.rate_paths import ped_quarterly_rate_schedules

    return ped_quarterly_rate_schedules(REPO_ROOT).reset_index()


def build_matrix_inventory() -> pd.DataFrame:
    from scripts.materialize_conflict_scenario_extract import (
        _export_paths,
        _path_metadata_frame,
    )

    return _path_metadata_frame(_export_paths())


def build_interaction_matrix() -> pd.DataFrame:
    import app
    from model_dashboard.engine import ENGINE_AR1, engine_revenue_outlook_dir
    from model_dashboard.fed_policy_states import policy_spec
    from model_dashboard.revenue_outlook import (
        PED_BRIDGE_DEFAULT_MODE,
        load_revenue_outlook_pack,
        revenue_outlook_signature,
    )
    from scripts.build_revenue_outlook_policy_runtime import governed_key

    app.POLICY_RUNTIME_FAST_PATH_ENABLED = False
    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(ENGINE_AR1)
    pack = load_revenue_outlook_pack(pack_dir, repo_root=REPO_ROOT)
    signature = revenue_outlook_signature(pack_dir, REPO_ROOT)

    def overlay(state: str, *, fleet="Off", pt="Off", freight="Off", demand="Off",
                uptake=None, eruc=(), population_trace=False) -> pd.DataFrame:
        sensitivity_key = app.selected_sensitivity_key(fleet, pt, demand, freight_rail_shift=freight)
        key = governed_key(pack, ENGINE_AR1, state, "published")
        changes = {}
        if uptake:
            changes["uptake_basis"] = uptake
        if eruc:
            changes["eruc_levers"] = eruc
        if changes:
            key = key.replace(**changes)
        rows, _u, _e, _p, _s = app.cached_scenario_overlay_rows(
            signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, key, pack
        )
        return rows

    def annual(rows: pd.DataFrame, trace: str, series_id: str) -> dict[int, float]:
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["trace_name"].astype(str).eq(trace)
            & rows["series_id"].astype(str).eq(series_id)
        ]
        fy = pd.to_numeric(selected["june_year"], errors="coerce")
        value = pd.to_numeric(selected["value"], errors="coerce")
        return {int(y): float(v) for y, v in zip(fy, value, strict=True) if pd.notna(y) and pd.notna(v)}

    eruc = (2027.0, 3.0, 1.0, -0.15, 2.70)
    combos = [
        # (label, state, kwargs, trace)
        ("6m + defaults", "delayed_6m", {}, "Current finalist Base case"),
        ("12m + defaults", "delayed_12m", {}, "Current finalist Base case"),
        ("18m + PT High + Fleet High", "delayed_18m", {"fleet": "High", "pt": "High"}, "Current finalist Base case"),
        ("24m + VFM Fast + e-RUC On", "delayed_24m", {"uptake": "MoT VFM fast", "eruc": eruc}, "Current finalist Base case"),
        ("30m + High conflict", "delayed_30m", {}, "Middle East conflict: High"),
        ("30m + High population", "delayed_30m", {}, "Current finalist High population/comparison"),
        ("36m + Freight High + PT Med", "delayed_36m", {"fleet": "Off", "pt": "Med", "freight": "High"}, "Current finalist Base case"),
        ("off + defaults", "off", {}, "Current finalist Base case"),
        ("6m + Fleet High", "delayed_6m", {"fleet": "High"}, "Current finalist Base case"),
        ("12m + demand elasticity Med", "delayed_12m", {"demand": "Med"}, "Current finalist Base case"),
        ("18m + VFM Slow", "delayed_18m", {"uptake": "MoT VFM slow"}, "Current finalist Base case"),
        ("24m + e-RUC On", "delayed_24m", {"eruc": eruc}, "Current finalist Base case"),
        ("36m + defaults", "delayed_36m", {}, "Current finalist Base case"),
    ]

    published_cache: dict[tuple, pd.DataFrame] = {}
    records = []
    for label, state, kwargs, trace in combos:
        cache_key = tuple(sorted((k, str(v)) for k, v in kwargs.items()))
        if cache_key not in published_cache:
            published_cache[cache_key] = overlay("published", **kwargs)
        published_rows = published_cache[cache_key]
        policy_rows = overlay(state, **kwargs)
        spec = policy_spec(state)
        window_fys = sorted(
            {
                int(q.split("Q")[0]) + (1 if int(q.split("Q")[1]) >= 3 else 0)
                for q in (spec.direct_affected_quarters() if spec.is_finite_deferral else ())
            }
        ) or [2027, 2028, 2029, 2030]
        mvr_policy = annual(policy_rows, trace, "net_mvr_revenue")
        mvr_published = annual(published_rows, trace, "net_mvr_revenue")
        mvr_invariant = max(
            abs(mvr_policy[fy] - mvr_published[fy])
            for fy in set(mvr_policy) & set(mvr_published)
        )
        fed_policy = annual(policy_rows, trace, "net_fed_revenue")
        fed_published = annual(published_rows, trace, "net_fed_revenue")
        ruc_policy = annual(policy_rows, trace, "total_ruc_net_revenue")
        ruc_published = annual(published_rows, trace, "total_ruc_net_revenue")
        total_policy = annual(policy_rows, trace, "total_nltf_net_revenue")
        total_published = annual(published_rows, trace, "total_nltf_net_revenue")
        # Strict in FY2027 (a taxed base always exists there); later window
        # years may legitimately be equal when another lever has removed the
        # taxed base entirely (e.g. e-RUC migrates the petrol fleet off
        # excise, leaving no wedge to defer).
        window_moves = all(
            (
                fed_policy[fy] < fed_published[fy]
                and ruc_policy[fy] < ruc_published[fy]
                if fy == 2027
                else fed_policy[fy] <= fed_published[fy] + 1e-9
                and ruc_policy[fy] <= ruc_published[fy] + 1e-9
            )
            for fy in window_fys
            if fy in fed_policy and fy in fed_published
        )
        closure = max(
            abs(
                (total_policy[fy] - total_published[fy])
                - (fed_policy[fy] - fed_published[fy])
                - (ruc_policy[fy] - ruc_published[fy])
            )
            for fy in set(total_policy) & set(total_published)
        )
        records.append(
            {
                "combination": label,
                "policy_state": state,
                "trace": trace,
                "fleet": kwargs.get("fleet", "Off"),
                "pt": kwargs.get("pt", "Off"),
                "freight": kwargs.get("freight", "Off"),
                "demand_elasticity": kwargs.get("demand", "Off"),
                "uptake_basis": kwargs.get("uptake", "MoT VFM base"),
                "eruc_on": bool(kwargs.get("eruc")),
                "net_fed_fy2027_policy": fed_policy.get(2027),
                "net_fed_fy2027_published": fed_published.get(2027),
                "net_fed_fy2029_policy": fed_policy.get(2029),
                "net_fed_fy2029_published": fed_published.get(2029),
                "net_ruc_fy2029_policy": ruc_policy.get(2029),
                "total_fy2030_policy": total_policy.get(2030),
                "mvr_invariance_max_abs": mvr_invariant,
                "mvr_invariant_pass": mvr_invariant <= 1e-9,
                "direct_window_moves_down": window_moves,
                "total_closure_max_abs": closure,
                "closure_pass": closure <= 1e-6,
            }
        )
    return pd.DataFrame(records)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = build_registry_csv()
    registry.to_csv(OUT_DIR / "policy_state_registry.csv", index=False)
    quarterly = build_quarterly_csv()
    quarterly.to_csv(OUT_DIR / "quarterly_rate_paths.csv", index=False)
    inventory = build_matrix_inventory()
    inventory.to_csv(OUT_DIR / "scenario_matrix_inventory.csv", index=False)
    interactions = build_interaction_matrix()
    interactions.to_csv(OUT_DIR / "interaction_test_matrix.csv", index=False)

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha": head,
        "generator": "scripts/build_fed_deferral_evidence.py",
        "outputs": {},
        "source_hashes": {},
    }
    for name in (
        "policy_state_registry.csv",
        "quarterly_rate_paths.csv",
        "scenario_matrix_inventory.csv",
        "interaction_test_matrix.csv",
    ):
        manifest["outputs"][name] = hashlib.sha256((OUT_DIR / name).read_bytes()).hexdigest()
    for rel in (
        "data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv",
        "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv",
        "data/current_revenue_outlook/sensitivity_seed_inputs.csv",
        "model_dashboard/fed_policy_states.py",
    ):
        manifest["source_hashes"][rel] = hashlib.sha256(
            (REPO_ROOT / rel).read_bytes()
        ).hexdigest()
    (OUT_DIR / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    failures = interactions[
        ~(interactions["mvr_invariant_pass"] & interactions["direct_window_moves_down"] & interactions["closure_pass"])
    ]
    print(interactions[["combination", "mvr_invariant_pass", "direct_window_moves_down", "closure_pass"]].to_string(index=False))
    if not failures.empty:
        print(f"INTERACTION GATES FAILED on {len(failures)} combinations")
        return 1
    print(f"evidence written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
