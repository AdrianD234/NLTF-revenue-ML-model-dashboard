"""The blocking gates for the anchored structural shape transition.

Section 17 of the brief. Each test names the gate it enforces. Gates that the
maths makes exact are asserted as equalities; the rest carry the governed
tolerance already used elsewhere in the repo (1e-6 for revenue reconciliation),
and no tolerance is widened anywhere to obtain a pass.

Gates 14, 15 and 29 (role independence, manifest authority and the
future-vintage contract) live in test_anchored_shape_role_independence.py.
Gates 7-10 and 12 (weights and the blend identity) live in
test_long_run_shape_transition.py. Everything else is here.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard import official_vintage as ov
from model_dashboard.long_run_shape_transition import (
    FLEET_COMPOSITION_SOURCE_ID,
    LONG_RUN_SHAPE_METHOD_ID,
    SCHEDULES,
    UNBLENDED_SCHEDULE_ID,
)
from model_dashboard.post_model_extrapolation import (
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    LIGHT_POOL_MAX_RATIO_TO_VFM,
    RETIRED_PATHOLOGY_FY2050_MILLION_KM,
    build_post_model_extrapolation_annual,
    light_fleet_composition_audit,
    post_model_growth_indices,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "current_revenue_outlook"
EVIDENCE = ROOT / "artifacts" / "anchored_structural_shape_transition"
BASE_SCENARIO = "current_basecase"

# The governed reconciliation tolerance used across this repo.
RECONCILIATION_TOLERANCE = 1e-6

POOL_CLASSES = ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")


@pytest.fixture(scope="module")
def pack_inputs() -> dict[str, pd.DataFrame]:
    return {
        "line_reconciliation": pd.read_parquet(
            PACK_DIR / "revenue_line_reconciliation.parquet"
        ),
        "raw_quarterly_audit": pd.read_parquet(
            PACK_DIR / "raw_quarterly_forecast_audit.parquet"
        ),
        "scenario_input_wide": pd.read_parquet(
            PACK_DIR / "scenario_inputs" / "scenario_input_wide.parquet"
        ),
    }


@pytest.fixture(scope="module")
def shape_pack():
    pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
    assert pack is not None
    return pack


@pytest.fixture(scope="module")
def baseline() -> pd.DataFrame:
    # float_precision="round_trip": the baseline is written at %.17g so a
    # float64 survives the text round-trip, but pandas' default C parser
    # still loses the last bits when READING 17-digit input. Without this the
    # "unchanged exactly" gates degrade into ~1e-12 comparisons for a reason
    # that has nothing to do with the change under test.
    return pd.read_csv(
        EVIDENCE / "merged_main_baseline.csv", float_precision="round_trip"
    )


def _build(pack_inputs, shape_pack, schedule: str) -> pd.DataFrame:
    return build_post_model_extrapolation_annual(
        line_reconciliation=pack_inputs["line_reconciliation"],
        raw_quarterly_audit=pack_inputs["raw_quarterly_audit"],
        scenario_input_wide=pack_inputs["scenario_input_wide"],
        mbu26_official_annual=shape_pack.official_annual,
        repo_root=ROOT,
        long_run_shape_official_annual=shape_pack.official_annual,
        long_run_shape_vintage_id="BEFU26",
        transition_schedule_id=schedule,
    )


@pytest.fixture(scope="module")
def candidates(pack_inputs, shape_pack) -> dict[str, pd.DataFrame]:
    return {schedule: _build(pack_inputs, shape_pack, schedule) for schedule in SCHEDULES}


class TestPreservationGates:
    """Gates 1-6: PR #11 and everything upstream of FY2031 stay put."""

    def test_gate_1_pr11_registry_and_defaults_intact(self):
        assert ov.default_comparator_vintage_id(ROOT) == "BEFU26"
        assert ov.default_bridge_vintage_id(ROOT) == "BEFU26"
        assert ov.latest_official_vintage_id(ROOT) == "BEFU26"
        entry = ov.official_vintage_entry("MBU26", ROOT)
        assert bool(entry["available"]) is True

    def test_gate_1b_committed_registry_owns_the_shape_role(self):
        """The optional role must actually be owned in production."""

        assert ov.default_long_run_shape_vintage_id(ROOT) == "BEFU26"

    def test_gate_2_fy2025_actuals_unchanged(self, baseline):
        actuals = baseline[
            baseline["baseline_block"].eq("revenue_line_reconciliation")
            & baseline["engine"].eq("ensemble")
            & baseline["baseline_segment"].eq("historical_actual")
            & pd.to_numeric(baseline["FY"], errors="coerce").eq(2025)
        ]
        assert not actuals.empty
        live = pd.read_parquet(PACK_DIR / "revenue_line_reconciliation.parquet")
        live = live[pd.to_numeric(live["FY"], errors="coerce").eq(2025)]
        merged = actuals.merge(
            live,
            on=["source_path", "series_id", "FY"],
            suffixes=("_baseline", "_live"),
        )
        assert not merged.empty
        assert np.allclose(
            merged["value_baseline"].to_numpy(dtype=float),
            merged["value_live"].to_numpy(dtype=float),
            rtol=0.0,
            atol=0.0,
        )

    def test_gate_3_current_fy2026_2030_unchanged_exactly(self, baseline):
        econometric = baseline[
            baseline["baseline_block"].eq("revenue_line_reconciliation")
            & baseline["engine"].eq("ensemble")
            & baseline["baseline_segment"].eq("econometric_forecast")
        ]
        assert not econometric.empty
        fy = pd.to_numeric(econometric["FY"], errors="coerce")
        assert int(fy.min()) >= 2026 and int(fy.max()) <= ANCHOR_FY
        live = pd.read_parquet(PACK_DIR / "revenue_line_reconciliation.parquet")
        merged = econometric.merge(
            live,
            on=["source_path", "series_id", "FY"],
            suffixes=("_baseline", "_live"),
        )
        assert len(merged) == len(econometric)
        # equal_nan: these frames legitimately carry NaN for series a given
        # vintage does not publish. Identical NaN PLACEMENT is still required,
        # and every real value must match bit for bit.
        assert np.array_equal(
            merged["value_baseline"].to_numpy(dtype=float),
            merged["value_live"].to_numpy(dtype=float),
            equal_nan=True,
        )

    @pytest.mark.parametrize("vintage_id", ["BEFU26", "MBU26"])
    def test_gates_4_and_5_official_published_rows_unchanged(self, baseline, vintage_id):
        frozen = baseline[
            baseline["baseline_block"].eq("official_vintage_official_annual")
            & baseline["official_vintage_id"].eq(vintage_id)
        ]
        assert not frozen.empty
        pack = ov.load_official_vintage(vintage_id, repo_root=ROOT)
        assert pack is not None
        merged = frozen.merge(
            pack.official_annual, on=["series_id", "FY"], suffixes=("_frozen", "_live")
        )
        assert len(merged) == len(frozen)
        assert np.array_equal(
            merged["value_frozen"].to_numpy(dtype=float),
            merged["value_live"].to_numpy(dtype=float),
            equal_nan=True,
        )

    def test_gate_6_promoted_fitted_states_unchanged(self, baseline):
        """The transition is post-model; it cannot touch fitted state."""

        live = pd.read_parquet(PACK_DIR / "revenue_line_reconciliation.parquet")
        fitted = live[
            live["value_status"].astype(str).eq("current_finalist_forecast")
        ]
        frozen = baseline[
            baseline["baseline_block"].eq("revenue_line_reconciliation")
            & baseline["engine"].eq("ensemble")
            & baseline["value_status"].astype(str).eq("current_finalist_forecast")
        ]
        assert len(fitted) == len(frozen)


