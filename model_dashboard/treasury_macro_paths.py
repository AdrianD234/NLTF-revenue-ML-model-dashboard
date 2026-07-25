"""Governed Treasury BEFU 2026 baseline macro path.

Treasury publishes quarterly real-GDP levels through 2030Q2 and June-quarter
population anchors through 2030.  This module applies their growth path to the
model without replacing the model's real-dollar scale:

* the model aggregate-GDP level is held at its 2026Q1 Base value;
* Treasury's quarterly GDP index determines growth from that anchor;
* quarterly population is log-linearly interpolated between official June
  anchors;
* after 2030Q2, the original model quarter-on-quarter growth rates continue
  from the re-anchored Treasury endpoint.

The transform is deliberately macro-only.  Fuel prices, RUC prices, FED rates,
and all other price inputs remain untouched.
"""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd


TREASURY_BEFU26_SOURCE_URL = (
    "https://www.treasury.govt.nz/sites/default/files/2026-05/"
    "befu26-suppinfo-charts-data.xlsx"
)
TREASURY_BEFU26_SOURCE_WORKBOOK = "befu26-suppinfo-charts-data.xlsx"
TREASURY_BEFU26_SOURCE_SHA256 = (
    "C6D48384C11295A00AAA0DA20E2BECFDDCF15D0A6203F810005F8905D5A9D391"
)
TREASURY_MACRO_PATH_CSV = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "current_revenue_outlook"
    / "treasury_befu26_macro_path.csv"
)
TREASURY_ANCHOR_PERIOD = "2026Q1"
TREASURY_PATH_END_PERIOD = "2030Q2"
TREASURY_BEFU26_ANNUAL_AVERAGE_REAL_GDP_GROWTH_PCT = {
    2026: 1.2,
    2027: 2.3,
    2028: 3.2,
    2029: 2.7,
    2030: 2.5,
}

EXPECTED_PERIODS = tuple(
    [f"2025Q{quarter}" for quarter in range(2, 5)]
    + [
        f"{year}Q{quarter}"
        for year in range(2026, 2030)
        for quarter in range(1, 5)
    ]
    + [f"2030Q{quarter}" for quarter in range(1, 3)]
)
OFFICIAL_REAL_GDP_MILLION = {
    "2025Q2": 69886.0,
    "2025Q3": 70489.0,
    "2025Q4": 70664.0,
    "2026Q1": 70975.0,
    "2026Q2": 71144.0,
    "2026Q3": 71590.0,
    "2026Q4": 72153.0,
    "2027Q1": 72763.0,
    "2027Q2": 73368.0,
    "2027Q3": 73962.0,
    "2027Q4": 74534.0,
    "2028Q1": 75084.0,
    "2028Q2": 75609.0,
    "2028Q3": 76103.0,
    "2028Q4": 76592.0,
    "2029Q1": 77094.0,
    "2029Q2": 77589.0,
    "2029Q3": 78070.4,
    "2029Q4": 78542.0,
    "2030Q1": 79010.0,
    "2030Q2": 79478.0,
}
OFFICIAL_JUNE_POPULATION_MILLION = {
    "2025Q2": 5.323,
    "2026Q2": 5.370,
    "2027Q2": 5.432,
    "2028Q2": 5.497,
    "2029Q2": 5.562,
    "2030Q2": 5.628,
}
REQUIRED_COLUMNS = (
    "period",
    "treasury_real_gdp_sa_nzd_million",
    "real_gdp_source_status",
    "treasury_population_million",
    "population_source_status",
    "real_gdp_source_cell",
    "population_source_cell",
    "source_url",
    "source_workbook",
    "real_gdp_source_sheet",
    "population_source_sheet",
    "source_workbook_sha256",
)
_PRICE_INPUT_PATTERN = re.compile(
    r"(price|rate_cents|nominal_rate|ruc_rate|fed_rate)", re.IGNORECASE
)


def _quarter_number(period: str) -> int:
    match = re.fullmatch(r"(\d{4})Q([1-4])", str(period).strip())
    if match is None:
        raise ValueError(f"Invalid canonical quarter {period!r}.")
    return int(match.group(1)) * 4 + int(match.group(2)) - 1


def _previous_quarter(period: str) -> str:
    value = _quarter_number(period) - 1
    year, zero_based_quarter = divmod(value, 4)
    return f"{year}Q{zero_based_quarter + 1}"


def _is_price_input_column(column: str) -> bool:
    """Return True for price/rate levels and their own log/lead/lag features."""

    return (
        _PRICE_INPUT_PATTERN.search(column) is not None
        and "interaction" not in column.casefold()
    )


