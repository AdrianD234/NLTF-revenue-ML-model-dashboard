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


def current_repro_pack_dirs(engine: str | None = None) -> dict[str, str]:
    """Engine-aware reproducibility-pack map (PED -> ped_ar1 under 'ar1')."""
    from model_dashboard.engine import engine_repro_pack_dirs

    return engine_repro_pack_dirs(engine)


def evidence_pack_data(engine: str | None = None) -> Path:
    from model_dashboard.engine import engine_evidence_data

    return engine_evidence_data(engine)


def current_repro_pack_root(stream: str, engine: str | None = None) -> Path:
    return REPRODUCIBILITY_BASE / current_repro_pack_dirs(engine)[stream]


def current_finalist(stream: str, engine: str | None = None) -> str:
    """Resolve the current finalist model name for the active (or given) engine.

    Order of truth: the stream's current reproducibility-pack manifest, then
    the governed evidence pack, then the archived fallback.
    """
    from model_dashboard.engine import active_engine

    return _current_finalist_cached(str(stream), engine or active_engine())


@lru_cache(maxsize=None)
def _current_finalist_cached(stream: str, engine: str) -> str:
    manifest_path = current_repro_pack_root(stream, engine) / "fitted_model_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            model = str(manifest.get("finalist_model", "")).strip()
            if model:
                return model
        except Exception:
            pass
    finalists_path = evidence_pack_data(engine) / "finalists.parquet"
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


def current_finalists(engine: str | None = None) -> dict[str, str]:
    return {stream: current_finalist(stream, engine) for stream in STREAMS}


def current_composite_model_id(engine: str | None = None) -> str:
    """Joined finalist ids for rollup rows that combine all three streams."""
    return "; ".join(current_finalist(stream, engine) for stream in STREAMS)
