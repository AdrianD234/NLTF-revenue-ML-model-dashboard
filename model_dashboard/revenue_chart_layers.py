"""The unified Revenue Outlook chart-layer registry.

One catalogue describes every selectable layer - deterministic paths, the
structural VFM envelope, and the conditional modelled-uncertainty bands - so a
single "Show on chart" control can drive all of them and nothing can be
selectable in two contradictory places.

Three concepts share the chart and must stay visually and verbally distinct:

``path``
    A deterministic scenario or an observed series. No probability attached.
``structural_envelope``
    The MoT VFM Fast-Slow range. A pair of governed composition scenarios.
    **Not probabilistic**, and never described as an interval.
``uncertainty_band``
    The 50%/80% conditional model forecast-error bands. Probabilistic within
    their stated evidence, but CONDITIONAL: the rolling-origin evidence uses
    observed future drivers, so it excludes Treasury-driver forecast error.

Z-order is fixed by ``draw_rank``: the widest, palest thing first so nothing
buries a line.

    1  80% modelled uncertainty
    2  VFM Fast-Slow structural range
    3  50% modelled uncertainty
    4+ deterministic paths and official comparators
"""
from __future__ import annotations

import dataclasses
from typing import Any

__all__ = [
    "BAND_GROUP",
    "LAYER_KIND_BAND",
    "LAYER_KIND_ENVELOPE",
    "LAYER_KIND_PATH",
    "PATH_GROUP",
    "RevenueChartLayerSpec",
    "UNCERTAINTY_BAND_LAYERS",
    "VFM_ENVELOPE_LAYER_ID",
    "VFM_FAST_TRACE_NAME",
    "VFM_SLOW_TRACE_NAME",
    "band_layer_ids",
    "build_layer_catalogue",
    "default_layer_ids",
    "layer_label",
    "path_trace_names",
]

LAYER_KIND_PATH = "path"
LAYER_KIND_ENVELOPE = "structural_envelope"
LAYER_KIND_BAND = "uncertainty_band"

PATH_GROUP = "Path"
BAND_GROUP = "Band"

VFM_FAST_TRACE_NAME = "MoT VFM Fast uptake"
VFM_SLOW_TRACE_NAME = "MoT VFM Slow uptake"
VFM_ENVELOPE_LAYER_ID = "band_vfm_fast_slow_range"
BAND_50_LAYER_ID = "band_modelled_uncertainty_50"
BAND_80_LAYER_ID = "band_modelled_uncertainty_80"
UNCERTAINTY_BAND_LAYERS = (BAND_80_LAYER_ID, BAND_50_LAYER_ID)

# Colour-blind-conscious. The two modelled-uncertainty bands share one slate
# hue at different opacities so they read as inner/outer of ONE object; the VFM
# envelope keeps a distinct teal so it can never be mistaken for them.
BAND_80_FILL = "rgba(82, 92, 122, 0.13)"
BAND_50_FILL = "rgba(82, 92, 122, 0.26)"
BAND_BOUNDARY = {"color": "rgba(82, 92, 122, 0.45)", "width": 1.0, "dash": "solid"}
ENVELOPE_FILL = "rgba(0, 150, 160, 0.16)"
ENVELOPE_BOUNDARY = {"color": "rgba(0, 150, 160, 0.60)", "width": 1.2, "dash": "dot"}

NOT_PROBABILISTIC = (
    "Structural scenario range, not probabilistic: the pair of governed MoT VFM "
    "fleet-composition scenarios. Not a confidence, credible or prediction interval."
)
CONDITIONAL_BAND = (
    "Conditional model forecast-error band. The rolling-origin evidence uses "
    "observed future economic drivers, so it isolates model error and EXCLUDES "
    "Treasury-driver forecast uncertainty. Where historical errors are biased "
    "the Current point forecast may sit outside the inner 50% band."
)


@dataclasses.dataclass(frozen=True)
class RevenueChartLayerSpec:
    """One independently selectable thing on the Total path chart."""

    layer_id: str
    display_name: str
    group: str
    layer_kind: str
    draw_rank: int
    default_selected: bool
    probabilistic: bool
    interpretation: str
    trace_name: str = ""
    scenario_id: str = ""
    colour: str = ""
    fill: str = ""
    legend_rank: int = 1000
    requires_uncertainty_pack: bool = False

    @property
    def label(self) -> str:
        return f"{self.group} · {self.display_name}"


def layer_label(spec: RevenueChartLayerSpec) -> str:
    return spec.label


