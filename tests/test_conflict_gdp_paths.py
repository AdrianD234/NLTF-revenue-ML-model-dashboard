from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.conflict_gdp_paths import (
    TREASURY_CONFLICT_GDP_URL,
    apply_conflict_gdp_impact,
    apply_conflict_unemployment_impact,
    build_conflict_gdp_paths,
    build_conflict_unemployment_paths,
    conflict_unemployment_input_audit,
    load_conflict_gdp_calibration,
    load_conflict_unemployment_calibration,
    validate_conflict_gdp_paths,
    validate_conflict_unemployment_paths,
)
from model_dashboard.conflict_fuel_paths import EXPECTED_PERIODS


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    ROOT
    / "data"
    / "engine_ar1"
    / "current_revenue_outlook"
    / "scenario_inputs"
    / "scenario_input_wide.parquet"
)


def test_governed_conflict_gdp_path_hits_treasury_anchors_and_recovers() -> None:
    paths = build_conflict_gdp_paths(ROOT)
    assert len(paths) == 3 * len(EXPECTED_PERIODS)
    assert not paths.duplicated(["severity", "period"]).any()
    anchor = paths[paths["period"].eq("2027Q1")].set_index("severity")
    assert float(anchor.at["medium", "real_gdp_level_impact_pct"]) == pytest.approx(
        -1.5, abs=1e-10
    )
    assert float(anchor.at["high", "real_gdp_level_impact_pct"]) == pytest.approx(
        -3.1, abs=1e-10
    )
    for severity in ("medium", "high"):
        selected = paths[paths["severity"].eq(severity)]
        assert (
            selected.loc[selected["real_gdp_level_loss"].idxmax(), "period"]
            == "2027Q1"
        )
    recovered = paths.set_index(["severity", "period"])[
        "real_gdp_level_factor"
    ]
    assert float(recovered.at[("low", "2027Q2")]) == pytest.approx(1.0)
    assert float(recovered.at[("medium", "2028Q2")]) == pytest.approx(1.0)


def test_conflict_gdp_factor_is_ordered_and_has_no_reverse_feedback() -> None:
    paths = build_conflict_gdp_paths(ROOT)
    pivot = paths.pivot(
        index="period", columns="severity", values="real_gdp_level_factor"
    )
    assert (pivot["high"] <= pivot["medium"] + 1e-12).all()
    assert (pivot["medium"] <= pivot["low"] + 1e-12).all()
    assert not paths["reverse_fuel_feedback_applied"].astype(bool).any()
    np.testing.assert_allclose(
        paths["real_gdp_level_factor"],
        1.0 + paths["real_gdp_level_impact_pct"] / 100.0,
        rtol=0.0,
        atol=1e-12,
    )


def test_conflict_gdp_transform_changes_only_gdp_level_fields() -> None:
    inputs = pd.read_parquet(INPUT_PATH)
    base = inputs[inputs["role"].astype(str).str.casefold().eq("basecase")].copy()
    transformed = apply_conflict_gdp_impact(
        base,
        severity="medium",
        repo_root=ROOT,
    )
    price_columns = [
        column
        for column in base.columns
        if any(token in column.casefold() for token in ("price", "rate"))
        and "interaction" not in column.casefold()
    ]
    pd.testing.assert_frame_equal(
        transformed[price_columns],
        base[price_columns],
        check_exact=True,
        check_dtype=True,
    )
    period = transformed["canonical_period"].astype(str)
    for stream, field in (
        ("PED", "real_gdp_per_capita_nzd"),
        ("LIGHT_RUC", "real_gdp_sa_nzd"),
        ("HEAVY_RUC", "real_gdp_sa_nzd"),
    ):
        mask = transformed["stream"].astype(str).eq(stream) & period.eq("2027Q1")
        before = float(pd.to_numeric(base.loc[mask, field], errors="coerce").iloc[0])
        after = float(
            pd.to_numeric(transformed.loc[mask, field], errors="coerce").iloc[0]
        )
        assert after / before == pytest.approx(0.985, abs=1e-12)


def test_conflict_gdp_validation_rejects_bad_factor_identity() -> None:
    paths = build_conflict_gdp_paths(ROOT)
    broken = paths.copy()
    broken.loc[0, "real_gdp_level_factor"] = 0.5
    with pytest.raises(ValueError, match="factor/loss identity"):
        validate_conflict_gdp_paths(broken)


def test_conflict_gdp_calibration_is_exact_and_source_backed() -> None:
    calibration = load_conflict_gdp_calibration(ROOT)
    assert calibration.set_index("severity")[
        "official_real_gdp_level_impact_pct"
    ].to_dict() == {"high": -3.1, "medium": -1.5}
    assert calibration["source_url"].astype(str).str.startswith("https://").all()


