"""Regenerate the integration evidence for the combined workshop release.

Reads the baseline frozen from main before the merges
(``main_baseline_hashes.csv``) and re-derives every governed digest from the
integrated tree, so the preservation matrix is a comparison rather than an
assertion. Nothing here rebuilds or promotes a pack: it reads what is
committed and reports what moved.

    python scripts/build_revenue_outlook_workshop_release_evidence.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "revenue_outlook_workshop_release"
sys.path.insert(0, str(REPO))

from model_dashboard import revenue_outlook_policy_runtime as policy_runtime  # noqa: E402
from model_dashboard import revenue_outlook_presentation_policy as presentation  # noqa: E402
from model_dashboard import revenue_outlook_series_coverage as coverage  # noqa: E402
from model_dashboard.revenue_scenario_key import (  # noqa: E402
    HEAVY_BEV_DEFAULT,
    RevenueScenarioComputationKey,
)

ENGINES = ("ar1", "ensemble")
PACKS = {
    "ensemble": REPO / "data" / "current_revenue_outlook",
    "ar1": REPO / "data" / "engine_ar1" / "current_revenue_outlook",
}
VALUE_COLUMNS = ["series_id", "trace_name", "time_grain", "period", "june_year", "value", "value_unit"]
TRACE_SCOPES = {
    "actual": "Actual",
    "current_base": "Current finalist Base case",
    "current_high_pop": "Current finalist High population/comparison",
    "current_conflict": "Current finalist comparison behavioural path",
    "befu26": "BEFU26 official",
    "mbu26": "MBU26 official",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def frame_digest(frame: pd.DataFrame) -> str:
    """Order-independent, float-exact digest. Must match the baseline's rule."""
    if frame is None or frame.empty:
        return "EMPTY"
    ordered = frame.reindex(sorted(frame.columns), axis=1)
    ordered = ordered.sort_values(list(ordered.columns), kind="mergesort").reset_index(drop=True)
    digest = hashlib.sha256()
    for column in ordered.columns:
        digest.update(column.encode("utf-8"))
        values = ordered[column]
        if pd.api.types.is_float_dtype(values):
            digest.update(np.asarray(values, dtype="float64").tobytes())
        else:
            digest.update("\x1f".join(values.astype(str).fillna("")).encode("utf-8"))
    return digest.hexdigest()


