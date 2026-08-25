"""Hard gates for the Persistent downside scenario.

The scenario's promise is behavioural: after the downside begins the
downside/central ratio never crosses one, the cumulative shortfall never
recovers toward zero, there is no oscillation, the seam is continuous, the
terminal window is exactly flat, and the governed terminal wedge stays inside
the committed lower-band evidence range. Each promise is a test here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard import persistent_downside as pdm

ROOT = Path(__file__).resolve().parents[1]


def _synthetic_values(
    *,
    high_ratios: dict[int, float] | None = None,
    first_fy: int = 2026,
    last_fy: int = 2050,
) -> tuple[dict[tuple[str, int], float], dict[tuple[str, int], float]]:
    ratios = high_ratios or {
        2026: 0.995,
        2027: 0.97,
        2028: 0.96,
        2029: 0.975,
        2030: 0.99,
    }
    base: dict[tuple[str, int], float] = {}
    high: dict[tuple[str, int], float] = {}
    for series in pdm.DEMAND_LEAF_SERIES:
        for fy in range(first_fy, last_fy + 1):
            level = 100.0 * (1.02 ** (fy - first_fy))
            base[(series, fy)] = level
            high[(series, fy)] = level * ratios.get(fy, 1.0)
    for fy in range(first_fy, last_fy + 1):
        base[("total_nltf_net_revenue", fy)] = (
            sum(base[(series, fy)] for series in pdm.DEMAND_LEAF_SERIES) + 50.0
        )
        base[("ruc_admin_revenue", fy)] = 50.0
    return base, high


def _build(base=None, high=None):
    if base is None:
        base, high = _synthetic_values()
    return pdm.build_persistent_downside_annual_values(
        base, high, aggregate_series={"total_nltf_net_revenue": "total"}
    )


class TestWedgePath:
    def test_seam_is_continuous_and_terminal_exactly_flat(self):
        path = pdm.downside_wedge_path(0.03).set_index("fy")
        # Smoothstep leaves the seam with near-zero slope: the first ramp
        # year moves less than 3% of the remaining distance to the terminal.
        first_step = float(path.at[2031, "w"]) - 0.03
        assert 0.0 <= first_step < 0.03 * (pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE - 0.03) / 0.03 + 0.01
        flat = path.loc[pdm.DOWNSIDE_TERMINAL_FLAT_FIRST_FY :, "w"].to_numpy()
        assert np.all(flat == flat[0])
        assert flat[0] == pytest.approx(pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE, abs=1e-12)

    def test_monotone_from_seam_to_terminal_in_both_directions(self):
        deepening = pdm.downside_wedge_path(0.02)["w"].to_numpy()
        assert np.all(np.diff(deepening) >= -1e-15)
        easing = pdm.downside_wedge_path(0.30)["w"].to_numpy()
        assert np.all(np.diff(easing) <= 1e-15)

    def test_negative_seam_fails_closed(self):
        with pytest.raises(pdm.PersistentDownsideError):
            pdm.downside_wedge_path(-0.01)

    def test_completion_and_flat_years_are_the_governed_schedule(self):
        assert pdm.DOWNSIDE_RAMP_COMPLETION_FY == 2042
        assert pdm.DOWNSIDE_TERMINAL_FLAT_FIRST_FY == 2043
        assert pdm.DOWNSIDE_LAST_FY == 2050


class TestConstructionGates:
    def test_ratchet_never_recovers_within_the_short_run(self):
        values = _build()
        leaf = values[values["series_id"].eq("gross_ped_revenue")].set_index("fy")
        # High recovers after 2028 (0.975, 0.99); the ratchet must not.
        assert float(leaf.at[2028, "factor"]) == pytest.approx(0.96)
        assert float(leaf.at[2029, "factor"]) == pytest.approx(0.96)
        assert float(leaf.at[2030, "factor"]) == pytest.approx(0.96)

    def test_ratio_never_crosses_one_and_never_recovers(self):
        values = _build()
        for series in pdm.DEMAND_LEAF_SERIES:
            ordered = values[values["series_id"].eq(series)].sort_values("fy")
            factors = ordered["factor"].to_numpy(dtype=float)
            assert (factors <= 1.0 + 1e-12).all()
            assert (np.diff(factors) <= 1e-9).all()

    def test_terminal_window_is_exactly_flat_at_the_governed_wedge(self):
        values = _build()
        leaf = values[values["series_id"].eq("heavy_ruc_net_revenue")].set_index("fy")
        flat = leaf.loc[pdm.DOWNSIDE_TERMINAL_FLAT_FIRST_FY :, "factor"].to_numpy()
        assert np.all(flat == flat[0])
        assert flat[0] == pytest.approx(
            float(np.exp(-pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE)), abs=1e-15
        )

    def test_seam_has_no_jump(self):
        values = _build()
        leaf = values[values["series_id"].eq("light_ruc_net_revenue")].set_index("fy")
        seam_factor = float(leaf.at[2030, "factor"])
        first_ramp = float(leaf.at[2031, "factor"])
        # Continuity: the first long-run year moves by well under one
        # ratchet-step of the short run.
        assert 0.0 < seam_factor - first_ramp < 0.005

    def test_fixed_lines_stay_central_and_aggregates_rebuild_additively(self):
        base, high = _synthetic_values()
        values = _build(base, high)
        fixed = values[values["series_id"].eq("ruc_admin_revenue")]
        assert (fixed["factor"] == 1.0).all()
        assert (fixed["phase"] == "carried_fixed_line").all()
        total = values[values["series_id"].eq("total_nltf_net_revenue")].set_index("fy")
        for fy in (2035, 2050):
            leaf_delta = sum(
                values[
                    values["series_id"].eq(series) & values["fy"].eq(fy)
                ]["value"].iloc[0]
                - base[(series, fy)]
                # The rebuild bases are the module's own leaf registries, so a
                # deliberately added revenue leaf (the FED->RUC transition's
                # petrol RUC line) keeps this gate green by construction while
                # an aggregate that drifted from its leaves still fails it.
                for series in (*pdm._PED_REVENUE_LEAVES, *pdm._RUC_REVENUE_LEAVES)
            )
            expected = base[("total_nltf_net_revenue", fy)] + leaf_delta
            assert float(total.at[fy, "value"]) == pytest.approx(expected, rel=1e-12)
        # The total's annual delta is negative every year: the cumulative
        # shortfall widens or plateaus and can never recover toward zero.
        assert (total["factor"] <= 1.0 + 1e-12).all()

    def test_missing_high_response_fails_closed(self):
        base, high = _synthetic_values()
        del high[("gross_ped_revenue", 2028)]
        with pytest.raises(pdm.PersistentDownsideError, match="High conflict"):
            _build(base, high)

    def test_zero_central_years_are_carried_not_rejected(self):
        """A lever can zero a demand leaf (full eRUC displaces gross PED).

        Zero times any wedge is zero: the year is carried at 0.0 with its own
        phase, the ratchet is untouched, and the missing-High gate does not
        fire for it - the shape of the CI failure this pins.
        """
        base, high = _synthetic_values()
        for fy in (2029, 2035):
            base[("gross_ped_revenue", fy)] = 0.0
        del high[("gross_ped_revenue", 2029)]
        values = _build(base, high)
        leaf = values[values["series_id"].eq("gross_ped_revenue")].set_index("fy")
        for fy in (2029, 2035):
            assert float(leaf.at[fy, "value"]) == 0.0
            assert str(leaf.at[fy, "phase"]) == "zero_central_carried"
        # Positive years around the zeros still take the ratchet/wedge.
        assert float(leaf.at[2028, "factor"]) == pytest.approx(0.96)
        assert float(leaf.at[2030, "factor"]) == pytest.approx(0.96)
        assert float(leaf.at[2050, "factor"]) == pytest.approx(
            float(np.exp(-pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE))
        )

    def test_negative_central_still_fails_closed(self):
        base, high = _synthetic_values()
        base[("gross_ped_revenue", 2029)] = -1.0
        with pytest.raises(pdm.PersistentDownsideError, match="non-negative"):
            _build(base, high)

    def test_class_shares_survive_the_wedge(self):
        """Pool-first allocation: one wedge moves the pool, never the split."""
        values = _build()
        classes = ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")
        by_class = {
            series: values[values["series_id"].eq(series)].set_index("fy")["factor"]
            for series in classes
        }
        for fy in (2032, 2040, 2050):
            factors = {series: float(by_class[series].at[fy]) for series in classes}
            assert len({round(v, 12) for v in factors.values()}) == 1, factors


class TestBandEvidence:
    def test_terminal_wedge_sits_inside_the_committed_band_evidence(self):
        band_rows = pd.read_parquet(
            ROOT / "data" / "revenue_outlook_uncertainty" / "uncertainty_band_rows.parquet"
        )
        values = _build()
        evidence = pdm.persistent_downside_band_evidence(band_rows, values)
        gate = evidence[evidence["measure"].eq("terminal_within_band_evidence_range")]
        assert float(gate["value"].iloc[0]) == 1.0
        lower50 = float(
            evidence.loc[evidence["measure"].eq("lower50_evidence_wedge"), "value"].iloc[0]
        )
        lower80 = float(
            evidence.loc[evidence["measure"].eq("lower80_evidence_wedge"), "value"].iloc[0]
        )
        assert lower50 < pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE < lower80

    def test_tampered_terminal_fails_the_evidence_gate(self):
        band_rows = pd.read_parquet(
            ROOT / "data" / "revenue_outlook_uncertainty" / "uncertainty_band_rows.parquet"
        )
        values = _build()
        original = pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE
        try:
            pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE = 0.5
            with pytest.raises(pdm.PersistentDownsideError, match="outside the band"):
                pdm.persistent_downside_band_evidence(band_rows, values)
        finally:
            pdm.PERSISTENT_DOWNSIDE_TERMINAL_WEDGE = original


class TestChartRowApplication:
    def _chart_rows(self) -> pd.DataFrame:
        base, high = _synthetic_values()
        rows = []
        for (series, fy), value in base.items():
            rows.append(
                {
                    "scenario_name": "current_basecase",
                    "scenario_role": "basecase",
                    "trace_name": "Current finalist Base case",
                    "series_id": series,
                    "time_grain": "june_year",
                    "june_year": fy,
                    "period": f"FY{fy}",
                    "value": value,
                }
            )
        for (series, fy), value in high.items():
            rows.append(
                {
                    "scenario_name": "middle_east_high",
                    "scenario_role": "comparison",
                    "trace_name": "Middle East conflict: High",
                    "series_id": series,
                    "time_grain": "june_year",
                    "june_year": fy,
                    "period": f"FY{fy}",
                    "value": value,
                }
            )
        return pd.DataFrame(rows)

    def test_appends_annual_only_trace_and_is_idempotent(self):
        chart = self._chart_rows()
        once, audit = pdm.apply_persistent_downside_to_chart_rows(
            chart, aggregate_series={"total_nltf_net_revenue": "total"}
        )
        added = once[once["scenario_name"].eq(pdm.PERSISTENT_DOWNSIDE_SCENARIO_ID)]
        assert not added.empty
        assert set(added["time_grain"]) == {"june_year"}
        assert set(added["trace_name"]) == {pdm.PERSISTENT_DOWNSIDE_TRACE_NAME}
        assert set(added["scenario_role"]) == {"comparison"}
        assert not audit.empty
        twice, _ = pdm.apply_persistent_downside_to_chart_rows(
            once, aggregate_series={"total_nltf_net_revenue": "total"}
        )
        assert len(twice) == len(once)

    def test_downside_total_below_central_every_year(self):
        chart = self._chart_rows()
        combined, _ = pdm.apply_persistent_downside_to_chart_rows(
            chart, aggregate_series={"total_nltf_net_revenue": "total"}
        )
        total = combined[combined["series_id"].eq("total_nltf_net_revenue")]
        pivot = total.pivot_table(
            index="june_year", columns="scenario_name", values="value", aggfunc="first"
        )
        delta = pivot[pdm.PERSISTENT_DOWNSIDE_SCENARIO_ID] - pivot["current_basecase"]
        assert (delta <= 1e-9).all()
        cumulative = delta.sort_index().cumsum()
        assert (np.diff(cumulative.to_numpy()) <= 1e-9).all()

    def test_missing_high_trace_fails_closed(self):
        chart = self._chart_rows()
        without_high = chart[~chart["scenario_name"].eq("middle_east_high")]
        with pytest.raises(pdm.PersistentDownsideError):
            pdm.apply_persistent_downside_to_chart_rows(
                without_high, aggregate_series={"total_nltf_net_revenue": "total"}
            )
