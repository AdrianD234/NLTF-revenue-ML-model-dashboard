from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .data.config import DEFAULT_BESPOKE_PARENT, DEFAULT_INPUT_PARENT


IGNORED_RUN_FOLDER_NAMES = {"run_20260519_150434"}

SCHIFF_SPEC_BENCHMARK_LABEL = "Schiff specification benchmark"
LEGACY_SCHIFF_STYLE_LABEL = "legacy Schiff-style benchmark"

STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "PED VKT per capita": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "Light RUC volume": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
    "Heavy RUC volume": "Heavy RUC volume",
}

STREAM_KEYS = {
    "PED": "PED",
    "PED VKT per capita": "PED",
    "LIGHT_RUC": "LIGHT_RUC",
    "Light RUC volume": "LIGHT_RUC",
    "HEAVY_RUC": "HEAVY_RUC",
    "Heavy RUC volume": "HEAVY_RUC",
}

STREAM_COLORS = {
    "PED": "#002B5C",
    "PED VKT per capita": "#002B5C",
    "LIGHT_RUC": "#A7C800",
    "Light RUC volume": "#A7C800",
    "HEAVY_RUC": "#008C7E",
    "Heavy RUC volume": "#008C7E",
}

METRIC_COLORS = {
    "Quarterly MAPE": "#002B5C",
    "Annual MAPE": "#A7C800",
}

POWERBI_BLUE = "#002B5C"
POWERBI_GREEN = "#A7C800"
POWERBI_TEXT = "#102A43"

STRESS_BUCKET_ORDER = [
    "1-4 qtrs",
    "5-8 qtrs",
    "9-12 qtrs",
    "2024+",
    "2022-23",
    "Annual",
]

OVERVIEW_STRESS_BUCKET_ORDER = [
    "1-4 qtrs",
    "5-8 qtrs",
    "9-12 qtrs",
    "Annual",
]

STRESS_SLICE_LABELS = {
    "horizon_1_4": "1-4 qtrs",
    "horizon_5_8": "5-8 qtrs",
    "horizon_9_12": "9-12 qtrs",
    "recent_2024_plus": "2024+",
    "ruc_discount_reversal_window_2022_23": "2022-23",
    "annual_full_june_years": "Annual",
    "all_quarters": "All qtrs",
    "covid_target_window_2020_21": "2020-21",
}

TERM_HELP = {
    "Stage 1 actual-driver test": (
        "A model-selection test where realised future explanatory variables are used. "
        "It isolates whether the volume model form is good before adding GDP, fuel price, "
        "and other input-forecast uncertainty."
    ),
    "Rolling-origin forecast": (
        "A backtest where the model is trained only on history up to a chosen quarter, "
        "then forecasts ahead. The origin moves forward and the process repeats."
    ),
    "Held-out forecast": "A future period that was not used to train the model at that origin.",
    "MAPE": "Mean absolute percentage error. Lower is better.",
    "Annual MAPE": "MAPE after quarterly forecasts are aggregated to June-year annual totals or averages.",
    "Bias": "Average signed percentage error. Positive bias means the model tends to over-forecast.",
    "P90 APE": "The 90th percentile absolute percentage error. A tail-risk measure.",
    "Schiff benchmark": "The Schiff specification benchmark scored on the current workbook evidence pack.",
    "GBM": "Gradient boosting model. A tree-based method that builds many small trees sequentially.",
    "Shallow GBM": "A GBM with small tree depth, often depth 1 or 2.",
    "Differenced features": "Inputs such as quarterly or annual changes in prices or GDP rather than only levels.",
    "Target lags": "Past values of the target variable, such as last quarter's VKT or RUC volume.",
    "Sliding window": "A model estimated on only the most recent N quarters.",
    "Expanding window": "A model estimated on all available historical data up to each forecast origin.",
    "Solver ensemble": "A blend of predictions where weights are chosen by an optimisation solver.",
    "Prequential ensemble": "An ensemble whose weights use only earlier forecast origins.",
}