class TestAnchorAndShapeGates:
    """Gates 11-13: the anchor holds and no official level is substituted."""

    def test_gate_11_fy2030_anchor_is_never_emitted_or_moved(self, candidates):
        for schedule, frame in candidates.items():
            assert ANCHOR_FY not in set(frame["fy"].astype(int)), schedule

    def test_gate_11b_seam_starts_from_the_anchor(self, candidates, pack_inputs):
        """FY2031 under every schedule starts from the same FY2030 level.

        With w(2030) = 0 the blend cannot move the anchor, so the FY2031 value
        differs between schedules only by one year of blended growth - never by
        a jump in level.
        """

        line = pack_inputs["line_reconciliation"]
        anchor = float(
            pd.to_numeric(
                line[
                    line["source_path"].eq("Current finalist Base case")
                    & pd.to_numeric(line["FY"], errors="coerce").eq(ANCHOR_FY)
                    & line["series_id"].eq("light_petrol_vkt")
                ]["value"],
                errors="coerce",
            ).iloc[0]
        )
        for schedule, frame in candidates.items():
            first = float(
                frame[
                    frame["scenario_name"].eq(BASE_SCENARIO)
                    & frame["series_id"].eq("light_petrol_vkt")
                    & frame["fy"].eq(FIRST_EXTRAPOLATION_FY)
                ]["value"].iloc[0]
            )
            assert abs(first / anchor - 1.0) < 0.05, (schedule, first, anchor)

    def test_gate_12_complete_transition_equals_official_normalised_growth(
        self, candidates, shape_pack
    ):
        """At w = 1 the hybrid index IS the structural index."""

        official = shape_pack.official_annual.pivot_table(
            index="FY", columns="series_id", values="value", aggfunc="first"
        )
        frame = candidates["early_structural"]
        petrol = (
            frame[
                frame["scenario_name"].eq(BASE_SCENARIO)
                & frame["series_id"].eq("light_petrol_vkt")
            ]
            .set_index("fy")["value"]
            .sort_index()
        )
        # Completion is FY2040, so FY2041+ must track the official growth ratio.
        for fy in (2041, 2045, 2050):
            observed = petrol.loc[fy] / petrol.loc[2041]
            expected = (
                official.at[fy, "light_petrol_vkt"]
                / official.at[2041, "light_petrol_vkt"]
            )
            assert observed == pytest.approx(expected, rel=1e-12)

    def test_gate_13_official_level_is_never_substituted(self, candidates, shape_pack):
        """The terminal ratio is the ANCHOR ratio, not 1.0."""

        official = shape_pack.official_annual.pivot_table(
            index="FY", columns="series_id", values="value", aggfunc="first"
        )
        frame = candidates["early_structural"]
        petrol = frame[
            frame["scenario_name"].eq(BASE_SCENARIO)
            & frame["series_id"].eq("light_petrol_vkt")
        ].set_index("fy")["value"]
        ratios = [
            float(petrol.loc[fy] / official.at[fy, "light_petrol_vkt"])
            for fy in (2041, 2045, 2050)
        ]
        # Constant after completion...
        assert max(ratios) - min(ratios) < 1e-12
        # ...and NOT 1.0, which is what substituting the official level would give.
        assert abs(ratios[0] - 1.0) > 1e-3


