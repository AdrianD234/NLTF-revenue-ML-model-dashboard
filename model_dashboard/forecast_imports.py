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

# Horizon zones for June-year (fiscal) rows.
#
# The quarterly forecast rows already carry H1-H12 / H13+ scope, but the
# decision-facing Revenue Outlook is aggregated to June years, and a June year
# can straddle a support boundary.  Classifying at the fiscal-year level is
# therefore its own governed step: FY2029 is half beyond H12 and FY2030 is
# entirely beyond it, which is invisible if only the quarterly rows are
# labelled.
#
# Three governed support states, not two.  Collapsing everything past H12 into
# one bucket would equate FY2030 - which has extended rolling-origin evidence
# from scripts/evaluate_long_horizon_rolling_origin.py - with FY2035, which has
# none at all.
EXTENDED_EVIDENCE_MAX_HORIZON = 20
FORECAST_HORIZON_ZONE_ACTUAL = "actual_or_nowcast"
FORECAST_HORIZON_ZONE_VALIDATED = "backtest_supported_h1_h12"
FORECAST_HORIZON_ZONE_EXTENDED = "extended_conditional_evidence_h13_h20"
FORECAST_HORIZON_ZONE_UNVALIDATED = "unvalidated_extrapolation_h21_plus"
FORECAST_HORIZON_ZONE_MIXED = "mixed_horizon_support"
# Retained for callers that predate the three-state split.
FORECAST_HORIZON_ZONE_STRADDLE = FORECAST_HORIZON_ZONE_MIXED
FORECAST_HORIZON_ZONE_EXTRAPOLATION = FORECAST_HORIZON_ZONE_UNVALIDATED
LONG_RANGE_EXTRAPOLATION_WARNING = (
    "long-range extrapolation - not validated to the short-term standard"
)
FORECAST_HORIZON_ZONE_LABELS = {
    FORECAST_HORIZON_ZONE_ACTUAL: "Actual or nowcast quarters",
    FORECAST_HORIZON_ZONE_VALIDATED: "H1-H12 backtest-supported horizon",
    FORECAST_HORIZON_ZONE_EXTENDED: (
        "H13-H20 extended conditional evidence - thinner samples, "
        + LONG_RANGE_EXTRAPOLATION_WARNING
    ),
    FORECAST_HORIZON_ZONE_UNVALIDATED: (
        "H21+ no extended evaluation evidence - " + LONG_RANGE_EXTRAPOLATION_WARNING
    ),
    FORECAST_HORIZON_ZONE_MIXED: (
        "Mixed horizon support across this year - part is "
        + LONG_RANGE_EXTRAPOLATION_WARNING
    ),
}
FORECAST_HORIZON_SCOPE_LABELS = {
    FORECAST_HORIZON_ZONE_ACTUAL: "",
    FORECAST_HORIZON_ZONE_VALIDATED: "H1-H12",
    FORECAST_HORIZON_ZONE_EXTENDED: "H13-H20",
    FORECAST_HORIZON_ZONE_UNVALIDATED: "H21+",
}


def june_year_quarters(june_year: Any) -> tuple[str, ...]:
    """Return the four canonical quarters of a NZ June fiscal year."""

    year = int(june_year)
    return (f"{year - 1}Q3", f"{year - 1}Q4", f"{year}Q1", f"{year}Q2")


def horizon_for_quarter(period: Any, model_training_cutoff: str) -> int | None:
    """Steps ahead of the training cutoff; <= 0 means actual or in-sample."""

    target = quarter_sort_key(period)
    cutoff = quarter_sort_key(model_training_cutoff)
    if target >= 999999 or cutoff >= 999999:
        return None
    return target - cutoff


def horizon_support_zone(
    horizon: Any,
    *,
    backtest_supported_max_horizon: int = BACKTEST_SUPPORTED_MAX_HORIZON,
    extended_evidence_max_horizon: int = EXTENDED_EVIDENCE_MAX_HORIZON,
) -> str:
    """Governed support state for one forecast horizon."""

    value = int(horizon)
    if value <= 0:
        return FORECAST_HORIZON_ZONE_ACTUAL
    if value <= backtest_supported_max_horizon:
        return FORECAST_HORIZON_ZONE_VALIDATED
    if value <= extended_evidence_max_horizon:
        return FORECAST_HORIZON_ZONE_EXTENDED
    return FORECAST_HORIZON_ZONE_UNVALIDATED


