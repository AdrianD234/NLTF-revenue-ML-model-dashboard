"""Single source of truth for stream, finalist and reproducibility-pack naming.

Every surface that needs to know "which model is the current finalist" or
"which reproducibility pack is current" must read it from here (or from the
governed packs via the resolvers below) so that a future finalist promotion
feeds through the whole dashboard by changing exactly one place:
``CURRENT_REPRO_PACK_DIRS`` (plus running the promotion script).

Lifecycle vocabulary used across the repo:
- "current"  -> drives dashboards, forecasts and governance views.
- "archived" -> retained as immutable lineage (legacy packs, v6 backup);
                never feeds current charts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPRODUCIBILITY_BASE = REPO_ROOT / "data" / "dashboard_evidence_pack_reproducibility"
EVIDENCE_PACK_DATA = REPO_ROOT / "data" / "dashboard_evidence_pack" / "data"

PARITY_TOLERANCE = 1e-6

STREAMS = ("PED", "LIGHT_RUC", "HEAVY_RUC")

STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
}
STREAM_BY_LABEL = {label: stream for stream, label in STREAM_LABELS.items()}

# Reproducibility packs that describe the CURRENT finalists. A finalist
# promotion updates this map (and only this map) on the code side.
CURRENT_REPRO_PACK_DIRS = {
    "PED": "ped_vnext",
    "LIGHT_RUC": "light_ruc",
    "HEAVY_RUC": "heavy_ruc_vnext",
}

# Immutable lineage; never feeds current charts.
ARCHIVED_REPRO_PACK_DIRS = ("ped", "heavy_ruc", "ped_inner_hpo", "light_ruc_vnext")

# Archived (pre-vNext) finalists; used only for lineage displays and for the
# governed-gap fallback when a current pack is absent.
ARCHIVED_FINALISTS = {
    "PED": "PED__RESCUE_static_annual_weighted_top12_capnone",
    "LIGHT_RUC": "dynamic_RESID_GBR_n150_d1_lr0.05_w36",
    "HEAVY_RUC": "HEAVY_RUC__RECON_STATIC_REBUILT",
}


def current_repro_pack_root(stream: str) -> Path:
    return REPRODUCIBILITY_BASE / CURRENT_REPRO_PACK_DIRS[stream]


@lru_cache(maxsize=None)
def current_finalist(stream: str) -> str:
    """Resolve the current finalist model name.

    Order of truth: the stream's current reproducibility-pack manifest, then
    the governed evidence pack, then the archived fallback. Cached per process.
    """
    manifest_path = current_repro_pack_root(stream) / "fitted_model_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            model = str(manifest.get("finalist_model", "")).strip()
            if model:
                return model
        except Exception:
            pass
    finalists_path = EVIDENCE_PACK_DATA / "finalists.parquet"
    if finalists_path.exists():
        try:
            import pandas as pd

            finalists = pd.read_parquet(finalists_path)
            rows = finalists[finalists["stream"].astype(str).eq(stream)]
            if not rows.empty:
                return str(rows["model"].iloc[0])
        except Exception:
            pass
    return ARCHIVED_FINALISTS[stream]


def current_finalists() -> dict[str, str]:
    return {stream: current_finalist(stream) for stream in STREAMS}