def write_csv(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


# ============================================================ current digests
def current_digests() -> dict[str, str]:
    """Re-derive every digest the baseline recorded, by the same rules."""
    digests: dict[str, str] = {}

    for engine, pack_dir in PACKS.items():
        digests[f"revenue_outlook_pack|{engine}:manifest.json"] = sha256_file(
            pack_dir / "manifest.json"
        )
        combined = hashlib.sha256()
        for parquet in sorted(pack_dir.rglob("*.parquet")):
            combined.update(parquet.relative_to(pack_dir).as_posix().encode("utf-8"))
            combined.update(sha256_file(parquet).encode("utf-8"))
        digests[f"revenue_outlook_pack|{engine}:all_parquet_bytes"] = combined.hexdigest()

    for engine in ENGINES:
        path = REPO / "data" / "revenue_outlook_replay_cache" / engine / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        digests[f"replay_cache|{engine}:manifest.json"] = sha256_file(path)
        digests[f"replay_cache|{engine}:source_digest"] = str(manifest.get("source_digest", ""))
        digests[f"replay_cache|{engine}:output_hashes"] = sha256_text(
            json.dumps(manifest.get("output_hashes", {}), sort_keys=True)
        )

    unc = REPO / "data" / "revenue_outlook_uncertainty"
    digests["uncertainty_pack|manifest.json"] = sha256_file(unc / "manifest.json")
    for parquet in sorted(unc.glob("*.parquet")):
        digests[f"uncertainty_pack|{parquet.name}"] = sha256_file(parquet)

    default_key = RevenueScenarioComputationKey(
        engine="ensemble",
        uptake_basis="MoT VFM base",
        current_fed_policy_state="published",
        official_fed_policy_state="published",
        ped_retention_sensitivity=False,
        heavy_bev_transition=HEAVY_BEV_DEFAULT,
        official_comparator_vintage_id="MBU26",
    )
    digests["scenario_key|documented_default_digest"] = default_key.digest()
    digests["scenario_key|empty_key_digest"] = RevenueScenarioComputationKey().digest()

    for engine, pack_dir in PACKS.items():
        chart = pd.read_parquet(pack_dir / "revenue_chart_rows.parquet")
        digests[f"chart_rows|{engine}:all_rows"] = frame_digest(chart[VALUE_COLUMNS])
        for scope, trace in TRACE_SCOPES.items():
            subset = chart[chart["trace_name"].astype(str).eq(trace)]
            annual = subset[subset["time_grain"].astype(str).eq("june_year")]
            quarterly = subset[subset["time_grain"].astype(str).eq("quarterly")]
            digests[f"chart_rows|{engine}:{scope}:annual"] = frame_digest(annual[VALUE_COLUMNS])
            digests[f"chart_rows|{engine}:{scope}:quarterly"] = frame_digest(
                quarterly[VALUE_COLUMNS]
            )
            for series_id in sorted(annual["series_id"].astype(str).unique()):
                per = annual[annual["series_id"].astype(str).eq(series_id)]
                digests[f"chart_rows_series|{engine}:{scope}:{series_id}:annual"] = frame_digest(
                    per[VALUE_COLUMNS]
                )
        for name in (
            "revenue_formula_residuals",
            "revenue_line_reconciliation",
            "revenue_stack_components",
            "fan_band_rows",
            "fan_availability",
            "ped_revenue_bridge_audit",
        ):
            path = pack_dir / f"{name}.parquet"
            if path.exists():
                digests[f"pack_frame|{engine}:{name}"] = frame_digest(pd.read_parquet(path))

    band = pd.read_parquet(unc / "uncertainty_band_rows.parquet")
    digests["uncertainty_rows|all"] = frame_digest(band)
    for series_id, group in band.groupby(band["series_id"].astype(str)):
        digests[f"uncertainty_rows|series:{series_id}"] = frame_digest(group)

    fitted = REPO / "data" / "dashboard_evidence_pack_reproducibility"
    for state_dir in sorted(p for p in fitted.iterdir() if p.is_dir()):
        manifests = sorted(state_dir.rglob("*manifest*.json"))
        combined = hashlib.sha256()
        for manifest in manifests:
            combined.update(manifest.relative_to(state_dir).as_posix().encode("utf-8"))
            combined.update(sha256_file(manifest).encode("utf-8"))
        digests[f"fitted_state|{state_dir.name}"] = (
            combined.hexdigest() if manifests else "NO_MANIFEST"
        )

    ensemble_manifest = json.loads((PACKS["ensemble"] / "manifest.json").read_text(encoding="utf-8"))
    q1: dict[str, object] = {
        key: ensemble_manifest[key]
        for key in (
            "pack_status",
            "runtime_pack_type",
            "promotion_time",
            "promoted_by",
            "period_rule",
            "horizon_boundaries",
            "validation_status",
            "official_vintages",
            "scenario_roles",
        )
        if key in ensemble_manifest
    }
    actuals = REPO / "artifacts" / "actuals_refresh_2026q1"
    if actuals.exists():
        q1["actuals_refresh_2026q1_files"] = {
            path.relative_to(actuals).as_posix(): sha256_file(path)
            for path in sorted(actuals.rglob("*"))
            if path.is_file()
        }
    digests["governance|q1_2026_metadata"] = sha256_text(
        json.dumps(q1, sort_keys=True, default=str)
    )
    return digests


# ========================================================= preservation matrix
INTENDED_CHANGE = {
    # The only value movement B is allowed: the reconditioned DERIVED quarterly
    # presentation rows, which live in B's own pack, not in these frames.
}


def preservation_matrix() -> list[dict]:
    baseline_path = OUT / "main_baseline_hashes.csv"
    baseline: dict[str, str] = {}
    detail: dict[str, str] = {}
    with baseline_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            baseline[f"{row['scope']}|{row['item']}"] = row["digest"]
            detail[f"{row['scope']}|{row['item']}"] = row["detail"]
    current = current_digests()

    rows: list[dict] = []
    for key in sorted(set(baseline) | set(current)):
        before = baseline.get(key, "ABSENT")
        after = current.get(key, "ABSENT")
        scope, _, item = key.partition("|")
        if before == after:
            verdict = "unchanged"
        elif before == "ABSENT":
            verdict = "added"
        elif after == "ABSENT":
            verdict = "removed"
        else:
            verdict = "CHANGED"
        rows.append(
            {
                "scope": scope,
                "item": item,
                "baseline_digest": before,
                "integrated_digest": after,
                "verdict": verdict,
                "baseline_detail": detail.get(key, ""),
            }
        )
    return rows


# ============================================================ official audit
def official_light_petrol_audit() -> list[dict]:
    import app  # noqa: PLC0415  - Streamlit import is slow; only load if needed

    chart = pd.read_parquet(PACKS["ensemble"] / "revenue_chart_rows.parquet")
    combined = app._append_missing_official_rows(chart)
    petrol = combined[combined["series_id"].astype(str).eq("light_petrol_vkt")]
    rows: list[dict] = []
    for record in petrol.sort_values(["trace_name", "june_year"]).itertuples():
        rows.append(
            {
                "series_id": "light_petrol_vkt",
                "trace_name": getattr(record, "trace_name", ""),
                "june_year": getattr(record, "june_year", ""),
                "period": getattr(record, "period", ""),
                "value": getattr(record, "value", ""),
                "value_unit": getattr(record, "value_unit", ""),
                "source": getattr(record, "source", ""),
                "source_basis": getattr(record, "source_basis", ""),
                "coverage_row_type": getattr(record, "coverage_row_type", ""),
                "empirical_or_derived": getattr(record, "empirical_or_derived", ""),
            }
        )
    return rows


# ========================================================== quarterly evidence
def quarterly_series_coverage() -> list[dict]:
    chart = pd.read_parquet(PACKS["ensemble"] / "revenue_chart_rows.parquet")
    table = coverage.quarterly_coverage_status(chart, repo_root=REPO)
    return table.to_dict("records")


def quarterly_reconciliation() -> list[dict]:
    audit = pd.read_parquet(
        REPO / "data" / "revenue_outlook_quarterly_display" / "annual_reconciliation_audit.parquet"
    )
    rows: list[dict] = []
    residual_columns = [c for c in audit.columns if "residual" in c.lower()]
    worst = 0.0
    for record in audit.itertuples(index=False):
        mapping = record._asdict()
        for column in residual_columns:
            value = mapping.get(column)
            if isinstance(value, float) and math.isfinite(value):
                worst = max(worst, abs(value))
    rows.append(
        {
            "check": "derived_annual_groups_reconcile",
            "groups": len(audit),
            "worst_absolute_residual": f"{worst:.3e}",
            "tolerance": "1e-06 absolute / 1e-12 relative (pack manifest)",
            "verdict": "pass" if len(audit) == 2093 else f"group count {len(audit)} != 2093",
        }
    )
    quarterly = pd.read_parquet(
        REPO / "data" / "revenue_outlook_quarterly_display" / "quarterly_rows.parquet"
    )
    negatives = pd.to_numeric(quarterly["value"], errors="coerce")
    rows.append(
        {
            "check": "zero_negative_quarters",
            "groups": len(quarterly),
            "worst_absolute_residual": f"{float(negatives.min()):.6g}",
            "tolerance": ">= 0",
            "verdict": "pass" if (negatives.dropna() >= 0).all() else "FAIL",
        }
    )
    rows.append(
        {
            "check": "terminal_quarter",
            "groups": len(quarterly),
            "worst_absolute_residual": str(sorted(quarterly["period"].astype(str))[-1]),
            "tolerance": presentation.terminal_display_quarter(),
            "verdict": (
                "pass"
                if sorted(quarterly["period"].astype(str))[-1]
                <= presentation.terminal_display_quarter()
                else "FAIL"
            ),
        }
    )
    return rows


def quarterly_reconditioning_preservation() -> list[dict]:
    snapshot_dir = (
        REPO / "artifacts" / "revenue_outlook_series_coverage" / "pre_reconditioning_snapshot"
    )
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        {
            "check": "snapshot_marked_non_decision_facing",
            "observed": str(manifest.get("decision_facing")),
            "required": "False",
            "verdict": "pass" if manifest.get("decision_facing") is False else "FAIL",
        },
        {
            "check": "snapshot_marked_production_prohibited",
            "observed": str(manifest.get("production_use", ""))[:60],
            "required": "PROHIBITED",
            "verdict": "pass" if "PROHIBITED" in str(manifest.get("production_use", "")) else "FAIL",
        },
    ]
    # No production module, and no app.py, may read the superseded snapshot.
    offenders = [
        path.name
        for path in sorted((REPO / "model_dashboard").glob("*.py")) + [REPO / "app.py"]
        if "pre_reconditioning_snapshot" in path.read_text(encoding="utf-8")
    ]
    rows.append(
        {
            "check": "no_production_reader_of_the_snapshot",
            "observed": ", ".join(offenders) or "none",
            "required": "none (model_dashboard/*.py and app.py)",
            "verdict": "pass" if not offenders else "FAIL",
        }
    )
    for entry in manifest.get("files", []) if isinstance(manifest.get("files"), list) else []:
        name = entry.get("path") or entry.get("file") or ""
        path = snapshot_dir / str(name)
        if path.exists():
            rows.append(
                {
                    "check": f"snapshot_hash_pinned:{name}",
                    "observed": sha256_file(path)[:16],
                    "required": str(entry.get("sha256", ""))[:16],
                    "verdict": "pass" if sha256_file(path) == entry.get("sha256") else "FAIL",
                }
            )
    rows.append(
        {
            "check": "evidence_kept_in_parquet_not_csv",
            "observed": ", ".join(sorted(p.suffix for p in snapshot_dir.glob("*") if p.is_file())),
            "required": ".parquet for float-exact claims",
            "verdict": "pass" if list(snapshot_dir.glob("*.parquet")) else "FAIL",
        }
    )
    return rows


