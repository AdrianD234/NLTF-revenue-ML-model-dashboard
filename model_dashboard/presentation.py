"""Presentation profile: executive vs analyst rendering of the same governed data.

Same governed data, same calculations, different presentation layer. This
module owns:

- the dashboard mode (``executive`` default everywhere, ``analyst`` via the
  in-app toggle or the ``NLTF_DASHBOARD_MODE`` environment variable);
- executive page titles for the existing page skeleton;
- curated plain-English display labels for model identifiers, score bases
  and forward-capability statuses (raw identifiers stay available in
  technical traces and analyst mode - nothing is removed, just not led with).

No metric, status or evidence value is computed here.
"""

from __future__ import annotations

import os
from typing import Any

EXECUTIVE = "executive"
ANALYST = "analyst"
MODE_ENV_VAR = "NLTF_DASHBOARD_MODE"
MODE_TOGGLE_KEY = "dashboard_analyst_toggle"

EXECUTIVE_PAGE_TITLES = {
    "Overview": "Executive Summary",
    "Diagnostics": "Model Confidence",
    "Scenario Comparison": "Scenario Forecasts",
    "Schiff Benchmark": "Benchmark Comparison",
    "Revenue Outlook": "Revenue Outlook",
    "Governance & Reproducibility": "Governance & Reproducibility",
}

EXECUTIVE_SUBTITLE = ("Transport revenue forecasting | Recommended models, benchmark gains "
                      "and forecast readiness at a glance.")
ANALYST_SUBTITLE = ("Transport Revenue Model Testbench | Refined finalist models | "
                    "actual-driver Stage 1 evidence.")

# --- curated model labels ---------------------------------------------------
# Every identifier that can surface in charts, hovers, tables or modals.
# Coverage is enforced by tests/test_executive_mode.py against the packs.
MODEL_DISPLAY = {
    "PED__VNEXT_SOLVED_CONVEX_TOP2": "PED weighted ensemble (vNext)",
    "HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4": "Heavy RUC weighted ensemble (vNext)",
    "dynamic_RESID_GBR_n150_d1_lr0.05_w36": "Light RUC residual-correction model",
    "PED__SCHIFF_SPEC_FROM_WORKBOOK": "Schiff specification benchmark (PED)",
    "LIGHT_RUC__SCHIFF_SPEC_FROM_WORKBOOK": "Schiff specification benchmark (Light RUC)",
    "HEAVY_RUC__SCHIFF_SPEC_FROM_WORKBOOK": "Schiff specification benchmark (Heavy RUC)",
    "LIGHT_RUC__SCHIFF_SPEC_FINAL_OLS_EXPANDING": "Schiff specification benchmark (archived parent run)",
    "PED__SCHIFF_SPEC_FINAL_OLS_EXPANDING": "Schiff specification benchmark (archived parent run, PED)",
    "HEAVY_RUC__SCHIFF_SPEC_FINAL_AR1_EXPANDING": "Schiff specification benchmark (archived parent run, Heavy RUC)",
    # vNext ensemble components
    "PED__VNEXT__dynamic_no_leads__resid_gbr_learning_rate0p05_max_depth1_n_estimators150__noylag__wexp":
        "PED component: dynamic residual-boosted model (expanding window)",
    "PED__VNEXT__diff__gbr_learning_rate0p05_max_depth1_n_estimators400__ylag__w56":
        "PED component: differenced gradient-boosted model (56q window)",
    "HEAVY_RUC__VNEXT__dynamic_no_leads__ridge_alpha10p0__ylag__w64":
        "Heavy RUC component: ridge regression (64q window)",
    "HEAVY_RUC__VNEXT__schiff__gbr_learning_rate0p08_max_depth1_n_estimators150__noylag__w52":
        "Heavy RUC component: Schiff-feature boosted model (52q window)",
    "HEAVY_RUC__VNEXT__dynamic_no_leads__gbr_learning_rate0p05_max_depth1_n_estimators650__ylag__w52":
        "Heavy RUC component: dynamic gradient-boosted model (52q window)",
    # archived legacy finalists (superseded; survive on governance surfaces)
    "HEAVY_RUC__RECON_STATIC_REBUILT": "Heavy RUC archived legacy finalist (superseded by vNext)",
    "PED__RESCUE_static_annual_weighted_top12_capnone": "PED archived legacy finalist (superseded by vNext)",
    "weighted_ensemble_final": "Weighted ensemble (final)",
}

