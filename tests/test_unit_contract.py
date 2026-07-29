"""No production path may infer a unit from a value's magnitude.

The retired behaviour divided by a million whenever a number "looked like" raw
kilometres. That is correct only while every series stays inside its expected
range; a re-based or genuinely large series silently loses six orders of
magnitude with no error. These gates keep the inference from coming back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from model_dashboard.unit_contract import (
    DIMENSION_BY_UNIT,
    SERIES_CANONICAL_UNITS,
    SOURCE_UNIT_ALIASES,
    UnitContractError,
    canonical_unit_for,
    convert_declared,
    display_scale_for,
    unit_registry_frames,
)

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = sorted((ROOT / "model_dashboard").glob("*.py")) + [ROOT / "app.py"]
# The magnitude idiom: a bare numeric threshold big enough to be a scale test.
MAGNITUDE_INFERENCE = re.compile(r"abs\([^)]*\)\s*>\s*[0-9_]{7,}")


def test_no_production_magnitude_inference_remains() -> None:
    offenders = []
    for path in PRODUCTION_FILES:
        if path.name == "unit_contract.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if MAGNITUDE_INFERENCE.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}")
    assert not offenders, "magnitude-based unit inference reintroduced:\n" + "\n".join(offenders)


def test_no_production_substring_unit_scaling_remains() -> None:
    """Scale must come from the registry, not from 'million' in a label."""
    offenders = []
    for path in PRODUCTION_FILES:
        if path.name == "unit_contract.py":
            continue
        source = path.read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "display_scale_for" in stripped:
                continue
            if re.search(r"[\"']million[\"']\s+in\s+\w+", stripped) and "return 1_000_000" in source:
                # Only flag when the substring test drives a scale decision.
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {stripped}")
    assert not offenders, "substring-driven unit scaling reintroduced:\n" + "\n".join(offenders)


def test_no_production_file_mixes_line_endings() -> None:
    """`.gitattributes` pins `* -text`, so committed bytes are the diff.

    A patch script that rewrites a whole file with the other convention
    produces a diff of thousands of lines for a change of fourteen, which
    hides the real edit from review. A whole-file conversion is internally
    consistent and only diff inspection catches it; a partial rewrite leaves
    mixed endings, and this gate catches that.
    """
    offenders = []
    for path in PRODUCTION_FILES:
        raw = path.read_bytes()
        crlf = raw.count(b"\r\n")
        lf_only = raw.count(b"\n") - crlf
        if crlf and lf_only:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {crlf} CRLF, {lf_only} bare LF")
    assert not offenders, "mixed line endings (partial rewrite):\n" + "\n".join(offenders)


def test_every_decision_facing_series_declares_a_canonical_unit() -> None:
    assert len(SERIES_CANONICAL_UNITS) >= 40
    for series, canonical in SERIES_CANONICAL_UNITS.items():
        assert canonical in DIMENSION_BY_UNIT, series


def test_every_registry_alias_resolves_and_is_dimensioned() -> None:
    for alias, canonical in SOURCE_UNIT_ALIASES.items():
        assert canonical_unit_for(alias) == canonical
        assert canonical in DIMENSION_BY_UNIT


def test_every_declared_unit_in_the_committed_packs_is_registered() -> None:
    """100% unit coverage: no production row carries an unknown declaration."""
    import pandas as pd

    unknown: set[str] = set()
    for pack in ("data/current_revenue_outlook", "data/engine_ar1/current_revenue_outlook"):
        for name in ("revenue_chart_rows.csv", "revenue_line_reconciliation.csv"):
            path = ROOT / pack / name
            if not path.exists():
                continue
            frame = pd.read_csv(path, low_memory=False)
            for column in ("value_unit", "unit"):
                if column not in frame.columns:
                    continue
                for declared in frame[column].dropna().astype(str).unique():
                    if not declared.strip():
                        continue
                    try:
                        canonical_unit_for(declared)
                    except UnitContractError:
                        unknown.add(declared)
    assert not unknown, f"unregistered declared units in committed packs: {sorted(unknown)}"


def test_missing_and_unknown_declarations_fail_closed() -> None:
    for bad in ("", None, "   "):
        with pytest.raises(UnitContractError, match="no declared unit"):
            canonical_unit_for(bad)
    with pytest.raises(UnitContractError, match="not in the canonical registry"):
        canonical_unit_for("furlongs")
    with pytest.raises(UnitContractError):
        display_scale_for("furlongs")


def test_dimensionally_incompatible_conversion_is_refused() -> None:
    with pytest.raises(UnitContractError, match="Dimensionally incompatible"):
        convert_declared(1.0, "net km", "million_nzd")
    with pytest.raises(UnitContractError, match="Dimensionally incompatible"):
        convert_declared(1.0, "persons", "million_km")


def test_conversion_preserves_the_governed_operation_order() -> None:
    """x / 1e6 and x * 1e-6 differ in the last ulp; the packs divide."""
    value = 3_052_255_123.456789
    result = convert_declared(value, "net km", "million_km")
    assert result.operation == "/"
    assert result.operand == 1_000_000.0
    assert result.converted == value / 1_000_000.0
    assert result.conversion_factor == pytest.approx(1e-6)


def test_identity_and_round_trip() -> None:
    assert convert_declared(5.0, "million km", "million_km").converted == 5.0
    there = convert_declared(2_000_000.0, "net km", "million_km").converted
    back = convert_declared(there, "million km", "km").converted
    assert back == pytest.approx(2_000_000.0, abs=1e-6)


def test_display_scale_resolves_by_declaration() -> None:
    assert display_scale_for("million km") == 1_000_000.0
    assert display_scale_for("$m nominal ex GST") == 1_000_000.0
    assert display_scale_for("million people") == 1_000_000.0
    assert display_scale_for("net km") == 1.0
    assert display_scale_for("km/person") == 1.0


def test_registry_frames_are_complete_and_dimensioned() -> None:
    series, aliases, conversions = unit_registry_frames()
    assert len(series) == len(SERIES_CANONICAL_UNITS)
    assert len(aliases) == len(SOURCE_UNIT_ALIASES)
    assert conversions["operation"].isin(["/", "*"]).all()
    assert conversions["lossless"].all()
    for frame in (series, aliases, conversions):
        assert frame["dimension"].notna().all()
