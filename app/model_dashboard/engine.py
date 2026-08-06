"""Engine selection: which governed pack family drives the whole dashboard.

Two engines exist; the choice is a per-session setting (default AR(1),
env-overridable) and maps ONLY to pack locations - no chart special-cases:

- ``ar1``      "AR(1) model"  - PED finalist is the GLSAR AR(1) regression
               (all six core diagnostics pass); packs under ``data/engine_ar1/``.
- ``ensemble`` "ML ensemble"  - the incumbent vNext finalists; packs under
               ``data/dashboard_evidence_pack`` / ``data/current_revenue_outlook``.

Light RUC and Heavy RUC finalists are identical under both engines.
"""
from __future__ import annotations

import os
from pathlib import Path

ENGINE_KEY = "dashboard_engine"
ENGINE_DEFAULT_ENV = "DASHBOARD_ENGINE_DEFAULT"
ENGINE_AR1 = "ar1"
ENGINE_ENSEMBLE = "ensemble"
ENGINE_LABELS = {
    ENGINE_AR1: "AR(1) model",
    ENGINE_ENSEMBLE: "ML ensemble",
}
ENGINE_ORDER = (ENGINE_AR1, ENGINE_ENSEMBLE)
ENGINE_HELP = (
    "AR(1) model: PED is forecast by an AR(1)-error regression that passes every core "
    "residual diagnostic (Durbin-Watson, White, heteroskedasticity and stationarity tests) at "
    "near-identical accuracy. ML ensemble: the incumbent gradient-boosted ensemble finalist, "
    "slightly more accurate on backtest MAPE but with Durbin-Watson and White failures. "
    "Light and Heavy RUC models are the same under both engines."
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def engine_default() -> str:
    value = str(os.environ.get(ENGINE_DEFAULT_ENV, "")).strip().lower()
    return value if value in ENGINE_LABELS else ENGINE_AR1


def active_engine() -> str:
    try:
        import streamlit as st

        value = str(st.session_state.get(ENGINE_KEY, engine_default())).strip().lower()
    except Exception:
        value = engine_default()
    return value if value in ENGINE_LABELS else engine_default()


def engine_label(engine: str | None = None) -> str:
    return ENGINE_LABELS.get(engine or active_engine(), ENGINE_LABELS[ENGINE_AR1])


def engine_evidence_root(engine: str | None = None) -> Path:
    engine = engine or active_engine()
    if engine == ENGINE_AR1:
        return _REPO_ROOT / "data" / "engine_ar1" / "dashboard_evidence_pack"
    return _REPO_ROOT / "data" / "dashboard_evidence_pack"


def engine_evidence_data(engine: str | None = None) -> Path:
    return engine_evidence_root(engine) / "data"


def engine_revenue_outlook_dir(engine: str | None = None) -> Path:
    """Repo-relative Revenue Outlook runtime pack directory for the engine."""
    engine = engine or active_engine()
    if engine == ENGINE_AR1:
        return Path("data") / "engine_ar1" / "current_revenue_outlook"
    return Path("data") / "current_revenue_outlook"


def engine_repro_pack_dirs(engine: str | None = None) -> dict[str, str]:
    engine = engine or active_engine()
    dirs = {"PED": "ped_vnext", "LIGHT_RUC": "light_ruc", "HEAVY_RUC": "heavy_ruc_vnext"}
    if engine == ENGINE_AR1:
        dirs["PED"] = "ped_ar1"
    return dirs


def render_engine_selector(*, widget_prefix: str = "") -> None:
    """Engine radio following the cloud-preview session-state pattern."""
    import streamlit as st

    st.session_state.setdefault(ENGINE_KEY, engine_default())
    st.radio(
        "Model engine",
        list(ENGINE_ORDER),
        format_func=lambda value: ENGINE_LABELS.get(value, value),
        key=ENGINE_KEY,
        help=ENGINE_HELP,
    )