def june_year_horizon_profile(
    june_year: Any,
    model_training_cutoff: str,
    *,
    backtest_supported_max_horizon: int = BACKTEST_SUPPORTED_MAX_HORIZON,
    extended_evidence_max_horizon: int = EXTENDED_EVIDENCE_MAX_HORIZON,
) -> dict[str, Any]:
    """Classify one June year across the three governed support states."""

    empty = {
        "horizon_zone": "",
        "horizon_zone_label": "",
        "horizon_scope": "",
        "first_horizon": None,
        "last_horizon": None,
        "forecast_quarters": 0,
        "actual_quarters": 0,
        "quarters_backtest_supported": 0,
        "quarters_extended_evidence": 0,
        "quarters_unvalidated": 0,
        "quarters_beyond_validated_horizon": 0,
        "share_beyond_validated_horizon": 0.0,
    }
    horizons = [
        horizon_for_quarter(period, model_training_cutoff)
        for period in june_year_quarters(june_year)
    ]
    if any(value is None for value in horizons):
        return empty
    zones = [
        horizon_support_zone(
            value,
            backtest_supported_max_horizon=backtest_supported_max_horizon,
            extended_evidence_max_horizon=extended_evidence_max_horizon,
        )
        for value in horizons
    ]
    counts = {
        FORECAST_HORIZON_ZONE_ACTUAL: zones.count(FORECAST_HORIZON_ZONE_ACTUAL),
        FORECAST_HORIZON_ZONE_VALIDATED: zones.count(FORECAST_HORIZON_ZONE_VALIDATED),
        FORECAST_HORIZON_ZONE_EXTENDED: zones.count(FORECAST_HORIZON_ZONE_EXTENDED),
        FORECAST_HORIZON_ZONE_UNVALIDATED: zones.count(
            FORECAST_HORIZON_ZONE_UNVALIDATED
        ),
    }
    forecast_zones = [zone for zone in zones if zone != FORECAST_HORIZON_ZONE_ACTUAL]
    if not forecast_zones:
        zone = FORECAST_HORIZON_ZONE_ACTUAL
    elif len(set(zones)) == 1:
        zone = zones[0]
    elif len(set(forecast_zones)) == 1 and counts[FORECAST_HORIZON_ZONE_ACTUAL]:
        # Part actual, part forecast, but the forecast half is one support
        # state - report that state rather than the vaguer "mixed".
        zone = forecast_zones[0]
    else:
        zone = FORECAST_HORIZON_ZONE_MIXED
    if zone == FORECAST_HORIZON_ZONE_MIXED:
        present = [
            FORECAST_HORIZON_SCOPE_LABELS[state]
            for state in (
                FORECAST_HORIZON_ZONE_VALIDATED,
                FORECAST_HORIZON_ZONE_EXTENDED,
                FORECAST_HORIZON_ZONE_UNVALIDATED,
            )
            if counts[state]
        ]
        scope = "/".join(present)
    else:
        scope = FORECAST_HORIZON_SCOPE_LABELS[zone]
    beyond = (
        counts[FORECAST_HORIZON_ZONE_EXTENDED]
        + counts[FORECAST_HORIZON_ZONE_UNVALIDATED]
    )
    return {
        "horizon_zone": zone,
        "horizon_zone_label": FORECAST_HORIZON_ZONE_LABELS[zone],
        "horizon_scope": scope,
        "first_horizon": min(horizons),
        "last_horizon": max(horizons),
        "forecast_quarters": len(forecast_zones),
        "actual_quarters": counts[FORECAST_HORIZON_ZONE_ACTUAL],
        "quarters_backtest_supported": counts[FORECAST_HORIZON_ZONE_VALIDATED],
        "quarters_extended_evidence": counts[FORECAST_HORIZON_ZONE_EXTENDED],
        "quarters_unvalidated": counts[FORECAST_HORIZON_ZONE_UNVALIDATED],
        "quarters_beyond_validated_horizon": beyond,
        "share_beyond_validated_horizon": beyond / len(horizons),
    }

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

