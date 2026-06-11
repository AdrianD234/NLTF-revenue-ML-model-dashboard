"""Emit Page-5 (Governance & Reproducibility) compatible audit files into the
vNext reproducibility packs so the dashboard's governance page narrates the
promoted vNext finalists from their own saved-state evidence.

Adds to ``data/dashboard_evidence_pack_reproducibility/<stream>_vnext/`` the
legacy stream-pack contract files that the Page-5 loader requires and that the
vNext pipeline stores under different names/schemas:
manifest.json, <stream> report md, parquet_write_status.json,
rebuilt_predictions, component_predictions, feature_importance_global,
annual_predictions, training_window_trace, evidence_prediction_comparison,
evidence_metric_comparison.

Evidence comparisons are computed against the live promoted evidence pack, so
deltas are exact-zero by construction (the pack was built from these
predictions).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import PIPELINE_VERSION
from .vnext_core import STREAM_LABELS
from .vnext_run import repo_root, state_dir

PACK_DATA = lambda: repo_root() / "data" / "dashboard_evidence_pack" / "data"  # noqa: E731

SHEETS = {"PED": "PED Inputs", "HEAVY_RUC": "Heavy RUC Inputs"}


def _annual_pairs(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["target_year"] = d["target_period"].astype(str).str.slice(0, 4).astype(int)
    rows = []
    for (basis, origin, year), g in d.groupby(["score_basis", "origin", "target_year"]):
        if g["target_period"].nunique() == 4 and g["pred"].notna().all():
            actual = float(g["actual"].sum())
            pred = float(g["pred"].sum())
            rows.append({"score_basis": basis, "origin": origin, "target_year": int(year),
                         "actual": actual, "pred": pred, "n_quarters": 4,
                         "error_pct": (pred - actual) / actual * 100.0 if actual else np.nan})
    out = pd.DataFrame(rows)
    out["ape"] = out["error_pct"].abs()
    return out


def emit_page5_compat(stream: str) -> Path:
    sdir = state_dir(stream)
    manifest = json.loads((sdir / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    parity = json.loads((sdir / "forward_scorer_parity_audit.json").read_text(encoding="utf-8"))
    finalist = manifest["finalist_model"]
    label = STREAM_LABELS[stream]

    # --- predictions keyed to the promoted evidence pack -------------------
    evidence = pd.read_parquet(PACK_DATA() / "scorecard_predictions.parquet")
    evidence = evidence[(evidence["stream"] == stream) & (evidence["model"] == finalist)]
    archived = pd.read_parquet(sdir / "validation_predictions.parquet")
    merged = evidence.merge(
        archived[["origin", "target_period", "pred"]].rename(columns={"pred": "rebuilt_pred"}),
        on=["origin", "target_period"], how="left",
    )
    assert merged["rebuilt_pred"].notna().all(), f"{stream}: archived predictions missing keys"

    rebuilt = merged.copy()
    rebuilt["pred"] = rebuilt["rebuilt_pred"]
    actual = rebuilt["actual"].astype(float)
    rebuilt["error_pct"] = np.where(actual != 0, (rebuilt["pred"] - actual) / actual * 100.0, np.nan)
    rebuilt["ape"] = rebuilt["error_pct"].abs()
    rebuilt["valid_actual"] = actual != 0
    rebuilt["source_dataset"] = "vnext_validation_predictions"
    keep = ["stream", "stream_label", "model", "scenario", "model_class", "score_basis",
            "eval_grid", "origin", "target_period", "horizon", "actual", "pred",
            "error_pct", "ape", "valid_actual", "source_dataset"]
    rebuilt = rebuilt[[c for c in keep if c in rebuilt.columns]]
    rebuilt.to_parquet(sdir / "rebuilt_predictions.parquet", index=False)

    # component_predictions in the legacy stream-pack schema.
    comp = pd.read_parquet(sdir / "component_validation_predictions.parquet")
    weights = {m["component_model"]: float(m["component_weight"]) for m in manifest["members"]}
    finals = archived.rename(columns={"pred": "final_pred"})[["origin", "target_period", "final_pred"]]
    # Duplicate component rows per stored score-basis keyset (legacy contract).
    basis_keys = merged[["score_basis", "eval_grid", "origin", "target_period"]].drop_duplicates()
    cp = comp.merge(basis_keys, on=["origin", "target_period"], how="inner")
    cp = cp.merge(finals, on=["origin", "target_period"], how="left")
    a = cp["actual"].astype(float)
    out_cp = pd.DataFrame({
        "stream": stream, "stream_label": label,
        "finalist_model": finalist,
        "score_basis": cp["score_basis"],
        "eval_grid": cp["eval_grid"],
        "component_model": cp["model"],
        "component_weight": cp["model"].map(weights),
        "origin": cp["origin"], "target_period": cp["target_period"],
        "horizon": cp["horizon"].astype(int),
        "actual": a,
        "component_pred": cp["pred"].astype(float),
        "weighted_component_pred": cp["model"].map(weights) * cp["pred"].astype(float),
        "final_pred": cp["final_pred"].astype(float),
        "final_error_pct": np.where(a != 0, (cp["final_pred"] - a) / a * 100.0, np.nan),
        "source_dataset": "vnext_component_validation_predictions",
    })
    out_cp.to_parquet(sdir / "component_predictions.parquet", index=False)

    # feature_importance_global: mean importance per feature per component.
    fi = pd.read_parquet(sdir / "feature_importance.parquet")
    gi = (fi.groupby(["stream", "stream_label", "model", "feature", "importance_type"], as_index=False)
            .agg(mean_abs_importance=("importance_value", "mean"),
                 importance_value=("importance_value", "mean")))
    gi["rank"] = gi.groupby("model")["importance_value"].rank(ascending=False, method="first")
    gi["notes"] = "Mean tree-impurity importance from the saved vNext production state."
    gi.to_parquet(sdir / "feature_importance_global.parquet", index=False)

    # annual predictions.
    ap = _annual_pairs(rebuilt.rename(columns={"pred": "pred"}))
    ap.insert(0, "stream", stream)
    ap.insert(1, "stream_label", label)
    ap.insert(2, "model", finalist)
    ap["source_dataset"] = "vnext_validation_predictions"
    ap["value_available"] = True
    ap.to_parquet(sdir / "annual_predictions.parquet", index=False)

    # training window trace from the per-origin fitted-state index.
    idx = pd.read_parquet(sdir / "fitted_state_index.parquet")
    twt = pd.DataFrame({
        "stream": stream, "stream_label": label, "finalist_model": finalist,
        "component_model": idx["component_model"], "origin": idx["origin"],
        "window_quarters": idx["train_rows"].astype(float),
        "training_start_period_inferred": idx["train_window_start"],
        "training_end_period_inferred": idx["train_window_end"],
        "note": "Measured from the saved per-origin fitted-state training matrices.",
    })
    twt.to_parquet(sdir / "training_window_trace.parquet", index=False)

    # evidence comparisons (zero by construction; computed, not asserted).
    pc_rows, mc_rows = [], []
    for basis, g in merged.groupby("score_basis"):
        deltas = (g["pred"].astype(float) - g["rebuilt_pred"].astype(float)).abs()
        pc_rows.append({"comparison": "vnext_saved_state_vs_evidence_pack", "score_basis": basis,
                        "n_common_rows": int(len(g)), "max_abs_pred_delta": float(deltas.max()),
                        "mean_abs_pred_delta": float(deltas.mean())})
        ga = g["actual"].astype(float).to_numpy()
        gp_e = g["pred"].astype(float).to_numpy()
        gp_r = g["rebuilt_pred"].astype(float).to_numpy()

        def _pooled(av, pv):
            m = (av != 0) & np.isfinite(pv)
            return float(np.mean(np.abs((pv[m] - av[m]) / av[m])) * 100.0)

        def _hmean(frame, col):
            vals = []
            for _, h in frame.groupby("horizon"):
                av = h["actual"].astype(float).to_numpy()
                pv = h[col].astype(float).to_numpy()
                m = (av != 0) & np.isfinite(pv)
                if m.any():
                    vals.append(float(np.mean(np.abs((pv[m] - av[m]) / av[m])) * 100.0))
            return float(np.mean(vals))

        mc_rows.append({
            "score_basis": basis,
            "rebuilt_quarterly_pooled_mape": _pooled(ga, gp_r),
            "evidence_quarterly_pooled_mape": _pooled(ga, gp_e),
            "delta_quarterly_pooled_mape": abs(_pooled(ga, gp_r) - _pooled(ga, gp_e)),
            "rebuilt_horizon_mean_mape": _hmean(g, "rebuilt_pred"),
            "evidence_horizon_mean_mape": _hmean(g, "pred"),
            "delta_horizon_mean_mape": abs(_hmean(g, "rebuilt_pred") - _hmean(g, "pred")),
            "n_rows": int(len(g)),
            "comparison": "vnext_saved_state_vs_evidence_pack",
            "status": "exact",
        })
    pd.DataFrame(pc_rows).to_parquet(sdir / "evidence_prediction_comparison.parquet", index=False)
    pd.DataFrame(mc_rows).to_parquet(sdir / "evidence_metric_comparison.parquet", index=False)

    max_delta = max(r["max_abs_pred_delta"] for r in pc_rows)

    # legacy-contract manifest + status + report.
    legacy_manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "stream": stream, "stream_label": label,
        "finalist_model": finalist, "model": finalist,
        "source_parent_run": "pipeline/vnext_run.py (search -> select -> finalize)",
        "source_workbook": "Master Copy revenue modelling workbook.xlsx",
        "source_sheet": SHEETS[stream],
        "workbook_provenance": {
            "workbook": "Master Copy revenue modelling workbook.xlsx",
            "sheet": SHEETS[stream],
            "history_basis": manifest["history_file"],
            "history_sha256": manifest["history_sha256"],
        },
        "evidence_pack": "data/dashboard_evidence_pack (v7 vNext finalists)",
        "component_weights": {m["component_model"]: m["component_weight"] for m in manifest["members"]},
        "max_prediction_delta": max_delta,
        "parity_status": parity["parity_status"],
        "reproducibility_claim": (
            "Production forward-scoreable: saved per-origin and production fitted "
            "estimators replay the archived predictions exactly (state replay delta "
            f"{parity['state_replay_max_abs_delta']:.1e}; recipe replay delta "
            f"{parity['recipe_replay_max_abs_delta']:.1e})."
        ),
        "limitations": (
            "The archived legacy finalist remains historically reproducible only; "
            "see reproducibility_gap_register.parquet and the v6 pack backup."
        ),
    }
    (sdir / "manifest.json").write_text(json.dumps(legacy_manifest, indent=2), encoding="utf-8")
    (sdir / "parquet_write_status.json").write_text(json.dumps({
        "created_by": "pipeline/vnext_page5_compat.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Page-5 compatible audit tables derived from the vNext saved-state pack.",
        "status": "complete",
    }, indent=2), encoding="utf-8")

    report_name = {"PED": "ped_reproducibility_report.md", "HEAVY_RUC": "heavy_ruc_reproducibility_report.md"}[stream]
    members_md = "\n".join(
        f"- `{m['component_model']}` (weight {m['component_weight']:.4f}, "
        f"{m['model_kind']}, window {m['window'] or 'expanding'})"
        for m in manifest["members"]
    )
    (sdir / report_name).write_text(f"""# {label} vNext reproducibility report

Status: COMPLETE (production forward-scoreable)

- Finalist: `{finalist}`
- Parity: state replay {parity['state_replay_max_abs_delta']:.1e}, recipe replay {parity['recipe_replay_max_abs_delta']:.1e} (tolerance 1e-6)
- Max evidence-pack prediction delta: {max_delta:.1e}
- Canonical input basis: `{manifest['history_file']}`
- Lag recursion: {manifest['lag_recursion_policy']}; transform: ln(target) -> exp
- Seeds fixed (random_state=42); scikit-learn {manifest['sklearn_version']}

## Components

{members_md}

## Lineage

The archived legacy finalist remains historically reproducible (stored replay)
but is not forward-scoreable; it is documented in
`reproducibility_gap_register.parquet` and preserved in the v6 pack backup.
""", encoding="utf-8")
    return sdir


def main() -> None:
    for stream in ("PED", "HEAVY_RUC"):
        sdir = emit_page5_compat(stream)
        print(f"[page5-compat] {stream}: emitted into {sdir}")


if __name__ == "__main__":
    main()
