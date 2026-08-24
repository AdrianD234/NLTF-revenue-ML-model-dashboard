"""Analyst preview control, selector independence and governed wording.

Sections 13-14 and gates 26-28. The point of these gates is that a reader of
the chart cannot be misled about what the long-run layer is: the empirical
bands still stop at FY2030, the long-run envelope is labelled non-probabilistic,
and no wording claims Current was calibrated to an official forecast.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

import app as dashboard
from model_dashboard.long_run_shape_transition import (
    PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID,
    STRUCTURAL_SCHEDULE_IDS,
    UNBLENDED_SCHEDULE_ID,
)
from model_dashboard.post_model_extrapolation import ANCHOR_FY

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "current_revenue_outlook"

# Wording that would misstate the method to a reader.
BANNED_PHRASES = (
    "calibrated to befu",
    "calibrated to mot",
    "forced to mot",
    "forced to befu",
    "blended to match official",
    "blended to match befu",
    "matched to official revenue",
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))


class TestPreviewOptions:
    def test_every_governed_candidate_is_offered(self, manifest):
        options = dashboard._long_run_shape_preview_options(manifest)
        schedules = {spec["schedule_id"] for spec in options.values()}
        assert UNBLENDED_SCHEDULE_ID in schedules
        for schedule_id in STRUCTURAL_SCHEDULE_IDS:
            assert schedule_id in schedules, schedule_id

    def test_a_prior_vintage_audit_option_exists(self, manifest):
        options = dashboard._long_run_shape_preview_options(manifest)
        audit = [spec for spec in options.values() if spec["role"] == "audit"]
        assert audit, "the prior-vintage audit preview is missing"
        # Every shape-capable vintage other than the pack's own shape source
        # (PREBU26 since the handover promotion) is offered for audit -
        # BEFU26 and MBU26.
        assert {spec["shape_vintage_id"] for spec in audit} == {"MBU26", "BEFU26"}

    def test_exactly_one_option_is_the_pack_default(self, manifest):
        options = dashboard._long_run_shape_preview_options(manifest)
        defaults = [spec for spec in options.values() if spec["is_pack_default"]]
        assert len(defaults) == 1

    def test_gate_28_public_default_is_the_packs_own_schedule(self, manifest):
        """The preview cannot move the published default.

        The default is now the promoted production schedule rather than the
        unblended control. What the gate protects is unchanged: the preview
        must reflect whatever the PACK recorded, never override it.
        """

        options = dashboard._long_run_shape_preview_options(manifest)
        default = next(spec for spec in options.values() if spec["is_pack_default"])
        block = manifest.get("official_vintages") or {}
        expected = str(
            block.get("long_run_transition_schedule_id") or UNBLENDED_SCHEDULE_ID
        )
        assert default["schedule_id"] == expected
        assert expected == PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID

    def test_options_are_registry_driven_not_hard_coded(self):
        """Gate 29 at the UI layer: no vintage literal in the option builder."""

        source = (ROOT / "app.py").read_text(encoding="utf-8")
        start = source.index("def _long_run_shape_preview_options")
        end = source.index("def _render_long_run_shape_controls")
        body = source[start:end]
        assert "BEFU26" not in body
        assert "MBU26" not in body


class TestSelectorIndependence:
    """Gate 28: each control changes only its own layer."""

    def test_shape_control_uses_its_own_session_key(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert 'revenue_outlook_long_run_shape_method' in source
        # ...and it is not the comparator's key.
        assert (
            dashboard._LONG_RUN_SHAPE_PREVIEW_KEY
            != "revenue_outlook_official_vintage"
        )

    def test_changing_the_comparator_does_not_change_the_shape_options(self, manifest):
        """The option set depends on the pack's shape role, not the comparator."""

        before = dashboard._long_run_shape_preview_options(manifest)
        swapped = json.loads(json.dumps(manifest))
        swapped["official_vintages"]["official_comparator_vintage_id"] = "MBU26"
        after = dashboard._long_run_shape_preview_options(swapped)
        assert set(before) == set(after)
        assert [spec["schedule_id"] for spec in before.values()] == [
            spec["schedule_id"] for spec in after.values()
        ]

    def test_changing_the_bridge_does_not_change_the_shape_options(self, manifest):
        swapped = json.loads(json.dumps(manifest))
        swapped["official_vintages"]["bridge_assumption_vintage_id"] = "MBU26"
        assert set(dashboard._long_run_shape_preview_options(swapped)) == set(
            dashboard._long_run_shape_preview_options(manifest)
        )