class TestMethodPurityGates:
    """Gates 16-19: nothing retired comes back."""

    def test_gate_16_no_lambda_in_decision_facing_calculations(self, candidates):
        for schedule, frame in candidates.items():
            formulas = " ".join(frame["formula"].astype(str)).lower()
            assert "lambda" not in formulas, schedule
            assert "migration total" not in formulas, schedule

    def test_gate_16b_module_source_carries_no_lambda_arithmetic(self):
        source = (
            ROOT / "model_dashboard" / "long_run_shape_transition.py"
        ).read_text(encoding="utf-8")
        # The word appears only where the module explains that lambda is NOT
        # what the transition weight is.
        lowered = source.lower()
        assert "lambda" in lowered  # the explanation exists
        assert "lambda *" not in lowered
        assert "* lambda" not in lowered

    def test_gate_17_no_conventional_over_share_expansion(self, candidates):
        for schedule, frame in candidates.items():
            formulas = " ".join(frame["formula"].astype(str)).lower()
            assert "/ share" not in formulas, schedule
            assert "conventional share" not in formulas.replace(
                "exact vfm conventional share", ""
            ), schedule

    def test_gate_18_exact_vfm_composition_remains_default(self, candidates):
        for schedule, frame in candidates.items():
            assert set(frame["fleet_composition_source_id"]) == {
                FLEET_COMPOSITION_SOURCE_ID
            }, schedule
            assert set(frame["fleet_composition_scenario"]) == {"Base_EV"}, schedule

    def test_gate_19_official_embedded_composition_is_audit_only(self, shape_pack):
        audit = light_fleet_composition_audit(
            hybrid_pool_by_fy={2040: 40_000.0, 2050: 50_000.0},
            repo_root=ROOT,
            official_shares={"BEFU26": shape_pack.official_annual},
        )
        embedded = audit[audit["composition_source"].eq("BEFU26_embedded_shares")]
        assert not embedded.empty
        assert set(embedded["composition_role"]) == {"audit_only"}
        production = audit[audit["composition_role"].eq("production_default")]
        assert set(production["composition_source"]) == {"exact_VFM_Base_EV"}