def stream_label(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return STREAM_LABELS.get(text, text or "Unknown")


def stream_key(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return STREAM_KEYS.get(text, text.upper().replace(" ", "_") if text else "UNKNOWN")


def stream_color(value: Any) -> str:
    label = stream_label(value)
    return STREAM_COLORS.get(label, STREAM_COLORS.get(stream_key(value), "#64748B"))


def is_schiff_text(*parts: Any) -> bool:
    model = "" if not parts else str(parts[0]).lower()
    source_family = "" if len(parts) < 2 or parts[1] is None else str(parts[1]).lower()
    text = " ".join("" if part is None else str(part).lower() for part in parts)
    if any(
        token in source_family
        for token in ["bespoke_schiff", "structural_schiff", "schiff_benchmark", "schiff benchmark"]
    ):
        return True
    if any(token in model for token in ["schiff_resid", "fixedblend_schiff", "prequential", "ensemble"]):
        return False
    return any(token in text for token in ["schiff_spec", "schiff_ols", "schiff benchmark", "schiff structural benchmark"])


def is_legacy_schiff_style_text(*parts: Any) -> bool:
    text = " ".join("" if part is None else str(part).lower() for part in parts)
    if "schiff_spec" in text:
        return False
    return any(token in text for token in ["schiff_ols", "fixedblend_schiff1.00", "schiff structural benchmark"])


def schiff_class(value: Any, source_family: Any = "", variant: Any = "") -> str:
    text = " ".join("" if part is None else str(part).lower() for part in [value, source_family, variant])
    if "schiff_resid" in text:
        return "Schiff residual challenger"
    if "fixedblend_schiff" in text or "schiff_blend" in text:
        return "Schiff blend challenger"
    if "prequential" in text or "ensemble" in text or "solver_static" in text:
        return "Ensemble challenger"
    if "schiff_spec" in text:
        return SCHIFF_SPEC_BENCHMARK_LABEL
    if is_schiff_text(value, source_family, variant):
        return LEGACY_SCHIFF_STYLE_LABEL
    return "Non-Schiff challenger"


def shorten_model_name(value: Any, max_length: int = 84) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip("_- ") + "..."


@lru_cache(maxsize=4096)
def _model_alias_text(text: str, max_length: int = 72) -> str:
    lower = text.lower()
    stream_prefixes = {
        "ped__": "PED",
        "light_ruc__": "Light RUC",
        "heavy_ruc__": "Heavy RUC",
    }
    stream = ""
    for prefix, label in stream_prefixes.items():
        if lower.startswith(prefix):
            stream = label
            break

    if "schiff_resid_gbr" in lower:
        family = "Schiff-residual GBM"
    elif "schiff_ols" in lower:
        family = "Schiff OLS"
    elif "solver_static" in lower:
        family = "Static solver"
    elif "prequential" in lower:
        family = "Prequential"
    elif "fixedblend" in lower:
        family = "Fixed blend"
    elif "resid_gbr" in lower or ("gbr" in lower and "resid" in lower):
        family = "Dynamic residual GBM" if "dynamic" in lower else "Residual GBM"
    elif "__ag__naive" in lower or lower.endswith("naive"):
        family = "Naive"
    elif "__ag__theta" in lower or "theta" in lower:
        family = "Theta"
    elif "autogluon" in lower or "__ag__" in lower:
        family = "AutoGluon"
    else:
        return shorten_model_name(text, max_length)

    variant = ""
    if "struct_log_only" in lower:
        variant = "struct log"
    elif "policy_dynamic_rich" in lower:
        variant = "policy rich"
    elif "policy_dynamic_no_leads" in lower:
        variant = "policy no-leads"
    elif "posthoc_ensemble" in lower:
        variant = "post-hoc"
    elif "resid_gbr" in lower or ("gbr" in lower and "resid" in lower):
        parts_for_variant = []
        trees = re.search(r"(?:^|_)n(\d+)(?:_|$)", lower)
        depth = re.search(r"(?:^|_)d(\d+)(?:_|$)", lower)
        window = re.search(r"(?:^|_)w(\d+)(?:_|$)", lower)
        if trees:
            parts_for_variant.append(f"{trees.group(1)} trees")
        if depth:
            parts_for_variant.append(f"depth {depth.group(1)}")
        if window:
            parts_for_variant.append(f"window {window.group(1)}")
        variant = ", ".join(parts_for_variant)

    parts = [part for part in [stream, family, variant] if part]
    return shorten_model_name(" - ".join(parts), max_length)


def model_alias(value: Any, max_length: int = 72) -> str:
    """Create a human-readable label for dense model identifiers."""
    text = "" if value is None else str(value)
    return _model_alias_text(text, max_length)


@lru_cache(maxsize=4096)
def _humanize_text(text: str) -> str:
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "-"
    special = {
        "ped": "PED",
        "ruc": "RUC",
        "mape": "MAPE",
        "p90": "P90",
        "ape": "APE",
        "gbm": "GBM",
        "ols": "OLS",
        "r2": "R2",
    }
    return " ".join(special.get(part.lower(), part.capitalize()) for part in text.split(" "))


def humanize_label(value: Any) -> str:
    text = "" if value is None else str(value)
    return _humanize_text(text)


def display_stream(value: Any) -> str:
    return stream_label(value)


def display_source_family(value: Any) -> str:
    return humanize_label(value)


def display_model_kind(value: Any) -> str:
    return humanize_label(value)


def short_model_label(value: Any) -> str:
    return display_model_label(value, max_length=72)


@lru_cache(maxsize=4096)
def _display_model_label_text(text: str, max_length: int = 84) -> str:
    alias = _model_alias_text(text, max_length=max_length)
    return _humanize_text(alias)


def display_model_label(value: Any, max_length: int = 84) -> str:
    text = "" if value is None else str(value)
    return _display_model_label_text(text, max_length=max_length)


def model_hover_title(value: Any) -> str:
    """Return a management-friendly model family title for chart hovers."""
    text = "" if value is None else str(value).strip()
    if not text:
        return "Model"
    lower = text.lower()
    if "dynamic_no_leads" in lower and "elastic" in lower:
        return "Dynamic ElasticNet model"
    if "resid_gbr" in lower or ("resid" in lower and "gbr" in lower):
        return "Dynamic residual GBM" if "dynamic" in lower else "Residual GBM"
    if "schiff_spec_from_workbook" in lower or "schiff specification" in lower:
        return SCHIFF_SPEC_BENCHMARK_LABEL
    if "schiff" in lower and "gbr" in lower:
        return "Schiff-feature GBM"
    if "gbr" in lower or "gbm" in lower:
        return "Gradient-boosted tree model"
    if "hpo" in lower and "solver" in lower:
        return "Static solver ensemble"
    if "solver_static" in lower or "weighted_top" in lower:
        return "Static weighted ensemble"
    if "recon_static_rebuilt" in lower:
        return "Reconstructed finalist ensemble"
    if "elastic" in lower:
        return "ElasticNet model"
    if "ridge" in lower:
        return "Ridge regression model"
    if "ols" in lower:
        return "OLS regression model"
    return display_model_label(text)


def model_hover_description(value: Any, *, weight: Any = None) -> str:
    """Translate dense model identifiers into concise management hover copy."""
    text = "" if value is None else str(value).strip()
    if not text:
        return "-"
    lower = text.lower()
    parts: list[str] = []

    if "dynamic_no_leads" in lower and "elastic" in lower:
        lag_phrase = "includes target lags" if "ylag" in lower and "noylag" not in lower else "does not include target lags"
        window = _extract_window(lower)
        parts.append(
            "Uses no lead variables, "
            + lag_phrase
            + (f", trained on a {window}-quarter rolling window." if window else ".")
        )
        alpha = _extract_decimal_token(lower, "alpha")
        l1_ratio = _extract_decimal_token(lower, "l1_ratio")
        hp = []
        if alpha is not None:
            hp.append(f"alpha = {_format_param(alpha)}")
        if l1_ratio is not None:
            hp.append(f"L1 ratio = {_format_param(l1_ratio)}")
        if hp:
            parts.append("Hyperparameters: " + ", ".join(hp) + ".")
    elif "resid_gbr" in lower or ("resid" in lower and "gbr" in lower):
        parts.append("A two-stage model: a base economic model plus a shallow gradient-boosted residual correction.")
        hp = _gbm_hyperparameter_sentence(lower)
        if hp:
            parts.append(hp)
    elif "schiff_spec_from_workbook" in lower or "schiff specification" in lower:
        parts.append("Structural benchmark specification sourced from the workbook evidence pack.")
    elif "schiff" in lower and "gbr" in lower:
        parts.append("Gradient-boosted tree model using the Schiff-style feature set.")
        hp = _gbm_hyperparameter_sentence(lower)
        if hp:
            parts.append(hp)
    elif "gbr" in lower or "gbm" in lower:
        parts.append("Gradient-boosted tree model for nonlinear accuracy improvement.")
        hp = _gbm_hyperparameter_sentence(lower)
        if hp:
            parts.append(hp)
    elif "hpo" in lower and "solver" in lower:
        parts.append("Optimisation-selected blend of high-performing candidate forecasts.")
        top_k = re.search(r"top[-_]?(\d+)", lower)
        if top_k:
            parts.append(f"Uses the top {top_k.group(1)} candidate forecasts in the solver pool.")
    elif "solver_static" in lower or "weighted_top" in lower:
        parts.append("Static weighted ensemble selected from the finalist candidate set.")
    elif "recon_static_rebuilt" in lower:
        parts.append("Reconstructed finalist ensemble validated against the evidence-pack final predictions.")
    elif "elastic" in lower:
        parts.append("Regularised linear model balancing ridge and lasso penalties.")
        alpha = _extract_decimal_token(lower, "alpha")
        l1_ratio = _extract_decimal_token(lower, "l1_ratio")
        hp = []
        if alpha is not None:
            hp.append(f"alpha = {_format_param(alpha)}")
        if l1_ratio is not None:
            hp.append(f"L1 ratio = {_format_param(l1_ratio)}")
        if hp:
            parts.append("Hyperparameters: " + ", ".join(hp) + ".")
    else:
        parts.append("Curated finalist or benchmark model from the governed evidence pack.")

    weight_text = _format_hover_weight(weight)
    if weight_text:
        parts.append(f"Ensemble weight: {weight_text}.")

    return " ".join(parts)


def _extract_window(text: str) -> int | None:
    match = re.search(r"(?:^|_)w(\d+)(?:_|$)", text)
    return int(match.group(1)) if match else None


def _extract_decimal_token(text: str, name: str) -> float | None:
    match = re.search(rf"{re.escape(name)}([0-9]+(?:[_.][0-9]+)?)", text)
    if not match:
        return None
    raw = match.group(1).replace("_", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_int_token(text: str, name: str) -> int | None:
    match = re.search(rf"{re.escape(name)}(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _gbm_hyperparameter_sentence(text: str) -> str:
    trees = _extract_int_token(text, "n_estimators")
    if trees is None:
        n_short = re.search(r"(?:^|_)n(\d+)(?:_|$)", text)
        trees = int(n_short.group(1)) if n_short else None
    depth = _extract_int_token(text, "max_depth")
    if depth is None:
        d_short = re.search(r"(?:^|_)d(\d+)(?:_|$)", text)
        depth = int(d_short.group(1)) if d_short else None
    learning_rate = _extract_decimal_token(text, "learning_rate")
    if learning_rate is None:
        lr_short = re.search(r"(?:^|_)lr([0-9]+(?:\.[0-9]+)?)(?:_|$)", text)
        learning_rate = float(lr_short.group(1)) if lr_short else None
    window = _extract_window(text)
    bits = []
    if trees is not None:
        bits.append(f"{trees} trees")
    if depth is not None:
        bits.append(f"depth {depth}")
    if learning_rate is not None:
        bits.append(f"learning rate {_format_param(learning_rate)}")
    if window is not None:
        bits.append(f"{window}-quarter rolling window")
    return ", ".join(bits).capitalize() + "." if bits else ""


def _format_param(value: float) -> str:
    return f"{value:.6g}"


def _format_hover_weight(value: Any) -> str:
    if value is None:
        return ""
    try:
        if _missing(value):
            return ""
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(number) <= 1.5:
        number *= 100.0
    return f"{number:.1f}%"


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def format_percent(value: Any, digits: int = 2) -> str:
    try:
        if _missing(value):
            return "-"
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.{digits}f}%"


def fmt_pct(value: Any, decimals: int = 2) -> str:
    return format_percent(value, digits=decimals)


def format_pp(value: Any, digits: int = 2) -> str:
    try:
        if _missing(value):
            return "-"
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "+" if number >= 0 else ""
    return f"{sign}{number:.{digits}f} pp"


def fmt_pp(value: Any, decimals: int = 2) -> str:
    return format_pp(value, digits=decimals)


def format_weight(value: Any) -> str:
    return format_percent(value, digits=1)


def fmt_weight(value: Any, decimals: int = 1) -> str:
    try:
        if _missing(value):
            return "-"
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) <= 1.5:
        number *= 100.0
    return f"{number:.{decimals}f}%"


def format_count(value: Any) -> str:
    try:
        if _missing(value):
            return "-"
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return "-"
    return f"{number:,}"


def fmt_count(value: Any) -> str:
    return format_count(value)


def clean_hover_text(value: Any) -> str:
    return humanize_label(shorten_model_name(value, 110))


def horizon_label(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("1-4 qtrs", "1–4 quarters")
        .replace("5-8 qtrs", "5–8 quarters")
        .replace("9-12 qtrs", "9–12 quarters")
        .replace("qtrs", "quarters")
    )
