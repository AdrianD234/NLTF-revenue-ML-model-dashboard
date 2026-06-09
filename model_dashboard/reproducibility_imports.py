from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go


R2_GOVERNANCE_INFO_TEXT = (
    "Forecast R2 is calculated from final delivered predictions after residual correction or ensemble weighting. "
    "Calibration R2 is actual-on-forecast validation R2. Neither is in-sample OLS R2."
)
OPTIONAL_IMPORT_FORCE_ENV = "NLTF_FORCE_REPRODUCIBILITY_IMPORT_FALLBACK"

_STREAM_LABELS = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
_STREAM_KEYS = {
    "PED VKT per capita": "ped",
    "Light RUC volume": "light_ruc",
    "Heavy RUC volume": "heavy_ruc",
}
_REPRO_BASE_ROOT = Path(__file__).resolve().parents[1] / "data" / "dashboard_evidence_pack_reproducibility"
_FALLBACK_MISSING = ("optional governance/reproducibility import unavailable",)


@dataclass(frozen=True)
class FallbackReproducibilityConfig:
    stream_label: str
    stream_key: str
    root: Path
    model: str = "unavailable"
    description: str = "Auxiliary reproducibility functions are unavailable in this runtime."
    report_file: str = "reproducibility_report.md"

    @property
    def required_files(self) -> tuple[str, ...]:
        return _FALLBACK_MISSING


@dataclass(frozen=True)
class FallbackReproducibilityPack:
    stream_label: str
    config: FallbackReproducibilityConfig
    root: Path
    manifest: dict[str, Any]
    tables: dict[str, pd.DataFrame]
    missing_files: tuple[str, ...]

    @property
    def available(self) -> bool:
        return False

    def table(self, name: str) -> pd.DataFrame:
        del name
        return pd.DataFrame()


@dataclass(frozen=True)
class FallbackPedInnerHpoAuditPack:
    root: Path
    manifest: dict[str, Any]
    tables: dict[str, pd.DataFrame]
    missing_files: tuple[str, ...]

    @property
    def available(self) -> bool:
        return False

    def table(self, name: str) -> pd.DataFrame:
        del name
        return pd.DataFrame()


_REPRO_SYMBOLS = {
    "PED_INNER_HPO_AUDIT_STATUS",
    "load_ped_inner_hpo_audit_pack",
    "ped_inner_hpo_audit_signature",
    "ped_inner_hpo_audit_summary",
    "ped_inner_hpo_gap_register_view",
    "ped_inner_hpo_nested_trace_view",
    "ped_inner_hpo_public_source_reference",
    "ped_inner_hpo_source_artifacts_view",
    "ped_inner_hpo_weight_detail_view",
    "ped_inner_hpo_weight_source_view",
    "reproducibility_coefficients_view",
    "reproducibility_component_trace_view",
    "reproducibility_feature_importance_view",
    "reproducibility_ensemble_equation",
    "reproducibility_ensemble_weight_view",
    "reproducibility_annual_view",
    "reproducibility_horizon_view",
    "reproducibility_pack_signature",
    "reproducibility_registry_view",
    "reproducibility_replay_summary",
    "reproducibility_sensitivity_view",
    "reproducibility_scorecard_view",
    "reproducibility_stress_view",
    "reproducibility_stream_labels",
    "reproducibility_training_window_view",
    "load_reproducibility_pack",
    "plot_reproducibility_feature_importance",
    "plot_reproducibility_sensitivities",
}
_R2_SYMBOLS = {"diagnostics_r2_summary_frame", "reproducibility_component_r2_frame", "format_r2"}
_R2_LADDER_SYMBOLS = {
    "R2_LADDER_NOTE",
    "R2_LADDER_TITLE",
    "R2_TRAINING_FIT_NOTE",
    "r2_ladder_frames",
    "r2_ladder_summary_frame",
}


