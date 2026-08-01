"""The runtime manifest must not contradict the pack it describes.

The manifest is the authoritative explanation of how the committed rows were
built, so stale governance prose is a real defect even when every number is
correct. These gates are static: they read the committed manifests and fail if
the wording asserts something the same manifest, or the pack beside it,
contradicts.

Each check is written against what the manifest ACTUALLY records rather than
against a hard-coded vintage or schedule, so promoting a different vintage or
schedule cannot make the test wrong - only a manifest that lies about itself
can fail it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.long_run_shape_transition import UNBLENDED_SCHEDULE_ID
from model_dashboard.post_model_extrapolation import (
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    POST_MODEL_SEGMENT,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIRS = {
    "ensemble": ROOT / "data" / "current_revenue_outlook",
    "ar1": ROOT / "data" / "engine_ar1" / "current_revenue_outlook",
}


def _manifest(pack_dir: Path) -> dict:
    return json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))


def _manifest_text(manifest: dict) -> str:
    return json.dumps(manifest, sort_keys=True)


def _post_model_rows(pack_dir: Path) -> pd.DataFrame:
    frame = pd.read_parquet(pack_dir / "revenue_line_reconciliation.parquet")
    segment = frame.get("forecast_segment", pd.Series("", index=frame.index))
    return frame[segment.fillna("").astype(str).eq(POST_MODEL_SEGMENT)]


@pytest.fixture(params=sorted(PACK_DIRS), ids=sorted(PACK_DIRS))
def pack(request) -> tuple[str, Path, dict]:
    engine = request.param
    pack_dir = PACK_DIRS[engine]
    return engine, pack_dir, _manifest(pack_dir)


class TestComparatorLanguage:
    def test_no_vintage_is_named_as_the_comparator_unless_it_is_selected(self, pack):
        """A literal vintage name in prose must match the selected role."""

        engine, _, manifest = pack
        block = manifest.get("official_vintages") or {}
        selected = str(block.get("official_comparator_vintage_id") or "")
        assert selected, engine
        text = _manifest_text(manifest)
        registered = {"MBU26", "BEFU26", "PREFU26"}
        for vintage in registered - {selected}:
            assert f"{vintage} official comparator" not in text, (engine, vintage)

    def test_runtime_policy_names_all_three_selected_roles(self, pack):
        engine, _, manifest = pack
        block = manifest.get("official_vintages") or {}
        policy = str(manifest.get("runtime_policy") or "")
        assert policy, engine
        for key in (
            "official_comparator_vintage_id",
            "bridge_assumption_vintage_id",
            "long_run_shape_vintage_id",
        ):
            value = str(block.get(key) or "")
            assert value and value in policy, (engine, key, policy)


class TestLambdaLanguage:
    def test_lambda_is_never_described_as_the_active_runtime_path(self, pack):
        engine, _, manifest = pack
        text = _manifest_text(manifest).lower()
        for banned in (
            "default lambda_mode is optimized",
            "default lambda_mode is optimised",
            "lambda_mode is optimized",
        ):
            assert banned not in text, (engine, banned)

    def test_the_runtime_formulas_carry_no_lambda(self, pack):
        """The prose claim is checked against the rows, not just other prose."""

        engine, pack_dir, _ = pack
        frame = pd.read_parquet(pack_dir / "revenue_line_reconciliation.parquet")
        current = frame[
            frame["source_path"].astype(str).str.startswith("Current finalist")
        ]
        # fillna before join: the column is Arrow-backed, so a missing formula
        # iterates as a float and str.join raises rather than reporting a
        # finding - a crash that reads like a failure but tests nothing.
        formulas = " ".join(current["formula"].fillna("").astype(str).tolist()).lower()
        assert "lambda" not in formulas, engine
        assert "migration total" not in formulas, engine


class TestLightRucSemantics:
    def test_light_ruc_is_described_as_a_conventional_anchor(self, pack):
        """The manifest must not still claim a total-net-km target."""

        engine, _, manifest = pack
        text = _manifest_text(manifest).lower()
        assert "treated as total light-ruc net km" not in text, engine
        assert "governed as a total light-ruc net-km model input" not in text, engine

    def test_the_conventional_anchor_claim_matches_the_rows(self, pack):
        """Non-vacuity: the econometric Light RUC formula names the anchor."""

        engine, pack_dir, _ = pack
        frame = pd.read_parquet(pack_dir / "revenue_line_reconciliation.parquet")
        scoped = frame[
            frame["source_path"].astype(str).eq("Current finalist Base case")
            & frame["series_id"].astype(str).eq("light_ruc_net_km")
            & pd.to_numeric(frame["FY"], errors="coerce").eq(2030)
        ]
        assert not scoped.empty, engine
        formula = str(scoped["formula"].iloc[0]).lower()
        assert "conventional" in formula, (engine, formula)


class TestHorizonLanguage:
    def test_horizon_boundaries_are_explicit_and_correct(self, pack):
        engine, pack_dir, manifest = pack
        boundaries = manifest.get("horizon_boundaries") or {}
        assert boundaries, engine
        assert int(boundaries["post_model_start_fy"]) == FIRST_EXTRAPOLATION_FY
        assert int(boundaries["post_model_end_fy"]) == LAST_EXTRAPOLATION_FY
        assert int(boundaries["current_display_end_fy"]) == LAST_EXTRAPOLATION_FY

        rows = _post_model_rows(pack_dir)
        fy = pd.to_numeric(rows["FY"], errors="coerce")
        assert int(fy.min()) == int(boundaries["post_model_start_fy"]), engine
        assert int(fy.max()) == int(boundaries["current_display_end_fy"]), engine
        assert int(boundaries["econometric_cutoff_fy"]) == int(fy.min()) - 1, engine

    def test_no_claim_that_current_stops_at_the_econometric_cutoff(self, pack):
        """The defect this suite exists for.

        While post-model rows exist, the manifest must not say the last
        displayed or calculated Current FY is the econometric cutoff.
        """

        engine, pack_dir, manifest = pack
        rows = _post_model_rows(pack_dir)
        if rows.empty:
            pytest.skip("no post-model rows in this pack")
        cutoff = int(manifest["horizon_boundaries"]["econometric_cutoff_fy"])
        text = _manifest_text(manifest).lower()
        for banned in (
            f"last displayed/current calculation fy is fy{cutoff}",
            f"current-finalist comparisons stop at fy{cutoff}",
            f"comparative charts stop at fy{cutoff}",
            f"current-finalist comparative charts and runtime calculations stop at fy{cutoff}",
            "no extrapolated current extension is used",
        ):
            assert banned not in text, (engine, banned)

    def test_the_post_model_segment_is_described(self, pack):
        engine, _, manifest = pack
        layers = manifest.get("runtime_source_layers") or {}
        joined = " ".join(str(v) for v in layers.values()).lower()
        assert POST_MODEL_SEGMENT in joined, engine
        assert "anchored structural shape transition" in joined, engine


class TestFixedComponentLanguage:
    def test_heavy_bev_names_the_selected_bridge_vintage(self, pack):
        engine, _, manifest = pack
        block = manifest.get("official_vintages") or {}
        bridge = str(block.get("bridge_assumption_vintage_id") or "")
        audit = (manifest.get("target_semantics_audit") or {}).get("HEAVY_RUC") or {}
        decision = str(audit.get("decision") or "")
        assert decision, engine
        assert bridge in decision, (engine, bridge, decision)
        for other in {"MBU26", "BEFU26"} - {bridge}:
            assert other not in decision, (engine, other, decision)


class TestScheduleLanguage:
    def test_the_recorded_schedule_matches_the_described_construction(self, pack):
        engine, _, manifest = pack
        block = manifest.get("official_vintages") or {}
        schedule = str(block.get("long_run_transition_schedule_id") or "")
        assert schedule, engine
        layers = manifest.get("runtime_source_layers") or {}
        joined = " ".join(str(v) for v in layers.values())
        if schedule == UNBLENDED_SCHEDULE_ID:
            assert "blended geometrically" not in joined, engine
        else:
            assert schedule in joined, (engine, schedule)
            assert "blended geometrically" in joined, engine

    def test_both_engines_describe_the_same_governed_construction(self):
        """A divergence between engines would be a governance defect."""

        described = {}
        for engine, pack_dir in PACK_DIRS.items():
            block = _manifest(pack_dir).get("official_vintages") or {}
            described[engine] = (
                block.get("official_comparator_vintage_id"),
                block.get("bridge_assumption_vintage_id"),
                block.get("long_run_shape_vintage_id"),
                block.get("long_run_transition_schedule_id"),
                block.get("fleet_composition_source_id"),
            )
        assert len(set(described.values())) == 1, described
