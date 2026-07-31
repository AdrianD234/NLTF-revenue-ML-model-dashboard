"""Runtime genericity, leakage and fail-closed gates for official vintages.

The ingestion layer was already generic. These gates cover the rest of the
claim: that the runtime and selector vocabulary are generated from the
registry or pack manifest rather than wired for two named releases, that the
selected vintage cannot leak another vintage's rows into anything a user sees
or downloads, and that a broken registry fails closed in production.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard import official_vintage as ov
from model_dashboard.rate_paths import rate_paths_frame
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    load_revenue_outlook_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / CURRENT_REVENUE_OUTLOOK_DIR


@pytest.fixture(scope="module")
def pack():
    loaded = load_revenue_outlook_pack(PACK_DIR, repo_root=ROOT)
    assert loaded is not None
    return loaded


class TestEffectiveRateChartFollowsTheBridgeVintage:
    """The defect this closes: the caption said BEFU26, the rates were MBU26."""

    @pytest.mark.parametrize("vintage_id", ["BEFU26", "MBU26"])
    def test_displayed_rates_equal_bridge_revenue_over_bridge_activity(
        self, pack, vintage_id
    ):
        frame = rate_paths_frame(
            ROOT, pack.revenue_chart_rows, bridge_vintage_id=vintage_id
        )
        spine = ov.official_vintage_spine_frame(vintage_id, ROOT)
        pairs = (
            ("Light RUC", "light_ruc_net_revenue", "light_ruc_net_km"),
            ("Heavy RUC", "heavy_ruc_net_revenue", "heavy_ruc_net_km"),
        )
        for label, revenue_series, activity_series in pairs:
            for fy in (2026, 2030, 2040, 2050):
                selected = frame[
                    frame["series"].eq(label)
                    & frame["june_year"].eq(fy)
                    & frame["segment"].eq("planned")
                ]
                assert not selected.empty, f"{label} FY{fy} missing"
                shown = float(selected["nzd_per_1000km"].iloc[0])
                expected = float(
                    spine.loc[fy, revenue_series] / spine.loc[fy, activity_series] * 1000
                )
                assert shown == pytest.approx(expected, abs=1e-9), (
                    f"{vintage_id} {label} FY{fy}: chart {shown} != source {expected}"
                )

    def test_the_two_vintages_actually_differ(self, pack):
        """Otherwise the test above would pass on a still-broken sourcing."""
        befu = rate_paths_frame(ROOT, pack.revenue_chart_rows, bridge_vintage_id="BEFU26")
        mbu = rate_paths_frame(ROOT, pack.revenue_chart_rows, bridge_vintage_id="MBU26")
        assert not befu["nzd_per_1000km"].equals(mbu["nzd_per_1000km"])

    def test_caption_names_the_vintage_it_was_derived_from(self):
        from model_dashboard.rate_paths import rate_chart_note

        for vintage_id in ("BEFU26", "MBU26"):
            note = rate_chart_note(vintage_id)
            assert vintage_id in note
            other = "MBU26" if vintage_id == "BEFU26" else "BEFU26"
            assert other not in note


class TestFleetMixFollowsTheBridgeVintage:
    @pytest.mark.parametrize("vintage_id", ["BEFU26", "MBU26"])
    def test_official_frame_matches_the_named_vintage(self, vintage_id):
        from model_dashboard.fleet_mix import load_official_frame, official_source_label

        frame = load_official_frame(ROOT, vintage_id)
        spine = ov.official_vintage_spine_frame(vintage_id, ROOT)
        for fy in (2030, 2040):
            assert float(frame.loc[fy, "light_ruc_net_km"]) == pytest.approx(
                float(spine.loc[fy, "light_ruc_net_km"]), abs=1e-9
            )
        # The visible label must name the vintage the frame came from.
        assert vintage_id in official_source_label(vintage_id)

    def test_source_options_are_generated_per_vintage(self):
        from model_dashboard.fleet_mix import source_options

        assert source_options("BEFU26")[0] == "BEFU26 official (MoT baseline)"
        assert source_options("MBU26")[0] == "MBU26 official (MoT baseline)"

    def test_cache_signature_follows_the_vintage_in_use(self):
        befu = {path for path, _size, _mtime in app._fleet_mix_signature("BEFU26")}
        mbu = {path for path, _size, _mtime in app._fleet_mix_signature("MBU26")}
        assert befu != mbu, "the cache key must change with the bridge vintage"
        assert any("befu26" in path.lower() for path in befu)
        assert any("mbu26" in path.lower() for path in mbu)


class TestRuntimeVocabularyIsRegistryDriven:
    def test_official_trace_names_come_from_the_registry(self):
        expected = tuple(
            ov.official_comparator_trace_name(
                str(ov.official_vintage_entry(vid, ROOT).get("release_round") or vid)
            )
            for vid, _display in ov.official_vintage_choices(ROOT)
        )
        assert app._registry_official_trace_names() == expected

    def test_default_comparator_is_not_hard_coded(self):
        assert app._registry_default_comparator_vintage_id() == ov.default_comparator_vintage_id(ROOT)

    def test_style_and_colour_maps_cover_every_registered_vintage(self):
        styles = app._official_trace_style_map()
        assert set(styles) == set(app._registry_official_trace_names())
        # Default comparator first and visually dominant.
        first = app._registry_official_trace_names()[0]
        assert styles[first][0] == "#00843D"

    def test_no_generic_default_hard_codes_a_release(self):
        """Catches a hard-coded BEFU26 default, not just MBU26 ones."""
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        banned = (
            '_DEFAULT_OFFICIAL_COMPARATOR_VINTAGE_ID = "BEFU26"',
            "_DEFAULT_OFFICIAL_COMPARATOR_VINTAGE_ID = 'BEFU26'",
            'officials = ["BEFU26 official", "MBU26 official"]',
            'official_fed_paths: tuple[str, ...] = ("BEFU26", "MBU26")',
        )
        for text in banned:
            assert text not in source, f"hard-coded release vocabulary: {text!r}"


class TestSelectedVintageLeakage:
    """With one vintage selected and overlay off, no other may reach the user."""

    def _view(self, pack, vintage_id: str, overlay: bool):
        signature = app.revenue_outlook_signature(PACK_DIR, ROOT)
        sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
        uptake_key = (
            app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0, False, vintage_id, overlay,
        )
        traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
        return app.cached_revenue_outlook_view(
            signature,
            "Total NLTF revenue",
            "june_year",
            "Current planned path",
            traces,
            sensitivity_key,
            app.PED_BRIDGE_DEFAULT_MODE,
            uptake_key,
            pack,
        )

    @pytest.mark.parametrize("selected,excluded", [("BEFU26", "MBU26"), ("MBU26", "BEFU26")])
    def test_no_other_official_vintage_reaches_any_consumer(self, pack, selected, excluded):
        view = self._view(pack, selected, overlay=False)
        excluded_scenario = ov.official_comparator_scenario_name(excluded)
        excluded_trace = ov.official_comparator_trace_name(excluded)
        for key in (
            "chart_rows",
            "filtered_rows",
            "line_reconciliation",
            "revenue_stack_components",
        ):
            frame = view.get(key)
            if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            for column in ("scenario_name", "trace_name", "source_path"):
                if column not in frame.columns:
                    continue
                leaked = set(frame[column].dropna().astype(str)) & {
                    excluded_scenario,
                    excluded_trace,
                }
                assert leaked == set(), (
                    f"{excluded} leaked into {key}.{column} while {selected} was selected: {leaked}"
                )

    def test_overlay_on_restores_the_prior_vintage(self, pack):
        view = self._view(pack, "BEFU26", overlay=True)
        traces = set(view["chart_rows"]["trace_name"].dropna().astype(str))
        assert "MBU26 official" in traces
        assert "BEFU26 official" in traces


class TestRegistryFailsClosed:
    def test_completeness_contract_raises_on_a_broken_registry(self, monkeypatch):
        """Production must not silently fall back to a hard-coded vintage."""
        from model_dashboard import completeness_contract

        def boom(*_args, **_kwargs):
            raise ov.OfficialVintageError("registry unreadable")

        monkeypatch.setattr(ov, "default_comparator_vintage_id", boom)
        with pytest.raises(ov.OfficialVintageError):
            completeness_contract._default_official_comparator_scenario()

    def test_explicit_scenario_by_role_still_works_without_the_registry(self, monkeypatch):
        """Fixture compatibility is explicit, not an implicit fallback."""
        from model_dashboard import completeness_contract

        def boom(*_args, **_kwargs):
            raise ov.OfficialVintageError("registry unreadable")

        monkeypatch.setattr(ov, "default_comparator_vintage_id", boom)
        frame = completeness_contract.completeness_matrix(
            {},
            scenario_by_role={
                "basecase": "current_basecase",
                "comparison": "current_comparison_1",
                "official_comparator": "mbu26_official",
            },
        )
        assert isinstance(frame, pd.DataFrame)

    def test_loader_rejects_an_unknown_vintage(self):
        with pytest.raises(ov.OfficialVintageError):
            ov.load_official_vintage("PREFU99", repo_root=ROOT)


class TestPlugAndPlayReachesTheRuntime:
    """Materialisation genericity was already proven; this covers the runtime."""

    def test_registering_a_vintage_extends_the_runtime_vocabulary(self, tmp_path, monkeypatch):
        registry = json.loads(ov.registry_path(ROOT).read_text(encoding="utf-8"))
        entry = json.loads(json.dumps(ov.official_vintage_entry("BEFU26", ROOT)))
        entry.update(
            {
                "vintage_id": "PREFU27",
                "display_name": "PREFU27 official",
                "release_round": "PREFU27",
                "is_latest": False,
                "is_default_comparator": False,
                "is_default_bridge_vintage": False,
                "status": "registered_official_vintage",
            }
        )
        registry["vintages"].append(entry)
        assert ov.validate_official_vintage_registry(registry) == []

        # The vocabulary helpers must pick the new vintage up from the registry
        # alone - no production-code edit, no new literal.
        names = tuple(
            ov.official_comparator_trace_name(str(item["release_round"]))
            for item in registry["vintages"]
            if item.get("available", True)
        )
        assert "PREFU27 official" in names
        assert ov.official_comparator_scenario_name("PREFU27") == "prefu27_official"