# ---------------------------------------------------------------------------
# Conflict unemployment channel
# ---------------------------------------------------------------------------

UNEMPLOYMENT_CSV = (
    ROOT / "data" / "current_revenue_outlook" / "conflict_unemployment_calibration.csv"
)
EXPECTED_UNEMPLOYMENT_GAPS = {
    ("medium", 2026): 0.1,
    ("medium", 2027): 0.8,
    ("medium", 2028): 0.3,
    ("high", 2026): 0.4,
    ("high", 2027): 1.9,
    ("high", 2028): 1.0,
}


def _base_scenario_input_rows() -> pd.DataFrame:
    inputs = pd.read_parquet(INPUT_PATH)
    return (
        inputs[inputs["role"].astype(str).str.casefold().eq("basecase")]
        .copy()
        .reset_index(drop=True)
    )


def _calibration_root_with(frame: pd.DataFrame, tmp_path) -> "Path":
    directory = tmp_path / "data" / "current_revenue_outlook"
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / "conflict_unemployment_calibration.csv", index=False)
    return tmp_path


def test_conflict_unemployment_calibration_is_exact_and_source_backed() -> None:
    calibration = load_conflict_unemployment_calibration(ROOT)
    assert len(calibration) == 6
    observed = {
        (str(row.severity), int(row.calendar_year)): float(row.unemployment_gap_pp)
        for row in calibration.itertuples(index=False)
    }
    assert observed == pytest.approx(EXPECTED_UNEMPLOYMENT_GAPS, abs=1e-12)
    assert calibration["source_url"].astype(str).eq(TREASURY_CONFLICT_GDP_URL).all()
    assert calibration["calibration_status"].astype(str).eq("official_anchor").all()
    np.testing.assert_allclose(
        calibration["unemployment_gap_pp"],
        calibration["official_unemployment_rate_pct"]
        - calibration["base_unemployment_rate_pct"],
        rtol=0.0,
        atol=1e-9,
    )


def test_conflict_unemployment_calibration_fails_closed_on_missing_file(
    tmp_path,
) -> None:
    with pytest.raises(FileNotFoundError, match="calibration is missing"):
        load_conflict_unemployment_calibration(tmp_path)


def test_conflict_unemployment_calibration_fails_closed_on_missing_columns(
    tmp_path,
) -> None:
    calibration = pd.read_csv(UNEMPLOYMENT_CSV)
    broken = calibration.drop(columns=["unemployment_gap_pp"])
    root = _calibration_root_with(broken, tmp_path)
    with pytest.raises(ValueError, match="missing columns"):
        load_conflict_unemployment_calibration(root)


def test_conflict_unemployment_calibration_fails_closed_on_tampered_gap(
    tmp_path,
) -> None:
    calibration = pd.read_csv(UNEMPLOYMENT_CSV)
    tampered = calibration.copy()
    tampered.loc[
        tampered["severity"].eq("medium") & tampered["calendar_year"].eq(2027),
        ["official_unemployment_rate_pct", "unemployment_gap_pp"],
    ] = [5.2, 0.5]
    root = _calibration_root_with(tampered, tmp_path)
    with pytest.raises(ValueError, match="no longer match the Treasury"):
        load_conflict_unemployment_calibration(root)


def test_conflict_unemployment_calibration_fails_closed_on_wrong_url(
    tmp_path,
) -> None:
    calibration = pd.read_csv(UNEMPLOYMENT_CSV)
    tampered = calibration.copy()
    tampered.loc[0, "source_url"] = "https://example.com/not-the-treasury-note.pdf"
    root = _calibration_root_with(tampered, tmp_path)
    with pytest.raises(ValueError, match="source URL"):
        load_conflict_unemployment_calibration(root)


def test_conflict_unemployment_calibration_fails_closed_on_missing_year(
    tmp_path,
) -> None:
    calibration = pd.read_csv(UNEMPLOYMENT_CSV)
    truncated = calibration[~calibration["calendar_year"].eq(2028)]
    root = _calibration_root_with(truncated, tmp_path)
    with pytest.raises(ValueError, match="cover exactly"):
        load_conflict_unemployment_calibration(root)