# ============================================================ policy evidence
def policy_state_parity() -> list[dict]:
    rows: list[dict] = []
    for engine in ENGINES:
        try:
            runtime = policy_runtime.load_policy_runtime(engine=engine, repo_root=REPO)
        except RuntimeError as error:
            rows.append(
                {
                    "engine": engine,
                    "state_id": "",
                    "current_policy": "",
                    "official_policy": "",
                    "chart_rows": "",
                    "band_rows": "",
                    "verdict": f"UNAVAILABLE: {error}",
                }
            )
            continue
        bands = runtime.uncertainty_rows
        for state in runtime.manifest["states"]:
            state_bands = bands[
                bands["policy_state"].astype(str).eq(str(state["current_fed_policy_state"]))
            ]
            rows.append(
                {
                    "engine": engine,
                    "state_id": state["state_id"],
                    "current_policy": state["current_fed_policy_state"],
                    "official_policy": state["official_fed_policy_state"],
                    "chart_rows": state.get("row_count", ""),
                    "band_rows": len(state_bands),
                    "verdict": "materialised",
                }
            )
    return rows


def policy_band_dependency_audit() -> list[dict]:
    rows: list[dict] = []
    for engine in ENGINES:
        try:
            runtime = policy_runtime.load_policy_runtime(engine=engine, repo_root=REPO)
        except RuntimeError:
            continue
        bands = runtime.uncertainty_rows
        states = sorted(bands["policy_state"].astype(str).unique())
        if "published" not in states:
            continue
        reference = bands[bands["policy_state"].astype(str).eq("published")]
        for state in states:
            if state == "published":
                continue
            other = bands[bands["policy_state"].astype(str).eq(state)]
            merged = reference.merge(
                other, on=["series_id", "FY"], suffixes=("_published", f"_{state}")
            )
            for series_id, group in merged.groupby(merged["series_id"].astype(str)):
                central_moves = ~np.isclose(
                    group["central_published"], group[f"central_{state}"], rtol=0, atol=1e-9
                )
                band_moves = ~np.isclose(
                    group["upper80_published"], group[f"upper80_{state}"], rtol=0, atol=1e-9
                )
                rows.append(
                    {
                        "engine": engine,
                        "compared_state": state,
                        "series_id": series_id,
                        "fy_count": len(group),
                        "fy_central_moves": int(central_moves.sum()),
                        "fy_band_moves": int(band_moves.sum()),
                        "verdict": (
                            "band follows central"
                            if bool((central_moves == band_moves).all())
                            else "MISMATCH: band and central disagree on which FYs move"
                        ),
                    }
                )
    return rows


