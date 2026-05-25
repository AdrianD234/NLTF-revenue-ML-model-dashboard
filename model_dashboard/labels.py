from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(
    r"C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review"
)
DEFAULT_INPUT_PARENT = PROJECT_ROOT / "04 Models" / "Inputs"
DEFAULT_BESPOKE_PARENT = DEFAULT_INPUT_PARENT / "bespoke_solver_stage1_outputs"
IGNORED_RUN_FOLDER_NAMES = {"run_20260519_150434"}

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
    "Schiff benchmark": "The structural econometric specification based on Aaron Schiff's modelling logic.",
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
    return any(token in text for token in ["schiff_ols", "schiff benchmark", "schiff structural benchmark"])


def schiff_class(value: Any, source_family: Any = "", variant: Any = "") -> str:
    text = " ".join("" if part is None else str(part).lower() for part in [value, source_family, variant])
    if "schiff_resid" in text:
        return "Schiff residual challenger"
    if "fixedblend_schiff" in text or "schiff_blend" in text:
        return "Schiff blend challenger"
    if "prequential" in text or "ensemble" in text or "solver_static" in text:
        return "Ensemble challenger"
    if is_schiff_text(value, source_family, variant):
        return "Pure Schiff benchmark"
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