def test_conflict_unemployment_paths_quarterly_mapping_and_taper() -> None:
    paths = build_conflict_unemployment_paths(ROOT)
    assert len(paths) == 3 * len(EXPECTED_PERIODS)
    assert not paths.duplicated(["severity", "period"]).any()
    gaps = paths.set_index(["severity", "period"])["unemployment_gap_pp"]
    for (severity, year), gap in EXPECTED_UNEMPLOYMENT_GAPS.items():
        for quarter in range(1, 5):
            assert float(gaps.at[(severity, f"{year}Q{quarter}")]) == pytest.approx(
                gap, abs=1e-12
            )
    # Medium tapers linearly to exactly zero across 2029.
    for quarter, expected in ((1, 0.225), (2, 0.15), (3, 0.075), (4, 0.0)):
        assert float(gaps.at[("medium", f"2029Q{quarter}")]) == pytest.approx(
            expected, abs=1e-12
        )
    assert float(gaps.at[("medium", "2029Q4")]) == 0.0
    # High holds the 2028 gap through 2029 then tapers to zero across 2030.
    for quarter in range(1, 5):
        assert float(gaps.at[("high", f"2029Q{quarter}")]) == pytest.approx(
            1.0, abs=1e-12
        )
    for quarter, expected in ((1, 0.75), (2, 0.5), (3, 0.25), (4, 0.0)):
        assert float(gaps.at[("high", f"2030Q{quarter}")]) == pytest.approx(
            expected, abs=1e-12
        )
    # Every severity ends the governed window at exactly zero.
    for severity in ("low", "medium", "high"):
        assert float(gaps.at[(severity, "2030Q4")]) == 0.0
    low = paths[paths["severity"].eq("low")]
    assert low["unemployment_gap_pp"].eq(0.0).all()
    assert low["source_status"].astype(str).eq("no_official_anchor").all()
    assert paths["source_url"].astype(str).eq(TREASURY_CONFLICT_GDP_URL).all()


def test_conflict_unemployment_paths_validation_rejects_tampering() -> None:
    paths = build_conflict_unemployment_paths(ROOT)
    negative = paths.copy()
    negative.loc[0, "unemployment_gap_pp"] = -0.1
    with pytest.raises(ValueError, match="non-negative"):
        validate_conflict_unemployment_paths(negative)
    unbounded = paths.copy()
    unbounded.loc[
        unbounded["severity"].eq("high")
        & unbounded["period"].eq("2027Q1"),
        "unemployment_gap_pp",
    ] = 5.0
    with pytest.raises(ValueError, match="sanity bound"):
        validate_conflict_unemployment_paths(unbounded)
    unrecovered = paths.copy()
    unrecovered.loc[
        unrecovered["severity"].eq("medium")
        & unrecovered["period"].eq("2030Q4"),
        "unemployment_gap_pp",
    ] = 0.05
    with pytest.raises(ValueError, match="exactly zero"):
        validate_conflict_unemployment_paths(unrecovered)
    off_anchor = paths.copy()
    off_anchor.loc[
        off_anchor["severity"].eq("medium")
        & off_anchor["period"].eq("2027Q2"),
        "unemployment_gap_pp",
    ] = 0.9
    with pytest.raises(ValueError, match="no longer meets"):
        validate_conflict_unemployment_paths(off_anchor)


def test_conflict_unemployment_transform_adjusts_only_unemployment_rate() -> None:
    base = _base_scenario_input_rows()
    transformed = apply_conflict_unemployment_impact(
        base,
        severity="medium",
        repo_root=ROOT,
    )
    added = {
        "conflict_unemployment_gap_pp",
        "conflict_unemployment_source_url",
        "conflict_unemployment_basis",
    }
    assert added.issubset(transformed.columns)
    untouched = [
        column
        for column in base.columns
        if column != "unemployment_rate"
    ]
    pd.testing.assert_frame_equal(
        transformed[untouched],
        base[untouched],
        check_exact=True,
        check_dtype=True,
    )
    # log_unemployment_rate stays byte-identical: the replay recomputes it.
    assert (
        transformed["log_unemployment_rate"] == base["log_unemployment_rate"]
    ).all()
    # LIGHT_RUC has no unemployment input and stays byte-identical.
    light_mask = base["stream"].astype(str).eq("LIGHT_RUC")
    assert (
        transformed.loc[light_mask, "unemployment_rate"]
        == base.loc[light_mask, "unemployment_rate"]
    ).all()
    # String dtype is preserved for the adjusted field.
    assert pd.api.types.is_string_dtype(transformed["unemployment_rate"].dtype)
    period = transformed["canonical_period"].astype(str)
    for stream in ("PED", "HEAVY_RUC"):
        stream_mask = transformed["stream"].astype(str).eq(stream)
        for anchor_period, gap in (
            ("2026Q1", 0.1),
            ("2027Q1", 0.8),
            ("2028Q1", 0.3),
            ("2029Q2", 0.15),
        ):
            mask = stream_mask & period.eq(anchor_period)
            before = float(
                pd.to_numeric(base.loc[mask.values, "unemployment_rate"]).iloc[0]
            )
            after = float(
                pd.to_numeric(transformed.loc[mask, "unemployment_rate"]).iloc[0]
            )
            assert after - before == pytest.approx(gap / 100.0, abs=1e-15)
        # Beyond the governed window the gap is zero and the value is
        # numerically unchanged (to within the 1-ULP pandas string-parse
        # noise inherent in the string-dtype round trip).
        tail_mask = stream_mask & period.eq("2035Q1")
        before = float(
            pd.to_numeric(base.loc[tail_mask.values, "unemployment_rate"]).iloc[0]
        )
        after = float(
            pd.to_numeric(transformed.loc[tail_mask, "unemployment_rate"]).iloc[0]
        )
        assert after == pytest.approx(before, rel=1e-13)
    assert (
        pd.to_numeric(
            transformed.loc[light_mask, "conflict_unemployment_gap_pp"]
        )
        .eq(0.0)
        .all()
    )


