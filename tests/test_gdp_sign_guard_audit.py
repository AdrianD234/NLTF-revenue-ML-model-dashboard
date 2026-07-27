"""Acceptance rules for the GDP sign-guard register.

The guards are a governance overlay on a fitted model, so the question is not
whether they exist but whether they are precautionary or load-bearing, and
whether every binding has an explicit disposition rather than sitting in an
indefinite review state.

These tests read the committed register, which CI regenerates from the replay
before running them, so a change in guard behaviour fails here rather than
being discovered later.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "artifacts" / "gdp_sign_guard_audit"
BINDINGS = AUDIT_DIR / "gdp_sign_guard_bindings.csv"
ACCEPTANCE = AUDIT_DIR / "gdp_sign_guard_acceptance.csv"


def _load(path: Path) -> pd.DataFrame:
    if not path.exists():
        pytest.skip(
            f"{path.name} missing; run scripts/audit_gdp_sign_guard_bindings.py"
        )
    return pd.read_csv(path)


def test_base_has_no_sign_guard_bindings():
    """Base is the reference the overlay is built from; clipping it is a defect."""

    bindings = _load(BINDINGS)
    assert bindings[bindings["severity"].astype(str).eq("base")].empty


def test_every_binding_has_an_explicit_disposition():
    """No binding may sit in an indefinite review state."""

    bindings = _load(BINDINGS)
    dispositions = set(bindings["disposition"].astype(str))
    assert dispositions.issubset(
        {"accepted_definitional_restoration", "accepted_expected_guard"}
    ), dispositions
    assert not bindings["disposition"].astype(str).eq("unresolved").any()


def test_economic_monotonicity_holds_for_every_binding():
    """A downside scenario must never end up above Base at the same price."""

    bindings = _load(BINDINGS)
    assert bindings["monotonicity_holds"].astype(bool).all()


def test_downside_guards_only_ever_clip_downward():
    """A wrong-sign correction that raised the forecast would be incoherent."""

    bindings = _load(BINDINGS)
    downside = bindings[bindings["downside_guard"].astype(bool)]
    if downside.empty:
        pytest.skip("no downside guards bound")
    assert downside["clip_amount"].astype(float).le(1e-15).all()
    assert downside["guarded_gdp_model_factor"].astype(float).le(1.0 + 1e-12).all()
    assert downside["raw_gdp_model_factor"].astype(float).gt(1.0).all()


def test_identity_guards_restore_exactly_one():
    bindings = _load(BINDINGS)
    identity = bindings[bindings["identity_guard"].astype(bool)]
    if identity.empty:
        pytest.skip("no identity guards bound")
    assert identity["guarded_gdp_model_factor"].astype(float).sub(1.0).abs().le(
        1e-12
    ).all()
    # An identity restoration only makes sense where the input GDP was unchanged.
    assert identity["input_gdp_level_factor"].astype(float).sub(1.0).abs().le(
        1e-12
    ).all()


def test_low_wrong_sign_bindings_are_accepted_and_bounded():
    """The six Low bindings that required an explicit verdict."""

    bindings = _load(BINDINGS)
    low_downside = bindings[
        bindings["severity"].astype(str).eq("low")
        & bindings["downside_guard"].astype(bool)
    ]
    if low_downside.empty:
        pytest.skip("no Low downside guards bound")
    assert (
        low_downside["disposition"].astype(str).eq("accepted_expected_guard").all()
    )
    assert low_downside["monotonicity_holds"].astype(bool).all()
    # They sit inside the Low path's own stress window, which converges at 2027Q1.
    assert set(low_downside["quarter"].astype(str)).issubset({"2026Q4", "2027Q1"})
    # And they are small: a Low conflict should not be materially guard-driven.
    assert low_downside["forecast_delta_pct"].abs().max() < 0.5


def test_guards_are_precautionary_not_load_bearing():
    """Disclosure requires knowing the scale, not just the count."""

    bindings = _load(BINDINGS)
    assert bindings["forecast_delta_pct"].abs().max() < 1.0, (
        "a guard moving the forecast by more than 1% is load-bearing and needs "
        "re-estimation rather than clipping"
    )


def test_acceptance_table_records_a_status_for_every_severity():
    acceptance = _load(ACCEPTANCE)
    assert set(acceptance["severity"].astype(str)) == {
        "base",
        "low",
        "medium",
        "high",
    }
    assert not acceptance["status"].astype(str).eq("failed").any()
    assert not acceptance["status"].astype(str).eq("review_required").any()