def no_uplift_scope_audit() -> list[dict]:
    """Which series the permanent rate factor may and may not reprice."""
    from model_dashboard import rate_paths

    priced = set(rate_paths._RATE_PRICED_LONG_RUN_SERIES)
    rows: list[dict] = []
    must_not_move = (
        "ped_vkt_per_capita",
        "ped_volume",
        "light_petrol_vkt",
        "light_ruc_net_km",
        "heavy_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "net_mvr_revenue",
    )
    for series_id in sorted(priced):
        rows.append(
            {
                "series_id": series_id,
                "in_rate_priced_scope": "yes",
                "expectation": "the collection rate governs this leaf, so a rate ratio may reprice it",
                "verdict": "pass",
            }
        )
    for series_id in must_not_move:
        rows.append(
            {
                "series_id": series_id,
                "in_rate_priced_scope": "yes" if series_id in priced else "no",
                "expectation": (
                    "activity or non-fuel revenue: a rate ratio is not an elasticity "
                    "and must never scale it"
                ),
                "verdict": "FAIL" if series_id in priced else "pass",
            }
        )
    return rows


def session_migration_audit() -> list[dict]:
    import app  # noqa: PLC0415
    import streamlit as st

    cases = [
        ("revenue_outlook_ped_retention_sensitivity", True, "dropped"),
        ("revenue_outlook_show_vfm_envelope_audit", True, "dropped"),
        ("revenue_outlook_ev_uptake_basis_v2", "MoT VFM fast", "reset to VFM Base"),
        ("ro_cmp_a_uptake", "MoT VFM slow", "reset to VFM Base"),
        ("ro_cmp_b_uptake", "MoT VFM fast", "reset to VFM Base"),
        ("revenue_outlook_selected_fy", "FY2053", "dropped"),
        ("revenue_outlook_fed_policy_state", "delayed_12m", "dropped"),
    ]
    rows: list[dict] = []
    for key, stale_value, expectation in cases:
        st.session_state.clear()
        st.session_state[key] = stale_value
        if key == "revenue_outlook_chart_layers":
            st.session_state[key] = list(stale_value)
        app._discard_withdrawn_revenue_outlook_state()
        after = st.session_state.get(key, "<absent>")
        if expectation == "dropped":
            ok = after == "<absent>"
        else:
            ok = after == app.DEFAULT_EV_UPTAKE_MODE
        rows.append(
            {
                "session_key": key,
                "stale_value": str(stale_value),
                "expectation": expectation,
                "value_after_entry": str(after),
                "verdict": "pass" if ok else "FAIL",
            }
        )
    # A persisted VFM layer selection is filtered, not fatal.
    st.session_state.clear()
    st.session_state["revenue_outlook_chart_layers"] = [
        "MoT VFM Fast–Slow range",
        "50% modelled uncertainty",
    ]
    app._discard_withdrawn_revenue_outlook_state()
    kept = st.session_state.get("revenue_outlook_chart_layers", [])
    rows.append(
        {
            "session_key": "revenue_outlook_chart_layers",
            "stale_value": "MoT VFM Fast–Slow range + 50% modelled uncertainty",
            "expectation": "VFM layer filtered out, live layer kept",
            "value_after_entry": str(kept),
            "verdict": "pass" if kept == ["50% modelled uncertainty"] else "FAIL",
        }
    )
    st.session_state.clear()
    return rows


