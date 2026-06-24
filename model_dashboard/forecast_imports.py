from __future__ import annotations

import importlib
import os
from pathlib import Path
import re
from typing import Any


OPTIONAL_IMPORT_FORCE_ENV = "NLTF_FORCE_FORECAST_RUNNER_IMPORT_FALLBACK"
FORECAST_BUILDER_TITLE = "Forecast Builder"
FORECAST_BUILDER_NOTE = (
    "This workflow creates forward forecasts or governed missing-capability gaps from a user-supplied "
    "variable-horizon assumption workbook. It writes separate forecast-run artifacts and does not alter governance "
    "evidence, KPIs, MAPE/R2, chart sources, finalists, scenarios, stress tests or diagnostics."
)
BACKTEST_SUPPORTED_MAX_HORIZON = 12
HORIZON_SUPPORT_NOTE = (
    "H1-H12 are the validated backtest-supported horizon; H13-H100 are long-range extrapolation, "
    "not validated 2050 accuracy."
)
HIGH_POPULATION_SMOKE_FIXTURE_NOTE = (
    "The high_population workbook is a technical smoke-test fixture: every user input is 2% above base, "
    "including unemployment, prices and starting target lags. It is not a decision-grade population-only scenario."
)
SCENARIO_ROLE_BASECASE = "basecase"
SCENARIO_ROLE_COMPARISON = "comparison"
SCENARIO_ROLE_OPTIONS = (SCENARIO_ROLE_BASECASE, SCENARIO_ROLE_COMPARISON)
TEMPLATE_FILENAME = "NLTF_forecast_input_template_20q.xlsx"

_FORECAST_SYMBOLS = {
    "FORECAST_BUILDER_NOTE",
    "FORECAST_BUILDER_TITLE",
    "BACKTEST_SUPPORTED_MAX_HORIZON",
    "HIGH_POPULATION_SMOKE_FIXTURE_NOTE",
    "HORIZON_SUPPORT_NOTE",
    "SCENARIO_ROLE_BASECASE",
    "SCENARIO_ROLE_COMPARISON",
    "SCENARIO_ROLE_OPTIONS",
    "TEMPLATE_FILENAME",
    "build_forecast_input_template_bytes",
    "forecast_pack_zip_bytes",
    "quarter_sort_key",
    "resolve_scenario_role",
    "run_forecast_workbook",
    "sanitize_scenario_name",
    "scenario_name_from_filename",
    "validate_forecast_workbook",
    "write_forecast_scenario_comparison",
}


class ForecastRunnerUnavailable(RuntimeError):
    pass


def _forced_fallback() -> bool:
    return os.environ.get(OPTIONAL_IMPORT_FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _load_forecast_runner() -> tuple[dict[str, Any], str | None]:
    if _forced_fallback():
        return {}, f"forced fallback via {OPTIONAL_IMPORT_FORCE_ENV}"
    try:
        module = importlib.import_module(".forecast_runner", package=__package__)
    except Exception as exc:
        return {}, f"model_dashboard.forecast_runner: {type(exc).__name__}: {exc}"
    missing = sorted(name for name in _FORECAST_SYMBOLS if not hasattr(module, name))
    if missing:
        return {}, "model_dashboard.forecast_runner: missing optional symbols: " + ", ".join(missing)
    return {name: getattr(module, name) for name in _FORECAST_SYMBOLS}, None


def _unavailable(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise ForecastRunnerUnavailable(
        "Forecast Builder is unavailable because optional forecast-runner imports failed."
    )


def quarter_sort_key(period: str) -> int:
    text = str(period).strip().upper()
    match = re.fullmatch(r"(\d{4})Q([1-4])", text)
    if not match:
        return 999999
    year, quarter = match.groups()
    return int(year) * 4 + int(quarter)


def sanitize_scenario_name(value: str | None) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "scenario")).strip("_").lower()
    return text or "scenario"


def scenario_name_from_filename(filename: str | Path | None) -> str:
    stem = Path(str(filename or "scenario")).stem
    for prefix in [
        "NLTF_forecast_input_template_",
        "forecast_input_",
        "completed_",
    ]:
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break
    return sanitize_scenario_name(stem or "scenario")


def resolve_scenario_role(
    *,
    scenario_role: str | None = None,
    scenario_name: str | None = None,
    workbook_filename: str | Path | None = None,
) -> tuple[str | None, str]:
    if scenario_role is None or not str(scenario_role).strip():
        text = ""
    else:
        text = sanitize_scenario_name(scenario_role)
    if text in {"base", "basecase", "base_case", "baseline", "reference"}:
        return SCENARIO_ROLE_BASECASE, "explicit"
    if text in {"comparison", "compare", "alternative", "alternate", "high_population", "upside", "downside"}:
        return SCENARIO_ROLE_COMPARISON, "explicit"
    combined = sanitize_scenario_name(f"{scenario_name or ''} {workbook_filename or ''}")
    has_base = "basecase" in combined or "base_case" in combined or re.search(r"(?:^|_)base(?:_|$)", combined)
    has_comparison = "high_population" in combined or any(
        token in combined.split("_") for token in ["comparison", "compare", "alternative", "alternate", "upside", "downside"]
    )
    if has_base == has_comparison:
        return None, "ambiguous"
    return (SCENARIO_ROLE_BASECASE if has_base else SCENARIO_ROLE_COMPARISON), "inferred_from_name"


_forecast, FORECAST_RUNNER_IMPORT_ERROR = _load_forecast_runner()
if FORECAST_RUNNER_IMPORT_ERROR is None:
    globals().update(_forecast)
else:
    build_forecast_input_template_bytes = _unavailable
    forecast_pack_zip_bytes = _unavailable
    run_forecast_workbook = _unavailable
    validate_forecast_workbook = _unavailable
    write_forecast_scenario_comparison = _unavailable

