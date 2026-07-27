"""Fingerprint the governed fixed-finalist replay for cross-platform comparison.

Clean-environment CI found the governed replay producing values up to ~0.42%
apart between Windows and Linux. For a fixed-finalist replay that is far too
large to wave through as floating-point noise, and the cause has to be located
before any tolerance is touched.

This script emits everything needed to localise it: the resolved runtime
versions and BLAS backend, the hashes of every committed input and fitted
state, and per-stream/per-quarter forecast values from the *stages* of the
pipeline, so the first stage that diverges identifies the culprit:

* ``raw_bridge``    - inputs straight off the committed pack, no model call.
* ``fitted_state``  - the serialized fitted states as loaded, hashed.
* ``replay``        - the fixed-finalist forecast per stream and quarter.

Run it on two platforms and diff the CSVs. The first stage that differs tells
you whether the divergence comes from deserialization, from a runtime refit, or
from linear algebra.

Usage::

    python scripts/replay_parity_fingerprint.py --output artifacts/replay_parity
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FINGERPRINT_VERSION = "replay-parity-fingerprint-v1"
SCENARIO_INPUTS = (
    REPO_ROOT
    / "data"
    / "current_revenue_outlook"
    / "scenario_inputs"
    / "scenario_input_wide.parquet"
)
STATE_DIRS = {
    "PED": "ped_vnext",
    "LIGHT_RUC": "light_ruc_vnext",
    "HEAVY_RUC": "heavy_ruc_vnext",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_environment() -> dict[str, Any]:
    record: dict[str, Any] = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.replace("\n", " "),
    }
    for module in (
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "joblib",
        "pyarrow",
        "statsmodels",
    ):
        try:
            record[module] = __import__(module).__version__
        except Exception as exc:  # noqa: BLE001 - report, do not fail the probe
            record[module] = f"unavailable: {exc}"
    try:
        import threadpoolctl

        record["threadpool_info"] = threadpoolctl.threadpool_info()
    except Exception as exc:  # noqa: BLE001
        record["threadpool_info"] = f"unavailable: {exc}"
    try:
        record["numpy_blas"] = np.__config__.show(mode="dicts")
    except Exception as exc:  # noqa: BLE001
        record["numpy_blas"] = f"unavailable: {exc}"
    return record


def input_hashes() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    targets: list[Path] = [SCENARIO_INPUTS]
    for stream, directory in STATE_DIRS.items():
        base = REPO_ROOT / "data" / "dashboard_evidence_pack_reproducibility" / directory
        if not base.exists():
            continue
        manifest = base / "fitted_model_manifest.json"
        if manifest.exists():
            targets.append(manifest)
        state_dir = base / "fitted_state"
        if state_dir.exists():
            targets.extend(sorted(state_dir.rglob("*")))
    for path in targets:
        if not path.is_file():
            continue
        rows.append(
            {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return pd.DataFrame(rows).sort_values("path").reset_index(drop=True)


def replay_fingerprint() -> pd.DataFrame:
    """Per stream/quarter forecast values from the governed replay."""

    from model_dashboard.fuel_price_scenario import run_fuel_price_scenario_replay

    replay = run_fuel_price_scenario_replay(
        pd.read_parquet(SCENARIO_INPUTS), repo_root=REPO_ROOT, engine="ensemble"
    )
    forecasts = replay.future_forecasts
    columns = [
        column
        for column in (
            "scenario_name",
            "stream",
            "target_period",
            "forecast",
            "demand_raw_forecast",
            "demand_reference_forecast",
            "demand_price_ratio",
            "demand_gdp_model_factor_raw",
            "demand_gdp_model_factor",
        )
        if column in forecasts.columns
    ]
    out = forecasts[columns].copy()
    for column in out.columns:
        if column in {"scenario_name", "stream", "target_period"}:
            out[column] = out[column].astype(str)
        else:
            # Full precision: a 1e-16 difference must survive the round trip so
            # the diff shows where divergence starts, not where it grew visible.
            out[column] = pd.to_numeric(out[column], errors="coerce").map(
                lambda value: format(float(value), ".17g") if pd.notna(value) else ""
            )
    return out.sort_values(["scenario_name", "stream", "target_period"]).reset_index(
        drop=True
    )


def raw_bridge_fingerprint() -> pd.DataFrame:
    """Committed inputs with no model call, to isolate data-vs-model divergence."""

    frame = pd.read_parquet(SCENARIO_INPUTS)
    rows: list[dict[str, Any]] = []
    # Scenario inputs store numbers as strings to preserve exact round-tripping,
    # so coerce every column rather than filtering on dtype.
    for column in sorted(frame.columns):
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            continue
        rows.append(
            {
                "column": column,
                "count": int(series.size),
                "sum": format(float(series.sum()), ".17g"),
                "min": format(float(series.min()), ".17g"),
                "max": format(float(series.max()), ".17g"),
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "artifacts" / "replay_parity"
    )
    args = parser.parse_args(argv)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    environment = runtime_environment()
    (output / "runtime_environment.json").write_text(
        json.dumps(environment, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({k: environment[k] for k in list(environment)[:10]}, indent=2, default=str))

    hashes = input_hashes()
    hashes.to_csv(output / "input_hashes.csv", index=False)
    print(f"\n{len(hashes)} committed inputs hashed")

    raw = raw_bridge_fingerprint()
    raw.to_csv(output / "raw_bridge_fingerprint.csv", index=False)
    print(f"{len(raw)} raw input columns fingerprinted")

    replay = replay_fingerprint()
    replay.to_csv(output / "replay_fingerprint.csv", index=False)
    print(f"{len(replay)} replay rows fingerprinted")

    digest = hashlib.sha256(
        (output / "replay_fingerprint.csv").read_bytes()
    ).hexdigest()
    (output / "replay_fingerprint_sha256.txt").write_text(digest + "\n", encoding="utf-8")
    print(f"\nreplay_fingerprint.csv sha256 = {digest}")
    print(f"Written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