class TestGovernedWording:
    def test_details_text_carries_the_four_required_lines(self, manifest):
        """Worded from the production default: the FY2035 growth handover on
        the PREBU26 shape source."""

        state = {
            "schedule_id": PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID,
            "shape_vintage_id": "PREBU26",
            "anchor_fy": ANCHOR_FY,
            "completion_fy": 2035,
        }
        text = dashboard._long_run_shape_details_text(state, "Base_EV")
        assert f"Current FY{ANCHOR_FY} level anchor" in text
        assert "Long-run activity shape: PREBU26" in text
        assert "Fleet composition: VFM202405 Base_EV" in text
        assert (
            f"Transition schedule: {PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID}"
            in text
        )

    def test_details_text_names_a_level_blend_candidate_when_selected(self, manifest):
        """The level blends stay governed candidates with truthful wording."""

        state = {
            "schedule_id": "balanced_structural",
            "shape_vintage_id": "BEFU26",
            "anchor_fy": ANCHOR_FY,
            "completion_fy": 2045,
        }
        text = dashboard._long_run_shape_details_text(state, "Base_EV")
        assert "Long-run activity shape: BEFU26" in text
        assert "Transition schedule: balanced_structural" in text

    def test_unblended_details_do_not_name_a_structural_source(self):
        state = {
            "schedule_id": UNBLENDED_SCHEDULE_ID,
            "shape_vintage_id": "BEFU26",
            "anchor_fy": ANCHOR_FY,
            "completion_fy": None,
        }
        text = dashboard._long_run_shape_details_text(state, "Base_EV")
        assert "no structural transition" in text.lower()

    @pytest.mark.parametrize("phrase", BANNED_PHRASES)
    def test_banned_wording_is_absent_from_the_app(self, phrase):
        source = (ROOT / "app.py").read_text(encoding="utf-8").lower()
        assert phrase not in source, phrase

    def test_banned_wording_is_absent_from_the_method_modules(self):
        for relative in (
            "model_dashboard/long_run_shape_transition.py",
            "model_dashboard/post_model_extrapolation.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8").lower()
            for phrase in BANNED_PHRASES:
                assert phrase not in source, (relative, phrase)

    def test_the_help_text_states_the_anchor_and_the_non_substitution(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        start = source.index("def _render_long_run_shape_controls")
        end = source.index("def _long_run_shape_details_text")
        body = source[start:end]
        # Adjacent string literals split phrases across source lines; join them
        # so the assertion is about the RENDERED help text rather than about
        # where the author happened to wrap a line.
        rendered = re.sub(r'"\s+"', "", body).lower()
        assert "level anchor" in rendered
        assert "official level is not substituted" in rendered


class TestUncertaintyTreatment:
    """Gates 26-27."""

    def test_gate_26_empirical_bands_stop_at_fy2030(self):
        path = PACK_DIR / "fan_band_rows.parquet"
        if not path.exists():
            pytest.skip("no fan band rows in this pack")
        bands = pd.read_parquet(path)
        year_column = next(
            (c for c in ("june_year", "FY", "fy") if c in bands.columns), None
        )
        assert year_column is not None
        # Only the EMPIRICAL sources must stop at the anchor. The scenario
        # spread deliberately continues past it as the separately named and
        # separately labelled long-run envelope - that seam split is the whole
        # point, so asserting on every row would forbid the intended design.
        empirical = bands[
            bands["fan_segment"].astype(str).eq("empirical_supported")
        ]
        assert not empirical.empty
        years = pd.to_numeric(empirical[year_column], errors="coerce").dropna()
        assert float(years.max()) <= ANCHOR_FY

        envelope = bands[
            bands["fan_segment"].astype(str).eq("long_run_scenario_envelope")
        ]
        assert not envelope.empty
        assert (
            float(pd.to_numeric(envelope[year_column], errors="coerce").max())
            > ANCHOR_FY
        )
        # No empirical source may leak into the long-run envelope.
        assert set(envelope["fan_source"].astype(str)) == {"Scenario spread"}

    def test_gate_27_long_run_envelope_is_labelled_non_probabilistic(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert "Long-run structural scenario envelope" in source
        # The label must carry the disclaimer in the same string.
        match = re.search(
            r"Long-run structural scenario envelope[^\"']*", source
        )
        assert match is not None
        assert "not probabilistic" in match.group(0).lower()

    def test_the_envelope_is_never_called_a_confidence_interval(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        window = source[
            max(0, source.find("Long-run structural scenario envelope") - 2000) :
            source.find("Long-run structural scenario envelope") + 2000
        ]
        lowered = window.lower()
        for banned in ("confidence interval", "prediction interval", "error band"):
            assert banned not in lowered, banned