def test_conflict_unemployment_transform_rejects_unknown_severity() -> None:
    base = _base_scenario_input_rows()
    with pytest.raises(ValueError, match="Unknown conflict unemployment severity"):
        apply_conflict_unemployment_impact(base, severity="extreme", repo_root=ROOT)


def test_conflict_unemployment_low_severity_is_numerically_neutral() -> None:
    base = _base_scenario_input_rows()
    transformed = apply_conflict_unemployment_impact(
        base,
        severity="low",
        repo_root=ROOT,
    )
    # Numerically neutral to within the 1-ULP pandas string-parse noise of
    # the string-dtype round trip (the gap added is exactly 0.0).
    np.testing.assert_allclose(
        pd.to_numeric(
            transformed.loc[
                transformed["stream"].astype(str).ne("LIGHT_RUC"),
                "unemployment_rate",
            ]
        ),
        pd.to_numeric(
            base.loc[
                base["stream"].astype(str).ne("LIGHT_RUC"), "unemployment_rate"
            ]
        ),
        rtol=1e-13,
        atol=0.0,
    )
    assert transformed["conflict_unemployment_gap_pp"].eq(0.0).all()


def test_combined_conflict_macro_layer_touches_gdp_and_unemployment_only() -> None:
    """The fuel_price_scenario macro layer chains GDP then unemployment.

    ``apply_conflict_gdp_impact`` keeps its tight GDP-only contract (asserted
    above); this test pins the union behaviour of the combined macro layer as
    wired in ``run_fuel_price_scenario_replay``.
    """

    base = _base_scenario_input_rows()
    combined = apply_conflict_unemployment_impact(
        apply_conflict_gdp_impact(base, severity="medium", repo_root=ROOT),
        severity="medium",
        repo_root=ROOT,
    )
    macro_fields = {
        "real_gdp_per_capita_nzd",
        "real_gdp_sa_nzd",
        "unemployment_rate",
    }
    untouched = [column for column in base.columns if column not in macro_fields]
    pd.testing.assert_frame_equal(
        combined[untouched],
        base[untouched],
        check_exact=True,
        check_dtype=True,
    )
    period = combined["canonical_period"].astype(str)
    anchor = combined["stream"].astype(str).eq("PED") & period.eq("2027Q1")
    base_anchor = base["stream"].astype(str).eq("PED") & base[
        "canonical_period"
    ].astype(str).eq("2027Q1")
    gdp_before = float(
        pd.to_numeric(base.loc[base_anchor, "real_gdp_per_capita_nzd"]).iloc[0]
    )
    gdp_after = float(
        pd.to_numeric(combined.loc[anchor, "real_gdp_per_capita_nzd"]).iloc[0]
    )
    assert gdp_after / gdp_before == pytest.approx(0.985, abs=1e-12)
    unemp_before = float(
        pd.to_numeric(base.loc[base_anchor, "unemployment_rate"]).iloc[0]
    )
    unemp_after = float(
        pd.to_numeric(combined.loc[anchor, "unemployment_rate"]).iloc[0]
    )
    assert unemp_after - unemp_before == pytest.approx(0.008, abs=1e-15)


def test_conflict_unemployment_audit_has_stable_column_order() -> None:
    base = _base_scenario_input_rows()
    transformed = apply_conflict_unemployment_impact(
        base,
        severity="medium",
        repo_root=ROOT,
    )
    audit = conflict_unemployment_input_audit(transformed)
    assert list(audit.columns) == [
        "scenario_name",
        "stream",
        "period",
        "conflict_unemployment_gap_pp",
        "conflict_unemployment_source_url",
        "conflict_unemployment_basis",
    ]
    assert len(audit) == len(transformed)
    assert conflict_unemployment_input_audit(base).empty