def _forced_fallback() -> bool:
    return os.environ.get(OPTIONAL_IMPORT_FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _load_symbols(module_name: str, names: set[str]) -> tuple[dict[str, Any], str | None]:
    if _forced_fallback():
        return {}, f"forced fallback via {OPTIONAL_IMPORT_FORCE_ENV}"
    try:
        module = importlib.import_module(module_name, package=__package__)
    except Exception as exc:
        return {}, f"{module_name}: {type(exc).__name__}: {exc}"
    missing = sorted(name for name in names if not hasattr(module, name))
    if missing:
        return {}, f"{module_name}: missing optional symbols: {', '.join(missing)}"
    return {name: getattr(module, name) for name in names}, None


def _fallback_config(stream_label: str) -> FallbackReproducibilityConfig:
    stream_key = _STREAM_KEYS.get(stream_label, "light_ruc")
    return FallbackReproducibilityConfig(
        stream_label=stream_label,
        stream_key=stream_key,
        root=_REPRO_BASE_ROOT / stream_key,
    )


def _fallback_pack(stream_label: str, root: str | Path | None = None) -> FallbackReproducibilityPack:
    config = _fallback_config(stream_label)
    pack_root = Path(root).expanduser() if root else config.root
    return FallbackReproducibilityPack(
        stream_label=config.stream_label,
        config=config,
        root=pack_root,
        manifest={"status": "optional_import_unavailable", "reason": REPRODUCIBILITY_IMPORT_ERROR or ""},
        tables={},
        missing_files=_FALLBACK_MISSING,
    )


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        showarrow=False,
        xref="paper",
        yref="paper",
        font=dict(color="#64748B"),
    )
    fig.update_layout(
        height=320,
        margin=dict(l=8, r=8, t=10, b=28),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


_repro, REPRODUCIBILITY_IMPORT_ERROR = _load_symbols(".light_ruc_reproducibility", _REPRO_SYMBOLS)
if REPRODUCIBILITY_IMPORT_ERROR is None:
    globals().update(_repro)
else:
    PED_INNER_HPO_AUDIT_STATUS = "Inner HPO/static-solver audit unavailable"

    def reproducibility_stream_labels() -> list[str]:
        return list(_STREAM_LABELS)

    def reproducibility_pack_signature(
        stream_label: str = "Light RUC volume",
        root: str | Path | None = None,
    ) -> tuple[tuple[str, int, int], ...]:
        del stream_label, root
        return ()

    def load_reproducibility_pack(
        stream_label: str = "Light RUC volume",
        root: str | Path | None = None,
    ) -> FallbackReproducibilityPack:
        return _fallback_pack(stream_label, root)

    def ped_inner_hpo_audit_signature(root: str | Path | None = None) -> tuple[tuple[str, int, int], ...]:
        del root
        return ()

    def load_ped_inner_hpo_audit_pack(root: str | Path | None = None) -> FallbackPedInnerHpoAuditPack:
        pack_root = Path(root).expanduser() if root else _REPRO_BASE_ROOT / "ped_inner_hpo"
        return FallbackPedInnerHpoAuditPack(
            root=pack_root,
            manifest={"status": "optional_import_unavailable", "reason": REPRODUCIBILITY_IMPORT_ERROR or ""},
            tables={},
            missing_files=_FALLBACK_MISSING,
        )

    def ped_inner_hpo_audit_summary(pack: Any) -> dict[str, Any]:
        del pack
        return {
            "outer_status": "Unavailable",
            "outer_max_abs_delta": pd.NA,
            "inner_status": PED_INNER_HPO_AUDIT_STATUS,
            "inner_max_abs_delta": pd.NA,
            "description": "PED inner HPO/static-solver audit functions are unavailable in this runtime.",
            "weight_source_count": 0,
        }

    def reproducibility_replay_summary(pack: Any) -> dict[str, Any]:
        stream_label = getattr(pack, "stream_label", "Reproducibility pack")
        config = getattr(pack, "config", _fallback_config(str(stream_label)))
        return {
            "status": "Unavailable",
            "model": getattr(config, "model", "unavailable"),
            "max_abs_pred_delta": pd.NA,
            "workbook": "unavailable",
            "source_sheet": "unavailable",
            "description": "Auxiliary reproducibility functions are unavailable in this runtime.",
        }

    def reproducibility_ensemble_equation(pack: Any) -> str:
        del pack
        return "Reproducibility pack unavailable."

    def plot_reproducibility_feature_importance(data: pd.DataFrame, stream_label: str) -> go.Figure:
        del data
        return _empty_figure(f"{stream_label} feature-importance rows are unavailable.")

    def plot_reproducibility_sensitivities(data: pd.DataFrame, stream_label: str) -> go.Figure:
        del data
        return _empty_figure(f"{stream_label} scenario-sensitivity rows are unavailable.")

    def _empty_frame(*args: Any, **kwargs: Any) -> pd.DataFrame:
        del args, kwargs
        return pd.DataFrame()

    ped_inner_hpo_gap_register_view = _empty_frame
    ped_inner_hpo_nested_trace_view = _empty_frame
    ped_inner_hpo_source_artifacts_view = _empty_frame
    ped_inner_hpo_weight_detail_view = _empty_frame
    ped_inner_hpo_weight_source_view = _empty_frame

    def ped_inner_hpo_public_source_reference(pack: Any, source_file: Any) -> str:
        del pack
        text = str(source_file)
        normalised = text.replace("\\", "/")
        if any(token in normalised.lower() for token in ["c:/users", "downloads", "onedrive", "appdata"]):
            return Path(normalised).name or "local source path hidden"
        return text
    reproducibility_coefficients_view = _empty_frame
    reproducibility_component_trace_view = _empty_frame
    reproducibility_feature_importance_view = _empty_frame
    reproducibility_ensemble_weight_view = _empty_frame
    reproducibility_annual_view = _empty_frame
    reproducibility_horizon_view = _empty_frame
    reproducibility_registry_view = _empty_frame
    reproducibility_sensitivity_view = _empty_frame
    reproducibility_scorecard_view = _empty_frame
    reproducibility_stress_view = _empty_frame
    reproducibility_training_window_view = _empty_frame


_r2, R2_IMPORT_ERROR = _load_symbols(".r2_metrics", _R2_SYMBOLS)
if R2_IMPORT_ERROR is None:
    globals().update(_r2)
else:

    def diagnostics_r2_summary_frame(
        scorecard_predictions: pd.DataFrame,
        diagnostic_tests: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        del scorecard_predictions, diagnostic_tests
        return pd.DataFrame()

    def reproducibility_component_r2_frame(repo_root: Path | str | None = None) -> pd.DataFrame:
        del repo_root
        return pd.DataFrame()

    def format_r2(value: Any) -> str:
        number = pd.to_numeric(value, errors="coerce")
        return "-" if pd.isna(number) else f"{float(number):.3f}"


_r2_ladder, R2_LADDER_IMPORT_ERROR = _load_symbols(".r2_ladder", _R2_LADDER_SYMBOLS)
if R2_LADDER_IMPORT_ERROR is None:
    globals().update(_r2_ladder)
else:
    R2_LADDER_TITLE = "R2 ladder: training fit vs calibration vs forecast R2"
    R2_LADDER_NOTE = (
        "Training-fit R2 is not comparable to forecast R2. High paper-style R2 usually measures in-sample fit, "
        "while forecast R2 measures out-of-sample explanatory power after final model composition."
    )
    R2_TRAINING_FIT_NOTE = (
        "Training-fit R2 is computed from fitted rows inside the rolling training windows. "
        "It is not an out-of-sample forecast metric."
    )

    def r2_ladder_frames(data: dict[str, pd.DataFrame], repo_root: Path | str | None = None) -> dict[str, pd.DataFrame]:
        del data, repo_root
        empty = pd.DataFrame()
        return {
            "summary": empty,
            "training_fit_detail": empty,
            "gap_register": empty,
        }

    def r2_ladder_summary_frame(data: dict[str, pd.DataFrame], repo_root: Path | str | None = None) -> pd.DataFrame:
        return r2_ladder_frames(data, repo_root=repo_root)["summary"]


__all__ = sorted(
    {
        "R2_GOVERNANCE_INFO_TEXT",
        "REPRODUCIBILITY_IMPORT_ERROR",
        "R2_IMPORT_ERROR",
        "R2_LADDER_IMPORT_ERROR",
        "OPTIONAL_IMPORT_FORCE_ENV",
        *_REPRO_SYMBOLS,
        *_R2_SYMBOLS,
        *_R2_LADDER_SYMBOLS,
    }
)
