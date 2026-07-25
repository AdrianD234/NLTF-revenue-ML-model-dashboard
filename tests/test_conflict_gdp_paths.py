from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.conflict_gdp_paths import (
    apply_conflict_gdp_impact,
    build_conflict_gdp_paths,
    load_conflict_gdp_calibration,
    validate_conflict_gdp_paths,
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