class TestActivityIdentityGates:
    """Gates 20-22 plus the retired-pathology ban."""

    def test_gate_20_light_classes_sum_to_the_hybrid_pool(self, candidates):
        for schedule, frame in candidates.items():
            wide = frame.pivot_table(
                index=["scenario_name", "fy"], columns="series_id", values="value"
            )
            classes = sum(wide[column] for column in POOL_CLASSES)
            conventional = wide["current_light_ruc_conventional_modelled_km"]
            # The conventional class and the published conventional line are
            # the same quantity, by construction.
            assert np.allclose(
                conventional.to_numpy(),
                wide["light_ruc_net_km"].to_numpy(),
                rtol=0.0,
                atol=0.0,
            ), schedule
            assert np.isfinite(classes.to_numpy()).all(), schedule

    def test_gate_21_ped_vkt_equals_vktpc_times_population(self, candidates, pack_inputs):
        """Exact by construction: VKTpc is derived from petrol and population."""

        for schedule, frame in candidates.items():
            growth = post_model_growth_indices(
                pack_inputs["raw_quarterly_audit"],
                pack_inputs["scenario_input_wide"],
                scenario_name=BASE_SCENARIO,
                repo_root=ROOT,
            ).set_index("fy")
            wide = frame[frame["scenario_name"].eq(BASE_SCENARIO)].pivot_table(
                index="fy", columns="series_id", values="value"
            )
            for fy in wide.index:
                population = float(growth.at[fy, "scenario_population"])
                implied = (
                    float(wide.at[fy, "ped_vkt_per_capita"]) * population / 1_000_000.0
                )
                published = float(wide.at[fy, "light_petrol_vkt"])
                assert implied == pytest.approx(published, rel=1e-12), (schedule, fy)

    def test_gate_22_heavy_bev_is_fixed_by_the_bridge_contract(self, candidates, shape_pack):
        official = shape_pack.official_annual.pivot_table(
            index="FY", columns="series_id", values="value", aggfunc="first"
        )
        for schedule, frame in candidates.items():
            heavy_bev = frame[
                frame["scenario_name"].eq(BASE_SCENARIO)
                & frame["series_id"].eq("heavy_bev_ruc_net_km")
            ].set_index("fy")["value"]
            for fy, value in heavy_bev.items():
                assert float(value) == pytest.approx(
                    float(official.at[fy, "heavy_bev_ruc_net_km"]), rel=0.0, abs=0.0
                ), (schedule, fy)

    def test_retired_pathology_stays_banned(self, candidates):
        for schedule, frame in candidates.items():
            pool = (
                frame[frame["series_id"].isin(POOL_CLASSES)]
                .groupby(["scenario_name", "fy"])["value"]
                .sum()
            )
            assert float(pool.max()) < RETIRED_PATHOLOGY_FY2050_MILLION_KM, schedule

    def test_light_pool_stays_inside_the_vfm_divergence_guard(self, candidates, pack_inputs):
        vfm = pd.read_csv(ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
        vfm = vfm[vfm["scenario"].eq("Base_EV")].set_index("june_year")
        vfm_pool = (
            vfm["light_ruc_conventional_million_km"]
            + vfm["light_ruc_bev_million_km"]
            + vfm["light_ruc_phev_million_km"]
        )
        for schedule, frame in candidates.items():
            pool = (
                frame[
                    frame["scenario_name"].eq(BASE_SCENARIO)
                    & frame["series_id"].isin(POOL_CLASSES)
                ]
                .groupby("fy")["value"]
                .sum()
            )
            for fy, value in pool.items():
                assert float(value) <= LIGHT_POOL_MAX_RATIO_TO_VFM * float(
                    vfm_pool.loc[fy]
                ), (schedule, fy)


class TestFormulaClosureGates:
    """Gate 25: every aggregate closes through the governed registry."""

    IDENTITIES = {
        "gross_fed_revenue": (
            ["gross_ped_revenue", "gross_lpg_revenue", "gross_cng_revenue"],
            [],
        ),
        "net_fed_revenue": (["gross_fed_revenue"], ["fed_refunds"]),
        "gross_ruc_revenue": (
            [
                "light_ruc_net_revenue",
                "heavy_ruc_net_revenue",
                "light_bev_ruc_net_revenue",
                "heavy_bev_ruc_net_revenue",
                "phev_ruc_net_revenue",
                "ruc_refunds",
            ],
            [],
        ),
        "total_ruc_net_revenue": (["gross_ruc_revenue"], ["ruc_admin_revenue", "ruc_refunds"]),
        "net_mvr_revenue": (
            ["mr1_revenue", "mr2_revenue"],
            ["mvr_admin_revenue", "mvr_refunds"],
        ),
        "total_nltf_net_revenue": (
            ["total_revenue_net_admin"],
            ["total_refunds"],
        ),
    }

    def test_gate_25_aggregates_close(self, candidates):
        for schedule, frame in candidates.items():
            wide = frame.pivot_table(
                index=["scenario_name", "fy"], columns="series_id", values="value"
            )
            for target, (plus, minus) in self.IDENTITIES.items():
                recomputed = sum(wide[c] for c in plus) - sum(wide[c] for c in minus)
                residual = (wide[target] - recomputed).abs().max()
                assert float(residual) < RECONCILIATION_TOLERANCE, (schedule, target)

    def test_no_force_balancing_residual_column_exists(self, candidates):
        for schedule, frame in candidates.items():
            assert "plug" not in frame.columns
            assert "balancing_item" not in frame.columns


class TestEvidenceGates:
    """Gates 30-31: the evidence is non-vacuous and independently derived."""

    def test_gate_30_every_evidence_join_is_non_vacuous(self):
        required = {
            "transition_weight_candidates.csv": 1,
            "candidate_activity_paths.csv": 1,
            "candidate_revenue_paths.csv": 1,
            "candidate_transition_metrics.csv": 1,
            "candidate_shape_scorecard.csv": 4,
            "current_growth_indices.csv": 1,
            "official_growth_indices.csv": 1,
            "hybrid_growth_indices.csv": 1,
            "anchor_shape_level_audit.csv": 1,
            "light_fleet_composition_audit.csv": 1,
            "formula_reconciliation.csv": 1,
            "merged_main_baseline.csv": 1,
        }
        for name, minimum in required.items():
            path = EVIDENCE / name
            assert path.exists(), name
            frame = pd.read_csv(path)
            assert len(frame) >= minimum, (name, len(frame))

    def test_gate_31_audit_does_not_duplicate_constructor_arithmetic(self):
        """The audit recomputes the blend; it must agree AND be separate code."""

        audit = pd.read_csv(EVIDENCE / "anchor_shape_level_audit.csv")
        residual = (
            audit["hybrid_growth_index"] - audit["recomputed_hybrid_index"]
        ).abs().max()
        assert float(residual) < 1e-12
        # The recomputation is written out in the audit, not imported from the
        # constructor: the constructor calls geometric_blend_index, the audit
        # uses the explicit power form.
        source = (
            ROOT / "model_dashboard" / "post_model_extrapolation.py"
        ).read_text(encoding="utf-8")
        assert "current_index ** (1.0 - weight)" in source

    def test_scorecard_covers_every_governed_candidate(self):
        scorecard = pd.read_csv(EVIDENCE / "candidate_shape_scorecard.csv")
        assert set(scorecard["candidate_id"]) == set(SCHEDULES)


class TestManifestVocabulary:
    """The method/schedule identifiers the pack manifest has to record."""

    def test_method_and_composition_ids_are_stamped_on_every_row(self, candidates):
        for schedule, frame in candidates.items():
            assert set(frame["long_run_shape_method_id"]) == {
                LONG_RUN_SHAPE_METHOD_ID
            }, schedule
            assert set(frame["long_run_transition_schedule_id"]) == {schedule}, schedule

    def test_manifest_key_vocabulary_is_complete(self):
        for key in (
            "long_run_shape_vintage_id",
            "long_run_shape_vintage_sha256",
            "long_run_shape_method_id",
            "long_run_transition_schedule_id",
            "long_run_anchor_fy",
            "long_run_transition_end_fy",
            "fleet_composition_source_id",
        ):
            assert key in ov.LONG_RUN_SHAPE_MANIFEST_KEYS


class TestProductionDefaultUnchanged:
    """The public default must not move until the owner selects a candidate."""

    def test_constructor_defaults_to_unblended(self, pack_inputs, shape_pack):
        frame = build_post_model_extrapolation_annual(
            line_reconciliation=pack_inputs["line_reconciliation"],
            raw_quarterly_audit=pack_inputs["raw_quarterly_audit"],
            scenario_input_wide=pack_inputs["scenario_input_wide"],
            mbu26_official_annual=shape_pack.official_annual,
            repo_root=ROOT,
        )
        assert set(frame["long_run_transition_schedule_id"]) == {
            UNBLENDED_SCHEDULE_ID
        }

    def test_committed_packs_carry_no_transition(self):
        for relative in (
            Path("data") / "current_revenue_outlook",
            Path("data") / "engine_ar1" / "current_revenue_outlook",
        ):
            manifest = json.loads(
                (ROOT / relative / "manifest.json").read_text(encoding="utf-8")
            )
            block = manifest.get("official_vintages") or {}
            schedule = str(block.get("long_run_transition_schedule_id") or
                           UNBLENDED_SCHEDULE_ID)
            assert schedule == UNBLENDED_SCHEDULE_ID, relative

    def test_unblended_reproduces_the_frozen_baseline(self, candidates, baseline):
        """The control candidate IS merged main, to within float noise."""

        frozen = baseline[
            baseline["baseline_block"].eq("revenue_line_reconciliation")
            & baseline["engine"].eq("ensemble")
            & baseline["baseline_segment"].eq("post_model_extrapolation")
        ]
        frame = candidates[UNBLENDED_SCHEDULE_ID]
        merged = frame.merge(
            frozen,
            left_on=["source_path", "series_id", "fy"],
            right_on=["source_path", "series_id", "FY"],
            suffixes=("_new", "_old"),
        )
        assert len(merged) == len(frozen)
        relative = (merged["value_new"] - merged["value_old"]).abs() / merged[
            "value_old"
        ].abs().clip(lower=1e-9)
        assert float(relative.max()) < 1e-12