def _path_spec(
    trace_name: str,
    *,
    draw_rank: int,
    default_selected: bool,
    scenario_id: str = "",
    interpretation: str = "",
) -> RevenueChartLayerSpec:
    return RevenueChartLayerSpec(
        layer_id=f"path_{trace_name}",
        display_name=trace_name,
        group=PATH_GROUP,
        layer_kind=LAYER_KIND_PATH,
        draw_rank=draw_rank,
        default_selected=default_selected,
        probabilistic=False,
        interpretation=interpretation or "Deterministic scenario path.",
        trace_name=trace_name,
        scenario_id=scenario_id,
    )


def build_layer_catalogue(
    trace_options: list[str],
    *,
    default_trace_names: list[str],
    uncertainty_available: bool,
    envelope_available: bool,
) -> tuple[RevenueChartLayerSpec, ...]:
    """Every selectable layer, in draw order.

    ``trace_options`` comes from the runtime pack, so a vintage or conflict
    path that is not in this pack simply does not appear - the catalogue never
    offers something the data cannot draw.
    """
    specs: list[RevenueChartLayerSpec] = []

    # Bands first: they are drawn underneath everything.
    if uncertainty_available:
        specs.append(
            RevenueChartLayerSpec(
                layer_id=BAND_80_LAYER_ID,
                display_name="80% conditional modelled uncertainty",
                group=BAND_GROUP,
                layer_kind=LAYER_KIND_BAND,
                draw_rank=1,
                default_selected=True,
                probabilistic=True,
                interpretation=CONDITIONAL_BAND,
                fill=BAND_80_FILL,
                legend_rank=1200,
                requires_uncertainty_pack=True,
            )
        )
    if envelope_available:
        specs.append(
            RevenueChartLayerSpec(
                layer_id=VFM_ENVELOPE_LAYER_ID,
                display_name="MoT VFM fast–slow range",
                group=BAND_GROUP,
                layer_kind=LAYER_KIND_ENVELOPE,
                draw_rank=2,
                default_selected=False,
                probabilistic=False,
                interpretation=NOT_PROBABILISTIC,
                fill=ENVELOPE_FILL,
                legend_rank=1150,
            )
        )
    if uncertainty_available:
        specs.append(
            RevenueChartLayerSpec(
                layer_id=BAND_50_LAYER_ID,
                display_name="50% conditional modelled uncertainty",
                group=BAND_GROUP,
                layer_kind=LAYER_KIND_BAND,
                draw_rank=3,
                default_selected=True,
                probabilistic=True,
                interpretation=CONDITIONAL_BAND,
                fill=BAND_50_FILL,
                legend_rank=1100,
            )
        )

    # Paths, in the order they should be drawn above the shading.
    for offset, trace in enumerate(trace_options):
        specs.append(
            _path_spec(
                trace,
                draw_rank=10 + offset,
                default_selected=trace in default_trace_names,
                interpretation=(
                    "Deterministic MoT VFM fleet-composition scenario, running "
                    "to FY2050. It shares the governed Light RUC pool with "
                    "Current Base; the exact VFM202405 scenario shares allocate "
                    "that common pool into a different conventional/BEV/PHEV mix."
                    if trace in (VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME)
                    else "Deterministic scenario path."
                ),
            )
        )
    return tuple(sorted(specs, key=lambda spec: spec.draw_rank))


def default_layer_ids(catalogue: tuple[RevenueChartLayerSpec, ...]) -> list[str]:
    return [spec.layer_id for spec in catalogue if spec.default_selected]


def path_trace_names(
    catalogue: tuple[RevenueChartLayerSpec, ...], selected_layer_ids: list[str]
) -> list[str]:
    chosen = set(selected_layer_ids)
    return [
        spec.trace_name
        for spec in catalogue
        if spec.layer_kind == LAYER_KIND_PATH and spec.layer_id in chosen
    ]


def band_layer_ids(
    catalogue: tuple[RevenueChartLayerSpec, ...], selected_layer_ids: list[str]
) -> list[str]:
    chosen = set(selected_layer_ids)
    return [
        spec.layer_id
        for spec in catalogue
        if spec.layer_kind in (LAYER_KIND_BAND, LAYER_KIND_ENVELOPE)
        and spec.layer_id in chosen
    ]


def catalogue_frame(catalogue: tuple[RevenueChartLayerSpec, ...]) -> list[dict[str, Any]]:
    """Audit rows for the layer catalogue."""
    return [
        {
            "layer_id": spec.layer_id,
            "display_name": spec.display_name,
            "label": spec.label,
            "group": spec.group,
            "layer_kind": spec.layer_kind,
            "draw_rank": spec.draw_rank,
            "legend_rank": spec.legend_rank,
            "default_selected": spec.default_selected,
            "probabilistic": spec.probabilistic,
            "trace_name": spec.trace_name,
            "interpretation": spec.interpretation,
        }
        for spec in catalogue
    ]