def _expected_interpolated_population(period: str) -> float:
    if period in OFFICIAL_JUNE_POPULATION_MILLION:
        return OFFICIAL_JUNE_POPULATION_MILLION[period]
    period_number = _quarter_number(period)
    anchors = sorted(
        (
            _quarter_number(anchor_period),
            anchor_value,
        )
        for anchor_period, anchor_value in OFFICIAL_JUNE_POPULATION_MILLION.items()
    )
    lower = max((anchor for anchor in anchors if anchor[0] < period_number), default=None)
    upper = min((anchor for anchor in anchors if anchor[0] > period_number), default=None)
    if lower is None or upper is None:
        raise ValueError(f"Period {period!r} is outside the governed population anchors.")
    weight = (period_number - lower[0]) / (upper[0] - lower[0])
    return float(lower[1] * (upper[1] / lower[1]) ** weight)


def validate_treasury_macro_path(frame: pd.DataFrame) -> None:
    """Raise ``ValueError`` when the committed BEFU26 path is not governed."""

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("Treasury macro path is missing columns: " + ", ".join(missing))

    source = frame.copy()
    source["period"] = source["period"].astype(str)
    if source["period"].duplicated(keep=False).any():
        raise ValueError("Treasury macro path contains duplicate quarters.")
    if tuple(source["period"]) != EXPECTED_PERIODS:
        raise ValueError("Treasury macro path must contain the exact 2025Q2-2030Q2 range.")

    for column in (
        "treasury_real_gdp_sa_nzd_million",
        "treasury_population_million",
    ):
        source[column] = pd.to_numeric(source[column], errors="coerce")
        if source[column].isna().any() or (~np.isfinite(source[column])).any():
            raise ValueError(f"Treasury macro path column {column!r} must be finite numeric.")
        if source[column].le(0).any():
            raise ValueError(f"Treasury macro path column {column!r} must be positive.")

    expected_gdp = pd.Series(
        [OFFICIAL_REAL_GDP_MILLION[period] for period in EXPECTED_PERIODS],
        dtype=float,
    )
    actual_gdp = source["treasury_real_gdp_sa_nzd_million"].reset_index(drop=True)
    if not np.allclose(actual_gdp, expected_gdp, rtol=0.0, atol=1e-9):
        raise ValueError("Treasury real-GDP values do not match the BEFU26 workbook.")

    expected_population = pd.Series(
        [_expected_interpolated_population(period) for period in EXPECTED_PERIODS],
        dtype=float,
    )
    actual_population = source["treasury_population_million"].reset_index(drop=True)
    if not np.allclose(actual_population, expected_population, rtol=0.0, atol=5e-10):
        raise ValueError(
            "Treasury population path does not reconcile to the official June anchors "
            "and log-linear interpolation."
        )

    official_population = source["period"].isin(OFFICIAL_JUNE_POPULATION_MILLION)
    if not source.loc[
        official_population, "population_source_status"
    ].astype(str).eq("official_june_anchor").all():
        raise ValueError("Official June population rows must be labelled official_june_anchor.")
    if not source.loc[
        ~official_population, "population_source_status"
    ].astype(str).eq("derived_log_linear_interpolation").all():
        raise ValueError(
            "Intervening population rows must be labelled derived_log_linear_interpolation."
        )
    if not source["real_gdp_source_status"].astype(str).eq(
        "official_published_quarterly_value"
    ).all():
        raise ValueError("Every Treasury real-GDP row must be labelled as an official value.")

    if not source["source_url"].astype(str).eq(TREASURY_BEFU26_SOURCE_URL).all():
        raise ValueError("Treasury macro path source URL does not match the governed source.")
    if not source["source_workbook"].astype(str).eq(
        TREASURY_BEFU26_SOURCE_WORKBOOK
    ).all():
        raise ValueError("Treasury macro path workbook name does not match the governed source.")
    if not source["source_workbook_sha256"].astype(str).str.upper().eq(
        TREASURY_BEFU26_SOURCE_SHA256
    ).all():
        raise ValueError("Treasury macro path workbook hash does not match the governed source.")
    if not source["real_gdp_source_sheet"].astype(str).eq("Table 1").all():
        raise ValueError("Treasury GDP lineage must point to Table 1.")
    if not source["population_source_sheet"].astype(str).eq("Table 6").all():
        raise ValueError("Treasury population lineage must point to Table 6.")
    for column in ("real_gdp_source_cell", "population_source_cell"):
        if source[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(f"Treasury lineage column {column!r} must be populated.")


def load_treasury_macro_path(repo_root: str | Path | None = None) -> pd.DataFrame:
    """Load and validate the committed BEFU26 quarterly macro path."""

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    source = (
        root
        if root.suffix.lower() == ".csv"
        else root
        / "data"
        / "current_revenue_outlook"
        / "treasury_befu26_macro_path.csv"
    )
    frame = pd.read_csv(source)
    validate_treasury_macro_path(frame)
    return frame.reset_index(drop=True)


def _base_scenario_name(frame: pd.DataFrame) -> str:
    required = {"scenario_name", "role", "stream", "canonical_period"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Scenario inputs are missing required columns: " + ", ".join(sorted(missing))
        )
    role = frame["role"].fillna("").astype(str).str.strip().str.casefold()
    names = (
        frame.loc[role.eq("basecase"), "scenario_name"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    if len(names) != 1:
        raise ValueError(f"Expected exactly one Basecase scenario; found {len(names)}: {names}")
    return names[0]


def _numeric_series(frame: pd.DataFrame, column: str, *, context: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"{context} requires scenario-input column {column!r}.")
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any() or (~np.isfinite(values)).any() or values.le(0).any():
        raise ValueError(f"{context} requires finite positive {column!r} values.")
    return values.astype(float)


def _period_value_lookup(
    frame: pd.DataFrame,
    *,
    column: str,
    context: str,
) -> dict[str, float]:
    periods = frame["canonical_period"].astype(str)
    if periods.duplicated(keep=False).any():
        duplicates = sorted(periods[periods.duplicated(keep=False)].unique())
        raise ValueError(f"{context} contains duplicate quarters: {duplicates}")
    values = _numeric_series(frame, column, context=context)
    return dict(zip(periods, values, strict=True))


def _rebuild_macro_features(
    result: pd.DataFrame,
    *,
    base_mask: pd.Series,
    treasury_gdp_million: dict[str, float],
) -> None:
    def assign_values(
        column: str,
        indices: pd.Index,
        values: np.ndarray | pd.Series,
    ) -> None:
        if column not in result.columns:
            return
        array = np.asarray(values)
        if pd.api.types.is_string_dtype(result[column].dtype):
            result.loc[indices, column] = [
                "" if pd.isna(value) else format(float(value), ".17g")
                for value in array
            ]
        else:
            result.loc[indices, column] = array

    for stream_name in ("LIGHT_RUC", "HEAVY_RUC"):
        stream_mask = base_mask & result["stream"].astype(str).eq(stream_name)
        stream = result.loc[stream_mask].copy()
        periods = stream["canonical_period"].astype(str)
        order = periods.map(_quarter_number)
        ordered_index = stream.assign(_order=order).sort_values("_order", kind="stable").index
        log_gdp = np.log(
            pd.to_numeric(result.loc[ordered_index, "real_gdp_sa_nzd"], errors="coerce")
        )
        if "log_real_gdp" in result.columns:
            assign_values("log_real_gdp", ordered_index, log_gdp.to_numpy())
        if "log_real_gdp_sa_nzd" in result.columns:
            assign_values(
                "log_real_gdp_sa_nzd", ordered_index, log_gdp.to_numpy()
            )
        if "diff_log_real_gdp" in result.columns:
            differences = log_gdp.diff()
            first_index = ordered_index[0]
            first_period = str(result.at[first_index, "canonical_period"])
            previous_period = _previous_quarter(first_period)
            if (
                first_period in treasury_gdp_million
                and previous_period in treasury_gdp_million
            ):
                differences.iloc[0] = np.log(
                    treasury_gdp_million[first_period]
                    / treasury_gdp_million[previous_period]
                )
            assign_values(
                "diff_log_real_gdp", ordered_index, differences.to_numpy()
            )

        price_column = (
            "real_light_ruc_price_nzd_per_1000km"
            if stream_name == "LIGHT_RUC"
            else "real_heavy_ruc_price_nzd_per_1000km"
        )
        interaction_column = (
            "gdp_light_ruc_price_interaction"
            if stream_name == "LIGHT_RUC"
            else "gdp_heavy_ruc_price_interaction"
        )
        if interaction_column in result.columns:
            price = _numeric_series(
                result.loc[ordered_index],
                price_column,
                context=f"{stream_name} GDP-price interaction",
            )
            assign_values(
                interaction_column,
                ordered_index,
                log_gdp.to_numpy() * np.log(price.to_numpy()),
            )

    ped_mask = base_mask & result["stream"].astype(str).eq("PED")
    ped_index = result.loc[ped_mask].index
    population = _numeric_series(
        result.loc[ped_index],
        "population",
        context="PED population transform",
    )
    gdp_per_capita = _numeric_series(
        result.loc[ped_index],
        "real_gdp_per_capita_nzd",
        context="PED GDP-per-capita transform",
    )
    log_population = np.log(population)
    log_gdp_per_capita = np.log(gdp_per_capita)
    if "log_population" in result.columns:
        assign_values("log_population", ped_index, log_population.to_numpy())
    if "log_real_gdp_per_capita" in result.columns:
        assign_values(
            "log_real_gdp_per_capita",
            ped_index,
            log_gdp_per_capita.to_numpy(),
        )
    if "log_real_gdp_per_capita_nzd" in result.columns:
        assign_values(
            "log_real_gdp_per_capita_nzd",
            ped_index,
            log_gdp_per_capita.to_numpy(),
        )
    if "gdp_petrol_interaction" in result.columns:
        petrol = _numeric_series(
            result.loc[ped_index],
            "real_petrol_price_cents_per_litre",
            context="PED GDP-petrol interaction",
        )
        assign_values(
            "gdp_petrol_interaction",
            ped_index,
            log_gdp_per_capita.to_numpy() * np.log(petrol.to_numpy()),
        )


def apply_treasury_baseline_macro_path(
    base_inputs: pd.DataFrame,
    repo_root: str | Path | None = None,
) -> pd.DataFrame:
    """Apply BEFU26 GDP/population to Base while preserving model units.

    Non-Base scenarios are returned unchanged.  The model's aggregate-GDP
    dollar level at 2026Q1 is the anchor, so only the Treasury growth profile
    is imported.  The PED per-capita series is derived from the same aggregate
    GDP and Treasury population path used by the RUC streams.
    """

    if base_inputs is None or base_inputs.empty:
        raise ValueError("Base scenario_input_wide rows are required.")

    result = base_inputs.copy(deep=True)
    base_name = _base_scenario_name(result)
    base_mask = result["scenario_name"].astype(str).eq(base_name)
    base = result.loc[base_mask].copy()
    required_streams = {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    actual_streams = set(base["stream"].dropna().astype(str))
    missing_streams = sorted(required_streams.difference(actual_streams))
    if missing_streams:
        raise ValueError(
            "Treasury macro transform requires Base rows for: " + ", ".join(missing_streams)
        )

    macro = load_treasury_macro_path(repo_root)
    macro_by_period = macro.set_index("period")
    treasury_gdp_million = (
        macro_by_period["treasury_real_gdp_sa_nzd_million"].astype(float).to_dict()
    )
    treasury_population = (
        macro_by_period["treasury_population_million"].astype(float).to_dict()
    )

    ruc_paths: list[dict[str, float]] = []
    for stream_name in ("LIGHT_RUC", "HEAVY_RUC"):
        stream = base[base["stream"].astype(str).eq(stream_name)]
        ruc_paths.append(
            _period_value_lookup(
                stream,
                column="real_gdp_sa_nzd",
                context=f"{stream_name} Base GDP path",
            )
        )
    common_periods = sorted(set(ruc_paths[0]).intersection(ruc_paths[1]), key=_quarter_number)
    if TREASURY_ANCHOR_PERIOD not in common_periods:
        raise ValueError(f"Base GDP path is missing anchor {TREASURY_ANCHOR_PERIOD}.")
    if TREASURY_PATH_END_PERIOD not in common_periods:
        raise ValueError(f"Base GDP path is missing endpoint {TREASURY_PATH_END_PERIOD}.")
    for period in common_periods:
        values = [path[period] for path in ruc_paths]
        if not np.isclose(values[0], values[1], rtol=1e-10, atol=1e-3):
            raise ValueError(
                f"LIGHT_RUC and HEAVY_RUC Base GDP disagree in {period}; "
                "a common macro path cannot be applied."
            )
    original_gdp = {
        period: float(np.mean([path[period] for path in ruc_paths]))
        for period in common_periods
    }
    model_anchor_gdp = original_gdp[TREASURY_ANCHOR_PERIOD]
    treasury_anchor_gdp = treasury_gdp_million[TREASURY_ANCHOR_PERIOD]
    original_end_gdp = original_gdp[TREASURY_PATH_END_PERIOD]
    reanchored_end_gdp = (
        model_anchor_gdp
        * treasury_gdp_million[TREASURY_PATH_END_PERIOD]
        / treasury_anchor_gdp
    )

    gdp_path: dict[str, float] = {}
    for period in common_periods:
        period_number = _quarter_number(period)
        if period in treasury_gdp_million:
            gdp_path[period] = (
                model_anchor_gdp * treasury_gdp_million[period] / treasury_anchor_gdp
            )
        elif period_number > _quarter_number(TREASURY_PATH_END_PERIOD):
            gdp_path[period] = (
                reanchored_end_gdp * original_gdp[period] / original_end_gdp
            )
        else:
            gdp_path[period] = original_gdp[period]

    ped = base[base["stream"].astype(str).eq("PED")]
    original_population = _period_value_lookup(
        ped,
        column="population",
        context="PED Base population path",
    )
    if TREASURY_PATH_END_PERIOD not in original_population:
        raise ValueError(f"PED Base population path is missing {TREASURY_PATH_END_PERIOD}.")
    original_end_population = original_population[TREASURY_PATH_END_PERIOD]
    reanchored_end_population = (
        treasury_population[TREASURY_PATH_END_PERIOD] * 1_000_000.0
    )
    population_path: dict[str, float] = {}
    for period, original_value in original_population.items():
        period_number = _quarter_number(period)
        if period in treasury_population:
            population_path[period] = treasury_population[period] * 1_000_000.0
        elif period_number > _quarter_number(TREASURY_PATH_END_PERIOD):
            population_path[period] = (
                reanchored_end_population
                * original_value
                / original_end_population
            )
        else:
            population_path[period] = original_value

    base_period = result["canonical_period"].astype(str)

    def assign_numeric(column: str, mask: pd.Series, values: np.ndarray) -> None:
        """Assign without widening untouched Arrow-string fixture columns."""

        if pd.api.types.is_string_dtype(result[column].dtype):
            result.loc[mask, column] = [
                format(float(value), ".17g") for value in values
            ]
        else:
            result.loc[mask, column] = values

    for stream_name in ("LIGHT_RUC", "HEAVY_RUC"):
        mask = base_mask & result["stream"].astype(str).eq(stream_name)
        mapped = base_period.loc[mask].map(gdp_path)
        if mapped.isna().any():
            missing = sorted(base_period.loc[mask][mapped.isna()].unique())
            raise ValueError(f"Treasury GDP transform could not map {stream_name}: {missing}")
        assign_numeric("real_gdp_sa_nzd", mask, mapped.to_numpy(dtype=float))

    ped_mask = base_mask & result["stream"].astype(str).eq("PED")
    ped_periods = base_period.loc[ped_mask]
    mapped_gdp = ped_periods.map(gdp_path)
    mapped_population = ped_periods.map(population_path)
    if mapped_gdp.isna().any() or mapped_population.isna().any():
        raise ValueError("Treasury macro transform could not map all PED Base quarters.")
    assign_numeric(
        "population",
        ped_mask,
        mapped_population.to_numpy(dtype=float),
    )
    assign_numeric(
        "real_gdp_per_capita_nzd",
        ped_mask,
        mapped_gdp.to_numpy(dtype=float)
        / mapped_population.to_numpy(dtype=float),
    )

    result["treasury_macro_applied"] = False
    result.loc[base_mask, "treasury_macro_applied"] = True
    result["treasury_macro_phase"] = ""
    official_mask = (
        base_mask
        & base_period.map(lambda period: period in treasury_gdp_million)
    )
    continuation_mask = (
        base_mask
        & base_period.map(_quarter_number).gt(_quarter_number(TREASURY_PATH_END_PERIOD))
    )
    result.loc[official_mask, "treasury_macro_phase"] = "befu26_quarterly_path"
    result.loc[continuation_mask, "treasury_macro_phase"] = (
        "reanchored_original_quarterly_growth"
    )
    result["treasury_macro_source_url"] = ""
    result.loc[base_mask, "treasury_macro_source_url"] = TREASURY_BEFU26_SOURCE_URL
    result["treasury_macro_source_workbook_sha256"] = ""
    result.loc[base_mask, "treasury_macro_source_workbook_sha256"] = (
        TREASURY_BEFU26_SOURCE_SHA256
    )

    _rebuild_macro_features(
        result,
        base_mask=base_mask,
        treasury_gdp_million=treasury_gdp_million,
    )

    # A defensive postcondition makes the one-way design explicit: this
    # transform is never allowed to mutate a price or policy-rate input.
    price_columns = [
        column for column in base_inputs.columns if _is_price_input_column(column)
    ]
    for column in price_columns:
        if not result[column].equals(base_inputs[column]):
            raise AssertionError(
                f"Treasury macro transform unexpectedly changed price input {column!r}."
            )
    return result