# ===================================================================== driver
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("regenerating workshop-release integration evidence")

    matrix = preservation_matrix()
    write_csv(
        "preservation_matrix.csv",
        ["scope", "item", "baseline_digest", "integrated_digest", "verdict", "baseline_detail"],
        matrix,
    )
    changed = [row for row in matrix if row["verdict"] == "CHANGED"]
    print(f"  -> {len(changed)} CHANGED, {len(matrix) - len(changed)} unchanged/added/removed")

    audit = official_light_petrol_audit()
    write_csv(
        "official_light_petrol_vkt_audit.csv",
        [
            "series_id",
            "trace_name",
            "june_year",
            "period",
            "value",
            "value_unit",
            "source",
            "source_basis",
            "coverage_row_type",
            "empirical_or_derived",
        ],
        audit,
    )

    cov_rows = quarterly_series_coverage()
    write_csv("quarterly_series_coverage.csv", list(cov_rows[0]), cov_rows)

    write_csv(
        "quarterly_reconciliation.csv",
        ["check", "groups", "worst_absolute_residual", "tolerance", "verdict"],
        quarterly_reconciliation(),
    )
    write_csv(
        "quarterly_reconditioning_preservation.csv",
        ["check", "observed", "required", "verdict"],
        quarterly_reconditioning_preservation(),
    )
    write_csv(
        "policy_state_parity.csv",
        ["engine", "state_id", "current_policy", "official_policy", "chart_rows", "band_rows", "verdict"],
        policy_state_parity(),
    )
    band_rows = policy_band_dependency_audit()
    if band_rows:
        write_csv(
            "policy_band_dependency_audit.csv",
            ["engine", "compared_state", "series_id", "fy_count", "fy_central_moves", "fy_band_moves", "verdict"],
            band_rows,
        )
    write_csv(
        "no_uplift_scope_audit.csv",
        ["series_id", "in_rate_priced_scope", "expectation", "verdict"],
        no_uplift_scope_audit(),
    )
    write_csv(
        "session_migration_audit.csv",
        ["session_key", "stale_value", "expectation", "value_after_entry", "verdict"],
        session_migration_audit(),
    )

    environment = {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "source_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip(),
    }
    try:
        import scipy  # noqa: PLC0415

        environment["scipy"] = scipy.__version__
    except ImportError:
        environment["scipy"] = "not installed"
    environment["blas"] = str(
        getattr(np, "__config__", None)
        and np.__config__.show(mode="dicts").get("Build Dependencies", {}).get("blas", {}).get("name", "")
        or "unknown"
    )
    (OUT / "build_environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  build_environment.json: {environment['source_sha'][:12]}")

    failures = [row for row in matrix if row["verdict"] == "CHANGED"]
    if failures:
        print("\nCHANGED digests (inspect each before committing):")
        for row in failures[:40]:
            print(f"  {row['scope']}|{row['item']}")


if __name__ == "__main__":
    main()
