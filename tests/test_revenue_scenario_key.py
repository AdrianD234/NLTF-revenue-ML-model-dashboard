"""The typed scenario key: one meaning per control, and no positional slots.

The defect this replaces: ``ev_uptake_key`` slot 6 was read as the official
comparator vintage id by one helper and as a Heavy-BEV transition flag by
another.  Production always wrote a non-empty vintage id there, so
``bool("BEFU26")`` switched Heavy-BEV reclassification ON in every real render,
against the settled ``HEAVY_RUC: not_reclassified`` contract.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import app
from model_dashboard.official_vintage import official_vintage_choices
from model_dashboard.revenue_scenario_key import (
    HEAVY_BEV_DEFAULT,
    RevenueScenarioComputationKey,
    as_scenario_key,
)

ROOT = Path(__file__).resolve().parents[1]


def production_shaped_key(vintage: str = "BEFU26") -> RevenueScenarioComputationKey:
    """The key shape `render_revenue_outlook_page` actually builds."""
    return RevenueScenarioComputationKey(
        engine="ar1",
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        ped_retention_sensitivity=False,
        heavy_bev_transition=HEAVY_BEV_DEFAULT,
        official_comparator_vintage_id=vintage,
        official_comparator_overlay=False,
        ped_bridge_mode="raw_model",
        bridge_vintage_id="BEFU26",
        long_run_transition_schedule_id="balanced_structural",
        long_run_shape_vintage_id="BEFU26",
    )


# ------------------------------------------------- 1. the collision is closed
@pytest.mark.parametrize("vintage", [vid for vid, _label in official_vintage_choices(ROOT)] or ["BEFU26"])
def test_no_official_vintage_can_activate_heavy_bev(vintage) -> None:
    key = production_shaped_key(vintage)
    assert key.official_comparator_vintage_id == vintage
    assert key.heavy_bev_transition is False
    assert app._heavy_bev_transition_enabled(key) is False
    assert app._official_vintage_scope(key)[0] == vintage


def test_heavy_bev_defaults_off_on_a_bare_key() -> None:
    assert HEAVY_BEV_DEFAULT is False
    assert RevenueScenarioComputationKey().heavy_bev_transition is False
    assert app._heavy_bev_transition_enabled(RevenueScenarioComputationKey()) is False


def test_heavy_bev_is_only_on_when_explicitly_asked_for() -> None:
    key = production_shaped_key().replace(heavy_bev_transition=True)
    assert app._heavy_bev_transition_enabled(key) is True
    # And turning it on must not disturb the comparator selection.
    assert app._official_vintage_scope(key)[0] == "BEFU26"


def test_the_production_key_shape_resolves_heavy_bev_off() -> None:
    """The regression the old tests missed: they never built this shape."""
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "RevenueScenarioComputationKey(" in source
    assert "heavy_bev_transition=HEAVY_BEV_DEFAULT" in source
    assert "official_comparator_vintage_id=" in source


# --------------------------------------------- 2. one meaning per field
def test_every_field_has_exactly_one_meaning() -> None:
    """A vintage id is a str; a flag is a bool. Neither can be read as the other."""
    key = production_shaped_key()
    assert isinstance(key.official_comparator_vintage_id, str)
    assert isinstance(key.heavy_bev_transition, bool)
    assert isinstance(key.ped_retention_sensitivity, bool)
    assert isinstance(key.official_comparator_overlay, bool)
    # A truthy vintage id cannot be mistaken for any flag.
    flags = {
        name
        for name, value in key.canonical_mapping().items()
        if isinstance(value, bool)
    }
    assert not any(value for name, value in key.canonical_mapping().items() if name in flags), (
        "no flag is on in the production default"
    )


def test_no_production_helper_addresses_controls_by_tuple_position() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")
    offenders = re.findall(r"ev_uptake_key\[\s*\d+\s*\]", source)
    assert not offenders, offenders
    assert "len(ev_uptake_key)" not in source


# --------------------------------------------- 3. deterministic serialization
def test_serialization_and_digest_are_deterministic() -> None:
    a = production_shaped_key()
    b = production_shaped_key()
    assert a == b and hash(a) == hash(b)
    assert a.serialize() == b.serialize()
    assert a.digest() == b.digest()
    assert len(a.digest()) == 64
    assert a.cache_token() == a.digest()[:16]
    # Field ORDER in the constructor must not change the identity.
    reordered = RevenueScenarioComputationKey(
        official_comparator_vintage_id="BEFU26",
        engine="ar1",
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        long_run_shape_vintage_id="BEFU26",
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        ped_bridge_mode="raw_model",
        bridge_vintage_id="BEFU26",
        long_run_transition_schedule_id="balanced_structural",
    )
    assert reordered.digest() == a.digest()


def test_equivalent_values_normalise_to_one_identity() -> None:
    listy = RevenueScenarioComputationKey(eruc_levers=[2027, 3, 1.0, -0.15, 2.7])
    tuply = RevenueScenarioComputationKey(eruc_levers=(2027.0, 3.0, 1.0, -0.15, 2.7))
    assert listy == tuply and listy.digest() == tuply.digest()


def test_no_dataframe_or_pack_can_enter_the_key() -> None:
    import dataclasses

    allowed = {"str", "bool", "tuple[float, ...]"}
    for field in dataclasses.fields(RevenueScenarioComputationKey):
        assert str(field.type) in allowed, (field.name, field.type)


# ----------------------------------- 4. one field changes one calculation
def test_changing_one_field_changes_only_its_own_resolution() -> None:
    base = production_shaped_key()
    checks = {
        "heavy_bev_transition": (True, app._heavy_bev_transition_enabled),
        "ped_retention_sensitivity": (True, app._ped_retention_enabled),
        "official_comparator_overlay": (True, lambda key: app._official_vintage_scope(key)[1]),
    }
    for field, (value, resolver) in checks.items():
        changed = base.replace(**{field: value})
        assert resolver(base) != resolver(changed), field
        # Every OTHER resolver is untouched.
        for other, (_value, other_resolver) in checks.items():
            if other == field:
                continue
            assert other_resolver(base) == other_resolver(changed), (field, other)
        assert app._official_vintage_scope(changed)[0] == app._official_vintage_scope(base)[0]
        assert app._long_run_shape_scope(changed) == app._long_run_shape_scope(base)


def test_named_fields_reach_every_scope_helper() -> None:
    key = production_shaped_key().replace(
        long_run_transition_schedule_id="balanced_structural",
        long_run_shape_vintage_id="BEFU26",
        current_fed_policy_state=app.FED_POLICY_OFF,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
    )
    assert app._long_run_shape_scope(key) == ("balanced_structural", "BEFU26")
    assert app._fed_policy_state_scope(key) == (app.FED_POLICY_OFF, app.FED_POLICY_PUBLISHED)
    assert app._resolve_uptake_basis(key) == app.DEFAULT_EV_UPTAKE_MODE


# ------------------------------------------------ 5. the legacy adapter
def test_the_adapter_tells_slot_six_apart_by_type() -> None:
    """A str there is a vintage id; a bool there is the old test key's flag."""
    production = (
        app.DEFAULT_EV_UPTAKE_MODE, (), (), "published", "published",
        False, "BEFU26", False, "balanced_structural", "BEFU26",
    )
    adapted = as_scenario_key(production)
    assert adapted.official_comparator_vintage_id == "BEFU26"
    assert adapted.heavy_bev_transition is False, (
        "the collision must not survive the adapter"
    )

    legacy_test_shape = (app.DEFAULT_EV_UPTAKE_MODE, (), (), "published", "published", False, True)
    adapted_legacy = as_scenario_key(legacy_test_shape)
    assert adapted_legacy.heavy_bev_transition is True
    assert adapted_legacy.official_comparator_vintage_id == ""


def test_a_short_legacy_key_resolves_to_the_documented_defaults() -> None:
    adapted = as_scenario_key((app.DEFAULT_EV_UPTAKE_MODE, (), ()))
    assert adapted.heavy_bev_transition is False
    assert adapted.ped_retention_sensitivity is False
    assert adapted.official_comparator_overlay is False
    assert app._long_run_shape_scope(adapted)[0] == app.UNBLENDED_SCHEDULE_ID


def test_the_legacy_tuple_round_trips_for_unmigrated_callers() -> None:
    production = (
        app.DEFAULT_EV_UPTAKE_MODE, (), (), "published", "published",
        False, "BEFU26", False, "balanced_structural", "BEFU26",
    )
    assert as_scenario_key(production).to_legacy_uptake_tuple() == production


def test_the_typed_key_is_streamlit_cacheable() -> None:
    """It has to be hashable by st.cache_data, not just by Python."""
    import streamlit as st

    @st.cache_data(show_spinner=False)
    def _echo(key: RevenueScenarioComputationKey) -> str:
        return key.digest()

    key = production_shaped_key()
    assert _echo(key) == key.digest()
