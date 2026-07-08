"""Performance-cache architecture: staged caches must not change results.

The view pipeline (bridge -> sensitivity -> lever overlays -> filter/cone)
is cached at three grains: the sensitivity stage, the series-agnostic
scenario overlay rows, and the full view. These tests pin the equivalences
that make those caches safe and the warmer targets that keep first-touch
interactions warm.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

ROOT = Path(__file__).resolve().parents[1]
FED = "Current planned path"
TRACES = ("Current finalist Base case", "Actual")


@pytest.fixture(scope="module")
def context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


def _default_keys():
    sens = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    uptake = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0)
    return sens, uptake


def test_view_returns_fresh_copies_across_calls(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    first = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    # Poison the returned frame; a second retrieval must be unaffected.
    first["filtered_rows"].loc[:, "value"] = -1.0
    second = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    assert not second["filtered_rows"]["value"].eq(-1.0).all()
    assert (pd.to_numeric(second["filtered_rows"]["value"], errors="coerce") > 0).any()


def test_overlay_rows_match_view_chart_rows(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    view = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    rows, _, _, _ = app.cached_scenario_overlay_rows(signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack)
    pd.testing.assert_frame_equal(view["chart_rows"].reset_index(drop=True), rows.reset_index(drop=True))


def test_cone_band_is_uptake_key_invariant(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    bands = {}
    for mode in ("MoT VFM base", "MoT VFM fast"):
        view = app.cached_revenue_outlook_view(
            signature, "Total NLTF revenue", "june_year", FED, TRACES, sens,
            PED_BRIDGE_DEFAULT_MODE, (mode, (), (), 0), pack,
        )
        bands[mode] = view["cone_band"]
    pd.testing.assert_frame_equal(
        bands["MoT VFM base"].reset_index(drop=True),
        bands["MoT VFM fast"].reset_index(drop=True),
    )
    assert not bands["MoT VFM base"].empty


def test_warm_targets_cover_single_family_sensitivities() -> None:
    keys = app._revenue_outlook_warm_sensitivity_keys()
    assert len(keys) == 9
    assert all(len(key) == 11 for key in keys)
    assert app.selected_sensitivity_key("Med", "Off", "Off", freight_rail_shift="Off") in keys
    assert app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="High") in keys


def test_warmer_respects_disable_flag(monkeypatch) -> None:
    monkeypatch.setenv("REVENUE_OUTLOOK_CACHE_WARMER", "0")
    app._REVENUE_OUTLOOK_WARMER_STARTED.clear()
    app._start_revenue_outlook_cache_warmer()
    assert not app._REVENUE_OUTLOOK_WARMER_STARTED.is_set()
