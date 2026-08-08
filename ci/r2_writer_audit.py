"""Instrumented audit of one PED calibration-R² chart-source writer invocation.

Loads one evidence pack exactly the way the writers do, records every input
identity that could move the two published PED calibration R² values, and
verifies that the chart-source CSV written as a side effect carries the same
values the calculation produced.

Written for the Phase B diagnosis in docs/FOLLOW_UP_PED_R2_DRIFT.md: the
xdist run moved `calibration_r2` 0.5591936636031876 -> 0.5803595524485978 and
0.9230110422702978 -> 0.9448430187011027, and the byte-scan hypothesis is that
those are the ENSEMBLE and AR(1) engine identities respectively, racing on a
then-shared output destination.  This tool makes the identity of every
invocation observable so that hypothesis can be proven or refuted.

Usage (inside the nltf-ci:local container, cwd = repo root):

    python ci/r2_writer_audit.py --engine ensemble --out /probe/audit_ens.json \
        --chart-output-dir /probe/chart_ens
    python ci/r2_writer_audit.py --engine ar1 --out /probe/audit_ar1.json \
        --chart-output-dir /probe/chart_ar1

Never writes into the tracked tree: --chart-output-dir is mandatory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

# The audit may be bind-mounted anywhere (the probe driver mounts it at
# /harness); the repo root is the working directory the container runs in.
_SELF_ROOT = Path(__file__).resolve().parents[1]
ROOT = _SELF_ROOT if (_SELF_ROOT / "model_dashboard").exists() else Path.cwd()
sys.path.insert(0, str(ROOT))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_vector(values) -> str:
    import numpy as np

    array = np.ascontiguousarray(np.asarray(values, dtype=float))
    return hashlib.sha256(array.tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["ensemble", "ar1"], required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--chart-output-dir", required=True)
    args = parser.parse_args()

    chart_dir = Path(args.chart_output_dir).resolve()
    tracked = (ROOT / "artifacts" / "chart_sources").resolve()
    if chart_dir == tracked:
        raise SystemExit("refusing to write into the tracked chart-source directory")
    chart_dir.mkdir(parents=True, exist_ok=True)
    # The same override the test suite uses; explicit here so this audit can
    # never touch the governed destination whatever the process env held.
    os.environ["NLTF_CHART_SOURCE_OUTPUT_DIR"] = str(chart_dir)

    import numpy as np
    import pandas as pd

    from model_dashboard.engine import engine_evidence_root
    from model_dashboard.evidence_pack import load_evidence_pack
    from model_dashboard.r2_ladder import r2_ladder_frames

    evidence_root = engine_evidence_root(args.engine)
    data_dir = evidence_root / "data"

    source_hashes = {
        name: sha256_file(data_dir / name)
        for name in ("scorecard_predictions.parquet", "diagnostic_tests.parquet")
        if (data_dir / name).exists()
    }
    repro_root = ROOT / "data" / "dashboard_evidence_pack_reproducibility"
    for pack_dir in sorted(p for p in repro_root.iterdir() if p.is_dir()):
        for name in ("component_predictions.parquet", "training_fit_predictions.parquet"):
            path = pack_dir / name
            if path.exists():
                source_hashes[f"reproducibility/{pack_dir.name}/{name}"] = sha256_file(path)

    pack = load_evidence_pack(evidence_root, repo_root=ROOT)
    data = pack.data

    # ---- the writers' own calculation, via the authoritative library
    summary = r2_ladder_frames(data, repo_root=ROOT)["summary"]
    ped = summary[summary["stream_label"].astype(str).eq("PED VKT per capita")]
    computed = {
        str(row["score_basis"]): float(row["calibration_r2"])
        for _, row in ped.iterrows()
        if pd.notna(row.get("calibration_r2"))
    }

    # ---- independent reconstruction of the two paths, with numerators
    scorecard = data["scorecard_predictions"]
    selected = scorecard[
        scorecard["scenario"].astype(str).str.casefold().eq("finalist")
        & scorecard.get("valid_for_mape", pd.Series(True, index=scorecard.index))
        .fillna(True)
        .astype(bool)
        & scorecard["stream_label"].astype(str).eq("PED VKT per capita")
    ]
    reconstruction: dict[str, dict] = {}
    for basis, group in selected.groupby("score_basis"):
        actual = pd.to_numeric(group["actual"], errors="coerce")
        pred = pd.to_numeric(group["pred"], errors="coerce")
        keep = actual.notna() & pred.notna()
        actual = actual[keep].to_numpy(dtype=float)
        pred = pred[keep].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(pred)), pred])
        coefficients, *_ = np.linalg.lstsq(design, actual, rcond=None)
        fitted = design @ coefficients
        sse = float(np.sum((actual - fitted) ** 2))
        sst = float(np.sum((actual - actual.mean()) ** 2))
        reconstruction[str(basis)] = {
            "n_rows": int(len(actual)),
            "actual_sha256": sha256_vector(actual),
            "pred_sha256": sha256_vector(pred),
            "intercept": float(coefficients[0]),
            "slope": float(coefficients[1]),
            "sse": sse,
            "sst": sst,
            "mz_calibration_r2": 1.0 - sse / sst if sst > 0 else None,
        }

    diagnostics = data.get("diagnostic_tests")
    override = None
    if diagnostics is not None and "calibration_r2" in diagnostics.columns:
        rows = diagnostics[
            diagnostics["stream_label"].astype(str).eq("PED VKT per capita")
        ]
        if "role" in rows.columns:
            rows = rows[rows["role"].astype(str).str.contains("finalist", case=False)]
        if not rows.empty:
            override = {
                "stored_calibration_r2": float(rows.iloc[0]["calibration_r2"]),
                "default_score_basis": str(
                    rows.iloc[0].get("default_score_basis", "<absent>")
                ),
                "model": str(rows.iloc[0].get("model", "<absent>")),
            }

    # ---- what the side-effect write actually published
    written = {}
    ladder_csv = chart_dir / "r2_ladder_summary.csv"
    if ladder_csv.exists():
        with ladder_csv.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("stream_label") == "PED VKT per capita":
                    written[row.get("score_basis", "")] = {
                        "calibration_r2": row.get("calibration_r2"),
                        "model": row.get("model"),
                        "n_rows": row.get("n_rows"),
                    }
        written["file_sha256"] = sha256_file(ladder_csv)

    record = {
        "pid": os.getpid(),
        "xdist_worker": os.environ.get("PYTEST_XDIST_WORKER", "<none>"),
        "engine": args.engine,
        "evidence_root": str(evidence_root.relative_to(ROOT)),
        "chart_output_dir": str(chart_dir),
        "environment": {
            name: os.environ.get(name, "<unset>")
            for name in (
                "DASHBOARD_ENGINE_DEFAULT",
                "DASHBOARD_EVIDENCE_PACK_ROOT",
                "NLTF_CHART_SOURCE_OUTPUT_DIR",
                "NLTF_FORCE_R2_LADDER_DEP_FALLBACK",
            )
        },
        "source_hashes": source_hashes,
        "computed_calibration_r2": computed,
        "reconstruction": reconstruction,
        "diagnostic_override": override,
        "written_csv": written,
        "python": sys.version,
    }
    Path(args.out).write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"engine": args.engine, "computed": computed}, indent=2))


if __name__ == "__main__":
    main()
