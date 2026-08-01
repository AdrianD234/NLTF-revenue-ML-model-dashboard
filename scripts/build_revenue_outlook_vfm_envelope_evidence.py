"""Evidence for the Integrated VFM Scenario Envelope.

Rebuilds, from the committed runtime packs only:

- ``applicability_audit.csv``   which series receive the MoT VFM Fast-Slow
                               range, over which years, how wide, and why not
                               when they do not;
- ``band_values.csv``          every displayed bound beside an INDEPENDENTLY
                               recomputed exact Fast/Slow extreme, so the two
                               can be compared without trusting the band
                               constructor;
- ``control_sensitivity.csv``  which selectors move the envelope and which are
                               display-only;
- ``page_timings.csv``         Revenue Outlook construction cost before and
                               after the separate uncertainty-fan figure left
                               the default layout.

Deterministic and clean-clone safe: no network, no scratch, no wall-clock in
any value column except the explicitly labelled timing table.

    .venv\\Scripts\\python.exe scripts\\build_revenue_outlook_vfm_envelope_evidence.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    FAN_SOURCE_AUTO,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

OUT = ROOT / "artifacts" / "revenue_outlook_vfm_envelope"
FED = "Current planned path"
TRACES = (
    "Actual",
    "Current finalist Base case",
    "Current finalist High population/comparison",
    "BEFU26 official",
)
SERIES = (
    "Total NLTF revenue",
    "Total RUC+PED revenue",
    "Total RUC all classes",
    "Net FED revenue",
    "PED volume",
    "PED revenue",
    "Light RUC revenue",
    "Light RUC net km",
    "Heavy RUC revenue",
    "Net MVR revenue",
)
ENGINES = (
    ("ensemble", Path(CURRENT_REVENUE_OUTLOOK_DIR)),
    ("ar1", Path("data") / "engine_ar1" / "current_revenue_outlook"),
)


def uptake_key(
    mode: str = DEFAULT_EV_UPTAKE_MODE,
    *,
    ped_retention: bool = False,
    vintage: str = "BEFU26",
    overlay: bool = False,
    schedule: str = "balanced_structural",
    shape_vintage: str = "BEFU26",
    current_policy: str = app.FED_POLICY_PUBLISHED,
) -> tuple:
    """The production key shape built by ``render_revenue_outlook_page``."""
    return (
        mode, (), (), current_policy, app.FED_POLICY_PUBLISHED,
        ped_retention, vintage, overlay, schedule, shape_vintage,
    )


def sensitivity_key() -> tuple:
    return app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")


def view_for(pack, signature, series: str, key: tuple) -> dict:
    return app.cached_revenue_outlook_view(
        signature, series, "june_year", FED, TRACES, sensitivity_key(),
        PED_BRIDGE_DEFAULT_MODE, key, pack,
    )


def independent_bounds(pack, signature, series: str, key: tuple) -> pd.DataFrame:
    """Fast/Slow extremes recomputed from the overlay rows, not from the band."""
    collected: dict[str, pd.Series] = {}
    for name in ("MoT VFM fast", "MoT VFM slow"):
        rows, *_ = app.cached_scenario_overlay_rows(
            signature, sensitivity_key(), PED_BRIDGE_DEFAULT_MODE,
            (name, *tuple(key[1:])), pack,
        )
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["trace_name"].astype(str).eq("Current finalist Base case")
            & ~rows["row_type"].astype(str).eq("historical_actual")
            & rows["series_label"].astype(str).eq(series)
            & rows["fed_path"].astype(str).eq(FED)
        ]
        collected[name] = pd.Series(
            pd.to_numeric(selected["value"], errors="coerce").to_numpy(),
            index=selected["period"].astype(str),
        )
    merged = pd.DataFrame(collected).dropna()
    return pd.DataFrame(
        {
            "period": merged.index.astype(str),
            "expected_lower": merged.min(axis=1).to_numpy(),
            "expected_upper": merged.max(axis=1).to_numpy(),
            "vfm_fast": merged["MoT VFM fast"].to_numpy(),
            "vfm_slow": merged["MoT VFM slow"].to_numpy(),
        }
    ).reset_index(drop=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    applicability: list[pd.DataFrame] = []
    parity: list[pd.DataFrame] = []
    timings: list[dict] = []

    for engine, relative in ENGINES:
        directory = ROOT / relative
        if not directory.exists():
            continue
        pack = load_revenue_outlook_pack(directory, repo_root=ROOT)
        signature = revenue_outlook_signature(directory, ROOT)
        key = uptake_key()

        for series in SERIES:
            view = view_for(pack, signature, series, key)
            audit = view["cone_band_audit"].copy()
            audit.insert(0, "engine", engine)
            applicability.append(audit)

            band = view["cone_band"]
            if band.empty:
                continue
            expected = independent_bounds(pack, signature, series, key)
            joined = band.merge(expected, on="period", how="left", validate="one_to_one")
            joined.insert(0, "series", series)
            joined.insert(0, "engine", engine)
            joined["lower_matches_independent"] = (
                (joined["lower"] - joined["expected_lower"]).abs() < 1e-9
            )
            joined["upper_matches_independent"] = (
                (joined["upper"] - joined["expected_upper"]).abs() < 1e-9
            )
            joined["width"] = joined["upper"] - joined["lower"]
            parity.append(joined)

    pd.concat(applicability, ignore_index=True).to_csv(
        OUT / "applicability_audit.csv", index=False
    )
    parity_frame = pd.concat(parity, ignore_index=True)
    parity_frame.to_csv(OUT / "band_values.csv", index=False)
    assert parity_frame["lower_matches_independent"].all()
    assert parity_frame["upper_matches_independent"].all()

    # ---------------------------------------------------- control sensitivity
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    baseline = view_for(pack, signature, "Total NLTF revenue", uptake_key())["cone_band"]
    rows = []
    cases = (
        ("displayed VFM basis = MoT VFM fast", uptake_key("MoT VFM fast"), "display_only"),
        ("displayed VFM basis = MoT VFM slow", uptake_key("MoT VFM slow"), "display_only"),
        ("official comparator = MBU26", uptake_key(vintage="MBU26"), "display_only"),
        ("official comparator overlay on", uptake_key(overlay=True), "display_only"),
        (
            "long-run transition schedule = unblended",
            uptake_key(schedule=app.UNBLENDED_SCHEDULE_ID, shape_vintage=""),
            "value_changing_outside_band_span",
        ),
        ("Current 12c policy = no uplift", uptake_key(current_policy=app.FED_POLICY_OFF), "value_changing"),
        ("PED retention sensitivity on", uptake_key(ped_retention=True), "value_changing"),
        ("back to the original controls", uptake_key(), "display_only"),
    )
    default_identity = tuple(uptake_key()[1:])
    for label, key, expectation in cases:
        band = view_for(pack, signature, "Total NLTF revenue", key)["cone_band"]
        identical = baseline.reset_index(drop=True).equals(band.reset_index(drop=True))
        rows.append(
            {
                "control_change": label,
                "expectation": expectation,
                "band_identical_to_default": identical,
                "rows": len(band),
                # True when this change alters the band's cache identity, i.e.
                # forces a recompute. The displayed VFM basis is slot 0 and is
                # deliberately excluded: the envelope always evaluates Fast and
                # Slow, so it is basis-invariant by construction.
                "changes_band_cache_identity": tuple(key[1:]) != default_identity,
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "control_sensitivity.csv", index=False)

    # -------------------------------------------------------------- timings
    def timed(label: str, stage: str, function) -> None:
        start = perf_counter()
        function()
        timings.append(
            {
                "layout": label,
                "stage": stage,
                "elapsed_ms": round((perf_counter() - start) * 1000.0, 2),
            }
        )

    app.cached_revenue_outlook_view.clear()
    app.cached_view_cone_band.clear()
    app.cached_revenue_outlook_total_path_figure.clear()
    app.cached_revenue_outlook_fan_figure.clear()

    timed(
        "shared", "selector metadata (pack load + signature)",
        lambda: (
            load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT),
            revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT),
        ),
    )
    key = uptake_key()
    timed("shared", "view (cold)", lambda: view_for(pack, signature, "Total NLTF revenue", key))
    view = view_for(pack, signature, "Total NLTF revenue", key)
    app.cached_view_cone_band.clear()
    timed(
        "shared", "VFM band construction",
        lambda: app.cached_view_cone_band(
            signature, "Total NLTF revenue", "june_year", FED, TRACES,
            sensitivity_key(), PED_BRIDGE_DEFAULT_MODE, tuple(key[1:]), pack,
        ),
    )
    app.cached_revenue_outlook_total_path_figure.clear()
    timed(
        "shared", "main Total path figure",
        lambda: app.cached_revenue_outlook_total_path_figure(
            signature, "Total NLTF revenue", "FY2030", "june_year", FED, TRACES,
            sensitivity_key(), PED_BRIDGE_DEFAULT_MODE, key,
            view["filtered_rows"], view["cone_band"],
        ),
    )
    fan_availability = app._pack_table(pack, "fan_availability")
    fan_band_rows = app._pack_table(pack, "fan_band_rows")
    app.cached_revenue_outlook_fan_figure.clear()
    timed(
        "before (fan rendered eagerly beside the chart)", "separate fan figure",
        lambda: app.cached_revenue_outlook_fan_figure(
            signature, "Total NLTF revenue", FED, FAN_SOURCE_AUTO,
            fan_band_rows, fan_availability, ("BEFU26", "MBU26"),
        ),
    )
    timings.append(
        {
            "layout": "after (fan behind an explicit request)",
            "stage": "separate fan figure",
            "elapsed_ms": 0.0,
        }
    )
    pd.DataFrame(timings).to_csv(OUT / "page_timings.csv", index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