SCORE_BASIS_DISPLAY = {
    "schiff_paper_horizon_mean": "Paper-style horizon scorecard",
    "current_grid_operational_pooled": "Operational backtest scorecard",
}

CAPABILITY_DISPLAY = {
    "numeric_forecast_available": "Forecast-ready: numeric forecasts available for new assumptions.",
    "parity_failed": "Forward scorer not verified: replay parity gate failed, so no numeric forecast is produced.",
    "governed_gap": "Forecast not yet approved for this stream: the governed output is an explicit gap, never a fabricated number.",
    "forward_scorer_missing": "Not forward-scoreable: the original model run did not retain the fitted state needed to score new assumptions.",
    "historical_replay_only": "Historically reproducible, but not yet forward-scoreable.",
}

BADGE_COLORS = {"Promote": "#15803d", "Watch": "#b45309", "Monitor": "#b91c1c"}


def default_mode() -> str:
    raw = os.environ.get(MODE_ENV_VAR, "").strip().lower()
    return ANALYST if raw == ANALYST else EXECUTIVE


def resolve_mode() -> str:
    """Session toggle wins; environment default otherwise."""
    try:
        import streamlit as st

        if MODE_TOGGLE_KEY in st.session_state:
            return ANALYST if st.session_state[MODE_TOGGLE_KEY] else EXECUTIVE
    except Exception:
        pass
    return default_mode()


def is_executive() -> bool:
    return resolve_mode() == EXECUTIVE


def render_mode_toggle() -> None:
    """Discreet analyst-mode switch; default mirrors the environment."""
    import streamlit as st

    st.toggle(
        "Analyst mode",
        key=MODE_TOGGLE_KEY,
        value=default_mode() == ANALYST,
        help=("Analyst mode shows full technical traceability: raw model identifiers, "
              "source tables and audit detail. Executive mode shows the same governed "
              "numbers with plain-English labels."),
    )


CLOUD_PREVIEW_KEY = "cloud_runtime_preview_toggle"


def cloud_preview_enabled() -> bool:
    """Session flag that makes a local run behave like Streamlit Cloud
    (same page set and runtime gating), so deploy behaviour can be tested
    before pushing. Code version is unaffected - use
    scripts/run_deployed_preview.ps1 to run the actually-deployed commit."""
    try:
        import streamlit as st

        return bool(st.session_state.get(CLOUD_PREVIEW_KEY, False))
    except Exception:
        return False


def render_cloud_preview_toggle() -> None:
    import streamlit as st

    st.toggle(
        "Cloud runtime preview",
        key=CLOUD_PREVIEW_KEY,
        help=("Render this local session with Streamlit Cloud runtime rules "
              "(e.g. the Governance & Reproducibility page is hidden, exactly as "
              "on the deployed app). This previews runtime behaviour only - the "
              "deployed code version may still differ until you push; use "
              "scripts/run_deployed_preview.ps1 to run the deployed commit side by side."),
    )


def page_display_title(page: str) -> str:
    if is_executive():
        return EXECUTIVE_PAGE_TITLES.get(page, page)
    return page


def header_subtitle() -> str:
    return EXECUTIVE_SUBTITLE if is_executive() else ANALYST_SUBTITLE


def display_model(model_id: Any) -> str:
    """Curated label first; family-based fallback so nothing raw ever leaks."""
    text = "" if model_id is None else str(model_id).strip()
    if not text:
        return "Model"
    if text in MODEL_DISPLAY:
        return MODEL_DISPLAY[text]
    from .labels import model_hover_title

    return model_hover_title(text)


def display_score_basis(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return SCORE_BASIS_DISPLAY.get(text, text.replace("_", " ").strip().capitalize() or "-")


def display_capability(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text in CAPABILITY_DISPLAY:
        return CAPABILITY_DISPLAY[text]
    for code, label in CAPABILITY_DISPLAY.items():
        if code in text:
            return label
    return text.replace("_", " ").strip().capitalize() or "-"


def missing_model_labels(model_ids) -> list[str]:
    """Identifiers without a curated label (fallback would still apply)."""
    return sorted({str(m) for m in model_ids if str(m).strip() and str(m) not in MODEL_DISPLAY})
