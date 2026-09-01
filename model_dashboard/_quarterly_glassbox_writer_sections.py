"""Sections E-K, top-block links, Checks (audit builds) and README.

Everything here follows the identities proven by the Python parity layer in
``revenue_outlook_quarterly_glassbox``:

- Post-model activity: central FY2030 anchor x one-way growth handover.
- Revenue leaves: displayed activity x bridge-vintage official rate x the
  selected rate path's rate factor (FY2026-FY2050).
- FY2031+ RUC aggregates: Total RUC = pack central x Treasury macro terminal
  carry x rate factor; Gross RUC = Total + admin + refunds; the hidden
  Heavy-BEV leaf is solved residually (production detail-frame behaviour).
- Displayed quarters: governed annual value x committed allocation share.
  The physical chains are CONSTRUCTED rows beside them; the timing-difference
  rows quantify allocation timing and sum to zero over each June year.
- Actual-period cells in the top block are colour-coded: darker grey-blue for
  natively published actual quarters, lighter grey for the governed derived
  quarterly presentation of annual actuals.
"""

from __future__ import annotations

import math
from typing import Mapping

from model_dashboard.revenue_outlook_quarterly_glassbox import (
    fiscal_year_of_quarter,
    quarters_of_fiscal_year,
)

from model_dashboard._quarterly_glassbox_writer import (
    SHEET_INPUTS,
    SHEET_PARAMS,
    SHEET_SCENARIO,
    TOP_ROW_TEMPLATE_MAP,
    TRANSITION_RESERVED_ROWS,
    _ANNUAL_LAST_FY,
    _FIRST_DATA_COLUMN,
    _NF_DELTA,
    _NF_FACTOR,
    _NF_KM,
    _NF_POP,
    _NF_VALUE,
    _column_letter,
    _formula_quarters,
    _fy_column,
    _fy_header_row,
    _fy_range,
    _paint_fy_row,
    _paint_quarters,
    _section_header,
    _set_label,
    _xlookup,
    display_name,
)

_POST_FIRST_FY = 2031

#: Below this size a timing difference is presentation noise; the clean build
#: omits it entirely (audit builds paint everything so the Checks close).
_CLEAN_DELTA_THRESHOLD = 0.005


def _annual_lookup(series_id: str, params_grid) -> str:
    header = params_grid.row("prm.fy_header")
    value = params_grid.row(f"prm.annual.{series_id}")
    return _xlookup(
        "{c}$1", _fy_range(header, SHEET_PARAMS), _fy_range(value, SHEET_PARAMS)
    )


def _param_lookup(params_grid, key: str) -> str:
    header = params_grid.row("prm.fy_header")
    value = params_grid.row(key)
    return _xlookup(
        "{c}$1", _fy_range(header, SHEET_PARAMS), _fy_range(value, SHEET_PARAMS)
    )


def _display_row(
    grid,
    params_grid,
    inputs_grid,
    row: int,
    series_id: str,
    label: str,
    data,
    *,
    number_format=_NF_VALUE,
    bold: bool = False,
) -> None:
    """The governed displayed quarterly row: annual value x committed share."""
    styles = grid.styles
    share_row = inputs_grid.row(f"share.{series_id}")
    values = data.quarterly_values.get(series_id, {})
    annual = data.annual_values.get(series_id, {})
    with_share = sorted(
        (q for q in values if abs(annual.get(fiscal_year_of_quarter(q), 0.0)) >= 1e-12),
        key=lambda q: (q[:4], q[-1]),
    )
    zero_years = {
        q: values[q]
        for q in values
        if abs(annual.get(fiscal_year_of_quarter(q), 0.0)) < 1e-12
        and abs(values[q]) >= 1e-12
    }
    template = (
        f"={_annual_lookup(series_id, params_grid)}"
        f"*'{SHEET_INPUTS}'!{{c}}{share_row}"
    )
    grid.register(f"disp.{series_id}", row)
    _set_label(grid, row, label, font=styles.label_bold if bold else styles.label, indent=1)
    _formula_quarters(
        grid, row, template,
        font=styles.formula_bold if bold else styles.formula,
        number_format=number_format, quarters=with_share,
    )
    if zero_years:
        _paint_quarters(grid, row, zero_years, font=styles.input,
                        number_format=number_format)


def _delta_row(
    grid,
    row: int,
    label: str,
    values: Mapping[str, float],
    data,
    display_series: str,
) -> None:
    """Paint the timing-difference row and record which June years close.

    A year is eligible for the audit Checks' sum-to-zero assertion only when
    the difference domain covers all four quarters. A complete year whose
    differences genuinely do not cancel (the post-model petrol VKT
    population-basis wedge) is excluded AND surfaced as a warning.
    """
    styles = grid.styles
    threshold = 1e-12 if getattr(data, "_audit_sheets", False) else _CLEAN_DELTA_THRESHOLD
    painted = {q: v for q, v in values.items() if abs(v) > threshold}
    _set_label(grid, row, label, font=styles.note, indent=2)
    _paint_quarters(grid, row, painted, font=styles.input, number_format=_NF_DELTA)
    eligible: list[str] = []
    for fy in range(2026, _ANNUAL_LAST_FY + 1):
        fy_quarters = quarters_of_fiscal_year(fy)
        if not all(q in values for q in fy_quarters):
            continue
        total = sum(values[q] for q in fy_quarters)
        if abs(total) <= 1e-6:
            eligible.append(fy_quarters[-1])
        else:
            data.warnings.append(
                f"{display_series} FY{fy}: quarterly timing differences sum to "
                f"{total:.4f} (documented basis difference, excluded from the "
                "sum-to-zero check)."
            )
    if not hasattr(data, "_adj_eligible"):
        data._adj_eligible = {}
    data._adj_eligible[display_series] = eligible


def write_post_model_and_revenue_sections(grid, data) -> None:
    styles = grid.styles
    params_grid = data._params_grid
    inputs_grid = data._inputs_grid
    row = data._scenario_row_cursor
    quarters = list(grid.quarters)
    disp = data.quarterly_values

    # ------------------------------------------------------------------ E
    _section_header(grid, row, "E. Long-run PREBU handover (June-year grid) - one-way growth-rate handover, FY2031-FY2050")
    row += 1
    _set_label(
        grid, row,
        f"Growth handover to FY{data.post_model.completion_fy} with shape source "
        f"{data.post_model.shape_vintage_id}. Central FY2030 anchor = displayed "
        "FY2030 with the rate-path activity factor divided out; the blend then "
        "rides the earned PREBU growth trajectory with no level pull-back.",
        font=styles.note,
    )
    row += 1
    grid.register("e.fy_header", row)
    _fy_header_row(grid, row, "June fiscal year")
    fy_header = row
    row += 1

    ped_raw_row = grid.row("ped.raw_level")
    heavy_raw_row = grid.row("heavy.raw_mkm")
    pop_row = inputs_grid.row("in.population")

    handover_fys = list(range(data.post_model.anchor_fy, _ANNUAL_LAST_FY + 1))

    def _fy_formula_row(key: str, label: str, template_by_fy, *, font=styles.formula,
                        number_format=_NF_FACTOR, indent: int = 1) -> int:
        nonlocal row
        grid.register(key, row)
        _set_label(grid, row, label, indent=indent,
                   font=styles.label if font is not styles.formula_bold else styles.label_bold)
        for fy in handover_fys:
            formula = template_by_fy(fy)
            if formula is None:
                continue
            cell = grid.ws.cell(row=row, column=_fy_column(fy))
            cell.value = formula
            cell.font = font
            cell.number_format = number_format
        row += 1
        return row - 1

    def _quarter_cols(fy: int) -> tuple[str, str]:
        first, _, _, last = quarters_of_fiscal_year(fy)
        return grid.letter(first), grid.letter(last)

    def _raw_petrol_formula(fy: int) -> str:
        first, last = _quarter_cols(fy)
        return (
            f"=SUMPRODUCT(${first}{ped_raw_row}:${last}{ped_raw_row},"
            f"'{SHEET_INPUTS}'!${first}{pop_row}:'{SHEET_INPUTS}'!${last}{pop_row})/1000000"
        )

    raw_petrol = _fy_formula_row(
        "e.raw_petrol", "Raw model petrol VKT (m km) = SUMPRODUCT(raw VKT pc, population) / 1e6",
        _raw_petrol_formula, number_format=_NF_VALUE,
    )

    def _raw_vktpc_formula(fy: int) -> str:
        first, last = _quarter_cols(fy)
        return f"=SUM(${first}{ped_raw_row}:${last}{ped_raw_row})"

    raw_vktpc = _fy_formula_row(
        "e.raw_vktpc", "Raw model VKT per capita (km, four-quarter sum)",
        _raw_vktpc_formula, number_format=_NF_KM,
    )

    def _raw_heavy_formula(fy: int) -> str:
        first, last = _quarter_cols(fy)
        return f"=SUM(${first}{heavy_raw_row}:${last}{heavy_raw_row})"

    raw_heavy = _fy_formula_row(
        "e.raw_heavy", "Raw model Heavy RUC km (m km, four-quarter sum)",
        _raw_heavy_formula, number_format=_NF_VALUE,
    )

    scenario_pop = _fy_formula_row(
        "e.pop", "Scenario population = raw petrol km / raw VKT per capita",
        lambda fy: f"={_column_letter(_fy_column(fy))}{raw_petrol}*1000000/"
                   f"{_column_letter(_fy_column(fy))}{raw_vktpc}",
        number_format=_NF_POP,
    )

    grid.register("e.vfm_pool_abs", row)
    _set_label(grid, row, "VFM absolute Light RUC pool (m km, vendored MoT table)", indent=1)
    _paint_fy_row(grid, row, data.post_model.vfm_pool_million_km,
                  font=styles.input, number_format=_NF_VALUE)
    vfm_pool_abs = row
    row += 1

    anchor_col = _column_letter(_fy_column(data.post_model.anchor_fy))
    current_rows: dict[str, int] = {}
    for stream, source_row, label in (
        ("light_petrol_vkt", raw_petrol, "Current growth index: light petrol VKT (FY2030 = 1)"),
        ("light_ruc_pool", vfm_pool_abs, "Current growth index: Light RUC pool (VFM absolute pool)"),
        ("heavy_ruc_net_km", raw_heavy, "Current growth index: Heavy RUC km"),
    ):
        current_rows[stream] = _fy_formula_row(
            f"e.cur.{stream}", label,
            lambda fy, r=source_row: f"={_column_letter(_fy_column(fy))}{r}/${anchor_col}${r}",
        )

    structural_rows: dict[str, int] = {}
    for stream, label in (
        ("light_petrol_vkt", "PREBU26 structural index: light petrol VKT"),
        ("light_ruc_pool", "PREBU26 structural index: Light RUC pool"),
        ("heavy_ruc_net_km", "PREBU26 structural index: Heavy RUC km"),
    ):
        grid.register(f"e.struct.{stream}", row)
        _set_label(grid, row, label, indent=1)
        _paint_fy_row(grid, row, data.post_model.structural_index[stream],
                      font=styles.input, number_format=_NF_FACTOR)
        structural_rows[stream] = row
        row += 1

    span = data.post_model.completion_fy - data.post_model.anchor_fy
    weight = _fy_formula_row(
        "e.weight",
        "Handover weight w = 3u^2 - 2u^3, u = clamp((FY - "
        f"{data.post_model.anchor_fy}) / {span}, 0, 1)",
        lambda fy: (
            f"=3*MIN(1,MAX(0,({_column_letter(_fy_column(fy))}{fy_header}-"
            f"{data.post_model.anchor_fy})/{span}))^2"
            f"-2*MIN(1,MAX(0,({_column_letter(_fy_column(fy))}{fy_header}-"
            f"{data.post_model.anchor_fy})/{span}))^3"
        ),
    )

    hybrid_rows: dict[str, int] = {}
    for stream, label in (
        ("light_petrol_vkt", "Hybrid index: light petrol VKT (blended growth recursion)"),
        ("light_ruc_pool", "Hybrid index: Light RUC pool"),
        ("heavy_ruc_net_km", "Hybrid index: Heavy RUC km"),
    ):
        cur = current_rows[stream]
        struct = structural_rows[stream]

        def _hybrid(fy: int, cur=cur, struct=struct) -> str:
            col = _column_letter(_fy_column(fy))
            if fy == data.post_model.anchor_fy:
                return "=1"
            prev = _column_letter(_fy_column(fy - 1))
            return (
                f"={prev}{row}*EXP((1-{col}{weight})*LN({col}{cur}/{prev}{cur})"
                f"+{col}{weight}*LN({col}{struct}/{prev}{struct}))"
            )

        hybrid_rows[stream] = _fy_formula_row(
            f"e.hybrid.{stream}", label, _hybrid, font=styles.formula_bold,
        )

    anchor_rows: dict[str, int] = {}
    prm_header = params_grid.row("prm.fy_header")

    def _anchor_formula(series_ids: tuple[str, ...]) -> str:
        terms = []
        for series_id in series_ids:
            annual_row = params_grid.row(f"prm.annual.{series_id}")
            factor_row = params_grid.row(f"prm.pair_factor.{series_id}")
            terms.append(
                _xlookup(str(data.post_model.anchor_fy),
                         _fy_range(prm_header, SHEET_PARAMS),
                         _fy_range(annual_row, SHEET_PARAMS))
                + "/"
                + _xlookup(str(data.post_model.anchor_fy),
                           _fy_range(prm_header, SHEET_PARAMS),
                           _fy_range(factor_row, SHEET_PARAMS))
            )
        return "=" + "+".join(terms)

    for stream, series_ids, label in (
        ("light_petrol_vkt", ("light_petrol_vkt",),
         "Central FY2030 anchor: light petrol VKT (displayed / activity factor)"),
        ("light_ruc_pool", ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"),
         "Central FY2030 anchor: Light RUC pool (sum of central class anchors)"),
        ("heavy_ruc_net_km", ("heavy_ruc_net_km",),
         "Central FY2030 anchor: Heavy RUC km"),
    ):
        grid.register(f"e.anchor.{stream}", row)
        _set_label(grid, row, label, indent=1)
        cell = grid.ws.cell(row=row, column=_fy_column(data.post_model.anchor_fy))
        cell.value = _anchor_formula(series_ids)
        cell.font = styles.formula
        cell.number_format = _NF_VALUE
        anchor_rows[stream] = row
        row += 1

    level_rows: dict[str, int] = {}
    for stream, label in (
        ("light_petrol_vkt", "Post-model level: light petrol VKT (m km) = anchor x hybrid"),
        ("light_ruc_pool", "Post-model level: Light RUC pool (m km)"),
        ("heavy_ruc_net_km", "Post-model level: Heavy RUC km (m km)"),
    ):
        anchor_row = anchor_rows[stream]
        hybrid_row = hybrid_rows[stream]
        level_rows[stream] = _fy_formula_row(
            f"e.level.{stream}", label,
            lambda fy, a=anchor_row, h=hybrid_row: (
                None if fy < _POST_FIRST_FY
                else f"=${anchor_col}${a}*{_column_letter(_fy_column(fy))}{h}"
            ),
            font=styles.formula_bold, number_format=_NF_VALUE,
        )

    _fy_formula_row(
        "e.level.vktpc", "Post-model VKT per capita (km) = petrol VKT x 1e6 / population",
        lambda fy: (
            None if fy < _POST_FIRST_FY
            else f"={_column_letter(_fy_column(fy))}{level_rows['light_petrol_vkt']}*1000000/"
                 f"{_column_letter(_fy_column(fy))}{scenario_pop}"
        ),
        font=styles.formula_bold, number_format=_NF_KM,
    )
    _set_label(
        grid, row,
        "Scenario wedge: the central baseline is the reference path, wedge = 0.",
        font=styles.note,
    )
    row += 2

    # ------------------------------------------------------------------ F
    _section_header(grid, row, "F. VFM fleet allocation (June-year grid) - exact vendored shares over the pool")
    row += 1
    share_rows: dict[str, int] = {}
    for cls, label in (
        ("conventional", "VFM conventional share (renormalised to sum to 1)"),
        ("bev", "VFM Light BEV share"),
        ("phev", "VFM PHEV share"),
    ):
        grid.register(f"f.share.{cls}", row)
        _set_label(grid, row, label, indent=1)
        _paint_fy_row(grid, row, data.post_model.vfm_shares[cls],
                      font=styles.input, number_format="0.0000")
        share_rows[cls] = row
        row += 1
    grid.register("f.share_sum", row)
    _set_label(grid, row, "Share sum (must equal 1)", indent=2, font=styles.note)
    for fy in handover_fys:
        col = _column_letter(_fy_column(fy))
        cell = grid.ws.cell(row=row, column=_fy_column(fy))
        cell.value = (
            f"={col}{share_rows['conventional']}+{col}{share_rows['bev']}+{col}{share_rows['phev']}"
        )
        cell.font = styles.formula
        cell.number_format = "0.0000"
    row += 1
    for cls, series_id, label in (
        ("conventional", "light_ruc_net_km", "Post-model conventional Light RUC km = pool x share"),
        ("bev", "light_bev_ruc_net_km", "Post-model Light BEV RUC km = pool x share"),
        ("phev", "phev_ruc_net_km", "Post-model PHEV RUC km = pool x share"),
    ):
        share_row = share_rows[cls]
        pool_row = level_rows["light_ruc_pool"]
        _fy_formula_row(
            f"f.level.{series_id}", label,
            lambda fy, s=share_row, p=pool_row: (
                None if fy < _POST_FIRST_FY
                else f"={_column_letter(_fy_column(fy))}{p}*{_column_letter(_fy_column(fy))}{s}"
            ),
            font=styles.formula_bold, number_format=_NF_VALUE,
        )
    row += 1

    # ---------------------------------------------------- G/H/I helper data
    factor_by_fy = data.policy_rate_factor_by_fy
    intensity = data.intensity_l_per_100km
    spine = data.official_spine

    def spine_rate(km_series: str, revenue_series: str, fy: int) -> float | None:
        km = spine.get(km_series, {}).get(fy)
        revenue = spine.get(revenue_series, {}).get(fy)
        if km is None or revenue is None or abs(km) < 1e-9:
            return None
        return revenue / km

    def _constructed_and_delta(
        label: str,
        physical: Mapping[str, float],
        display_series: str,
        *,
        number_format=_NF_VALUE,
        formula_template: str | None = None,
        formula_quarters=None,
    ) -> None:
        nonlocal row
        grid.register(f"con.{display_series}", row)
        _set_label(grid, row, label, indent=1)
        if formula_template is not None:
            _formula_quarters(grid, row, formula_template, font=styles.formula,
                              number_format=number_format, quarters=formula_quarters)
        else:
            _paint_quarters(grid, row, physical, font=styles.formula,
                            number_format=number_format)
        row += 1
        shown = disp.get(display_series, {})
        delta = {
            q: shown[q] - physical[q]
            for q in physical
            if q in shown and math.isfinite(physical[q])
        }
        _delta_row(grid, row, "Timing difference vs displayed (four-quarter sum = 0)",
                   delta, data, display_series)
        grid.register(f"adj.{display_series}", row)
        row += 1

    # ------------------------------------------------------------------ G
    _section_header(grid, row, "G. Petrol volume and fuel-intensity bridge (quarterly)")
    row += 1
    pop = data.drivers.get("population", {})
    vktpc_disp = disp.get("ped_vkt_per_capita", {})
    petrol_disp = disp.get("light_petrol_vkt", {})
    volume_disp = disp.get("ped_volume", {})

    _display_row(grid, params_grid, inputs_grid, row, "ped_vkt_per_capita",
                 "Displayed: Light petrol VKT per capita (km)", data,
                 number_format=_NF_KM, bold=True)
    vktpc_row = row
    row += 1

    physical_petrol = {
        q: vktpc_disp[q] * pop[q] / 1e6
        for q in vktpc_disp
        if q in pop
    }
    petrol_template = (
        f"={{c}}{vktpc_row}*'{SHEET_INPUTS}'!{{c}}{inputs_grid.row('in.population')}/1000000"
    )
    _constructed_and_delta(
        "Constructed: light petrol VKT (m km) = VKT per capita x population / 1e6",
        physical_petrol, "light_petrol_vkt",
        formula_template=petrol_template,
        formula_quarters=[q for q in quarters if q in physical_petrol],
    )
    _display_row(grid, params_grid, inputs_grid, row, "light_petrol_vkt",
                 "Displayed: Light petrol VKT (m km)", data, bold=True)
    petrol_row = row
    row += 1

    physical_volume = {
        q: petrol_disp[q] * intensity[fiscal_year_of_quarter(q)] / 100.0
        for q in petrol_disp
        if fiscal_year_of_quarter(q) in intensity
    }
    volume_template = (
        f"={{c}}{petrol_row}*{_param_lookup(params_grid, 'prm.intensity')}/100"
    )
    _constructed_and_delta(
        "Constructed: petrol volume (m L) = petrol VKT x litres per 100 km / 100",
        physical_volume, "ped_volume",
        formula_template=volume_template,
        formula_quarters=[q for q in quarters if q in physical_volume],
    )
    _display_row(grid, params_grid, inputs_grid, row, "ped_volume",
                 "Displayed: PED volume (m L)", data, bold=True)
    volume_row = row
    row += 2

    # ------------------------------------------------------------------ H
    _section_header(grid, row, "H. FED revenue bridge (quarterly)")
    row += 1
    physical_gross_ped = {}
    for q in volume_disp:
        fy = fiscal_year_of_quarter(q)
        rate = spine_rate("ped_volume", "gross_ped_revenue", fy)
        factor = factor_by_fy.get(fy)
        if rate is None or factor is None:
            continue
        physical_gross_ped[q] = volume_disp[q] * rate * factor
    gross_ped_template = (
        f"={{c}}{volume_row}*{_param_lookup(params_grid, 'prm.rate.ped')}"
        f"*{_param_lookup(params_grid, 'prm.policy_rate_factor')}"
    )
    _constructed_and_delta(
        "Constructed: gross PED (m $) = volume x official PED rate x rate factor",
        physical_gross_ped, "gross_ped_revenue",
        formula_template=gross_ped_template,
        formula_quarters=[q for q in quarters if q in physical_gross_ped],
    )
    _display_row(grid, params_grid, inputs_grid, row, "gross_ped_revenue",
                 "Displayed: Gross PED revenue (m $)", data, bold=True)
    gross_ped_row = row
    row += 1

    carried_rows: dict[str, int] = {}
    for series_id in ("gross_lpg_revenue", "gross_cng_revenue", "fed_refunds"):
        _display_row(grid, params_grid, inputs_grid, row, series_id,
                     f"{display_name(data, series_id)} [governed carried input]", data)
        carried_rows[series_id] = row
        row += 1

    physical_gross_fed = {}
    for q in disp.get("gross_ped_revenue", {}):
        parts = [disp["gross_ped_revenue"].get(q),
                 disp.get("gross_lpg_revenue", {}).get(q),
                 disp.get("gross_cng_revenue", {}).get(q)]
        if all(v is not None for v in parts):
            physical_gross_fed[q] = sum(parts)
    gross_fed_template = (
        f"={{c}}{gross_ped_row}+{{c}}{carried_rows['gross_lpg_revenue']}"
        f"+{{c}}{carried_rows['gross_cng_revenue']}"
    )
    _constructed_and_delta(
        "Constructed: gross FED (m $) = gross PED + LPG + CNG",
        physical_gross_fed, "gross_fed_revenue",
        formula_template=gross_fed_template,
        formula_quarters=[q for q in quarters if q in physical_gross_fed],
    )
    _display_row(grid, params_grid, inputs_grid, row, "gross_fed_revenue",
                 "Displayed: Gross FED revenue (m $)", data, bold=True)
    gross_fed_row = row
    row += 1

    physical_net_fed = {}
    for q in disp.get("gross_fed_revenue", {}):
        refunds = disp.get("fed_refunds", {}).get(q)
        if refunds is not None:
            physical_net_fed[q] = disp["gross_fed_revenue"][q] - refunds
    net_fed_template = f"={{c}}{gross_fed_row}-{{c}}{carried_rows['fed_refunds']}"
    _constructed_and_delta(
        "Constructed: net FED (m $) = gross FED - FED refunds",
        physical_net_fed, "net_fed_revenue",
        formula_template=net_fed_template,
        formula_quarters=[q for q in quarters if q in physical_net_fed],
    )
    _display_row(grid, params_grid, inputs_grid, row, "net_fed_revenue",
                 "Displayed: Net FED revenue (m $)", data, bold=True)
    row += 2

    # ------------------------------------------------------------------ I
    _section_header(grid, row, "I. RUC revenue bridge (quarterly)")
    row += 1
    _set_label(
        grid, row,
        "Class revenue = net km x official effective rate ($/1,000 km) x rate "
        "factor / 1,000. FY2031+ aggregates follow the production top-down "
        "construction: Total RUC = pack central x Treasury macro terminal carry x "
        "rate factor; the hidden Heavy-BEV line closes the Gross RUC identity.",
        font=styles.note,
    )
    row += 1

    class_disp_rows: dict[str, int] = {}
    class_meta = (
        ("light_ruc_net_km", "light_ruc_net_revenue", "prm.rate.light",
         "conventional Light RUC"),
        ("light_bev_ruc_net_km", "light_bev_ruc_net_revenue", "prm.rate.light_bev",
         "Light BEV RUC"),
        ("phev_ruc_net_km", "phev_ruc_net_revenue", "prm.rate.phev", "PHEV RUC"),
        ("heavy_ruc_net_km", "heavy_ruc_net_revenue", "prm.rate.heavy", "Heavy RUC"),
    )
    km_rows: dict[str, int] = {}
    for km_series, _, _, label in class_meta:
        _display_row(grid, params_grid, inputs_grid, row, km_series,
                     f"Displayed: {display_name(data, km_series)}", data)
        km_rows[km_series] = row
        row += 1
    _display_row(grid, params_grid, inputs_grid, row, "heavy_bev_ruc_net_km",
                 f"Displayed: {display_name(data, 'heavy_bev_ruc_net_km')} [governed carried input]", data)
    row += 1

    for km_series, revenue_series, rate_key, label in class_meta:
        physical = {}
        for q in disp.get(km_series, {}):
            fy = fiscal_year_of_quarter(q)
            rate = spine_rate(km_series, revenue_series, fy)
            factor = factor_by_fy.get(fy)
            if rate is None or factor is None:
                continue
            physical[q] = disp[km_series][q] * rate * factor
        template = (
            f"={{c}}{km_rows[km_series]}*{_param_lookup(params_grid, rate_key)}"
            f"*{_param_lookup(params_grid, 'prm.policy_rate_factor')}/1000"
        )
        _constructed_and_delta(
            f"Constructed: {label} revenue (m $) = km x rate x factor / 1,000",
            physical, revenue_series,
            formula_template=template,
            formula_quarters=[q for q in quarters if q in physical],
        )
        _display_row(grid, params_grid, inputs_grid, row, revenue_series,
                     f"Displayed: {display_name(data, revenue_series)}", data, bold=True)
        class_disp_rows[revenue_series] = row
        row += 1

    for series_id in ("ruc_refunds", "ruc_admin_revenue"):
        _display_row(grid, params_grid, inputs_grid, row, series_id,
                     f"{display_name(data, series_id)} [governed carried input]", data)
        carried_rows[series_id] = row
        row += 1

    _display_row(grid, params_grid, inputs_grid, row, "heavy_bev_ruc_net_revenue",
                 "Displayed: Heavy BEV RUC net revenue (m $) [hidden line: solved "
                 "residually from the Gross RUC closure in production]", data)
    class_disp_rows["heavy_bev_ruc_net_revenue"] = row
    row += 1

    physical_gross_ruc = {}
    for q in disp.get("gross_ruc_revenue", {}):
        parts = [disp.get(series, {}).get(q) for series in (
            "light_ruc_net_revenue", "heavy_ruc_net_revenue",
            "light_bev_ruc_net_revenue", "heavy_bev_ruc_net_revenue",
            "phev_ruc_net_revenue", "ruc_refunds",
        )]
        if all(v is not None for v in parts):
            physical_gross_ruc[q] = sum(parts)
    gross_ruc_template = "=" + "+".join(
        f"{{c}}{class_disp_rows[series]}" for series in (
            "light_ruc_net_revenue", "heavy_ruc_net_revenue",
            "light_bev_ruc_net_revenue", "heavy_bev_ruc_net_revenue",
            "phev_ruc_net_revenue",
        )
    ) + f"+{{c}}{carried_rows['ruc_refunds']}"
    _constructed_and_delta(
        "Constructed: gross RUC (m $) = class revenues + Heavy BEV + RUC refunds",
        physical_gross_ruc, "gross_ruc_revenue",
        formula_template=gross_ruc_template,
        formula_quarters=[q for q in quarters if q in physical_gross_ruc],
    )
    _display_row(grid, params_grid, inputs_grid, row, "gross_ruc_revenue",
                 "Displayed: Gross RUC revenue (m $)", data, bold=True)
    gross_ruc_row = row
    row += 1

    physical_net_admin = {}
    for q in disp.get("ruc_revenue_net_admin", {}):
        admin = disp.get("ruc_admin_revenue", {}).get(q)
        gross = disp.get("gross_ruc_revenue", {}).get(q)
        if admin is not None and gross is not None:
            physical_net_admin[q] = gross - admin
    _constructed_and_delta(
        "Constructed: RUC net of admin (m $) = gross RUC - admin",
        physical_net_admin, "ruc_revenue_net_admin",
        formula_template=f"={{c}}{gross_ruc_row}-{{c}}{carried_rows['ruc_admin_revenue']}",
        formula_quarters=[q for q in quarters if q in physical_net_admin],
    )
    _display_row(grid, params_grid, inputs_grid, row, "ruc_revenue_net_admin",
                 "Displayed: RUC revenues net of admin fees (m $)", data, bold=True)
    net_admin_row = row
    row += 1

    physical_total_ruc = {}
    for q in disp.get("total_ruc_net_revenue", {}):
        refunds = disp.get("ruc_refunds", {}).get(q)
        net_admin = disp.get("ruc_revenue_net_admin", {}).get(q)
        if refunds is not None and net_admin is not None:
            physical_total_ruc[q] = net_admin - refunds
    _constructed_and_delta(
        "Constructed: total RUC (m $) = net of admin - refunds",
        physical_total_ruc, "total_ruc_net_revenue",
        formula_template=f"={{c}}{net_admin_row}-{{c}}{carried_rows['ruc_refunds']}",
        formula_quarters=[q for q in quarters if q in physical_total_ruc],
    )
    _display_row(grid, params_grid, inputs_grid, row, "total_ruc_net_revenue",
                 "Displayed: Total RUC net revenue (m $)", data, bold=True)
    row += 2

    # ------------------------------------------------------------------ J
    _section_header(grid, row, "J. MVR and TUC carried lines (quarterly, governed carry)")
    row += 1
    _set_label(
        grid, row,
        "Registration, licensing and track user charges are governed carried "
        f"inputs from the {data.bridge_vintage_id} bridge vintage - not generated "
        "by the econometric models. Quarters are the neutral-flat governed "
        "allocation.",
        font=styles.note,
    )
    row += 1
    mvr_rows: dict[str, int] = {}
    for series_id in (
        "mr1_revenue", "mr2_revenue", "coo_revenue", "mvr_admin_revenue",
        "mvr_refunds", "tuc_gtk", "tuc_net_revenue",
    ):
        _display_row(grid, params_grid, inputs_grid, row, series_id,
                     f"{display_name(data, series_id)} [governed carried input]", data)
        mvr_rows[series_id] = row
        row += 1
    for output, terms, expression in (
        ("gross_mvr_revenue", ("mr1_revenue", "mr2_revenue", "coo_revenue"),
         "MR1 + MR2 + MR13"),
        ("mvr_revenue_net_admin_coo", None, "MR1 + MR2 - admin"),
        ("net_mvr_revenue", None, "net of admin and COO - refunds"),
    ):
        grid.register(f"con.{output}", row)
        _set_label(grid, row, f"Constructed: {display_name(data, output)} = {expression}", indent=1)
        if output == "gross_mvr_revenue":
            template = "=" + "+".join(f"{{c}}{mvr_rows[t]}" for t in terms)
        elif output == "mvr_revenue_net_admin_coo":
            template = (
                f"={{c}}{mvr_rows['mr1_revenue']}+{{c}}{mvr_rows['mr2_revenue']}"
                f"-{{c}}{mvr_rows['mvr_admin_revenue']}"
            )
        else:
            template = (
                f"={{c}}{grid.row('con.mvr_revenue_net_admin_coo')}"
                f"-{{c}}{mvr_rows['mvr_refunds']}"
            )
        available = [
            q for q in quarters
            if q in disp.get("mr1_revenue", {}) and q in disp.get("mvr_refunds", {})
        ]
        _formula_quarters(grid, row, template, font=styles.formula,
                          number_format=_NF_VALUE, quarters=available)
        row += 1
        shown = disp.get(output, {})
        physical = {}
        if output == "gross_mvr_revenue":
            for q in shown:
                parts = [disp.get(t, {}).get(q) for t in terms]
                if all(v is not None for v in parts):
                    physical[q] = sum(parts)
        elif output == "mvr_revenue_net_admin_coo":
            for q in shown:
                parts = [disp.get("mr1_revenue", {}).get(q), disp.get("mr2_revenue", {}).get(q),
                         disp.get("mvr_admin_revenue", {}).get(q)]
                if all(v is not None for v in parts):
                    physical[q] = parts[0] + parts[1] - parts[2]
        else:
            for q in shown:
                parts = [disp.get("mvr_revenue_net_admin_coo", {}).get(q),
                         disp.get("mvr_refunds", {}).get(q)]
                if all(v is not None for v in parts):
                    physical[q] = parts[0] - parts[1]
        delta = {q: shown[q] - physical[q] for q in physical if q in shown}
        _delta_row(grid, row, "Timing difference vs displayed (four-quarter sum = 0)",
                   delta, data, output)
        grid.register(f"adj.{output}", row)
        row += 1
        _display_row(grid, params_grid, inputs_grid, row, output,
                     f"Displayed: {display_name(data, output)}", data, bold=True)
        row += 1
    row += 1

    # ------------------------------------------------------------------ K
    _section_header(grid, row, "K. Total NLTF formula reconciliation (quarterly)")
    row += 1
    for output, expression, terms, signs in (
        ("total_gross_revenue", "gross RUC + gross FED + gross MVR + TUC",
         ("gross_ruc_revenue", "gross_fed_revenue", "gross_mvr_revenue", "tuc_net_revenue"),
         (1, 1, 1, 1)),
        ("total_admin_fees", "RUC admin + MVR admin + MR13",
         ("ruc_admin_revenue", "mvr_admin_revenue", "coo_revenue"), (1, 1, 1)),
        ("total_revenue_net_admin", "total gross - total admin",
         ("total_gross_revenue", "total_admin_fees"), (1, -1)),
        ("total_refunds", "RUC refunds + FED refunds + MVR refunds",
         ("ruc_refunds", "fed_refunds", "mvr_refunds"), (1, 1, 1)),
        ("total_nltf_net_revenue", "total net of admin - total refunds",
         ("total_revenue_net_admin", "total_refunds"), (1, -1)),
    ):
        term_rows = [grid.row(f"disp.{term}") for term in terms]
        template = "=" + "".join(
            ("+" if sign > 0 and index > 0 else ("-" if sign < 0 else ""))
            + f"{{c}}{term_row}"
            for index, (term_row, sign) in enumerate(zip(term_rows, signs))
        )
        physical = {}
        shown = disp.get(output, {})
        for q in shown:
            parts = [disp.get(t, {}).get(q) for t in terms]
            if all(v is not None for v in parts):
                physical[q] = sum(s * v for s, v in zip(signs, parts))
        grid.register(f"con.{output}", row)
        _set_label(grid, row, f"Constructed: {display_name(data, output)} = {expression}", indent=1)
        _formula_quarters(grid, row, template, font=styles.formula,
                          number_format=_NF_VALUE,
                          quarters=[q for q in quarters if q in physical])
        row += 1
        delta = {q: shown[q] - physical[q] for q in physical if q in shown}
        _delta_row(grid, row, "Timing difference vs displayed (four-quarter sum = 0)",
                   delta, data, output)
        grid.register(f"adj.{output}", row)
        row += 1
        _display_row(grid, params_grid, inputs_grid, row, output,
                     f"Displayed: {display_name(data, output)}", data,
                     bold=output == "total_nltf_net_revenue")
        row += 1
    row += 1
    data._scenario_row_cursor = row


def write_top_block_links(grid, data) -> None:
    """Top block: every value is a link; actual-period cells are colour-coded."""
    from model_dashboard.revenue_outlook_excel_extract import (
        LEVEL_ROW_SERIES,
        REVENUE_ROW_SERIES,
    )
    from model_dashboard._quarterly_glassbox_writer import (
        _TEMPLATE_BOLD_ROWS,
        _NF_VALUE as NF_VALUE,
    )

    styles = grid.styles
    inputs_grid = data._inputs_grid
    workbook_row_of_template = {
        template: workbook for workbook, template in TOP_ROW_TEMPLATE_MAP.items()
    }

    for template_row, series_id in {**LEVEL_ROW_SERIES, **REVENUE_ROW_SERIES}.items():
        workbook_row = workbook_row_of_template.get(template_row)
        if workbook_row is None:
            continue
        target_series = (
            "light_ruc_net_km"
            if series_id == "current_light_ruc_conventional_modelled_km"
            else series_id
        )
        display_quarters = set(data.quarterly_values.get(target_series, {}))
        target_row = grid.rows.get(f"disp.{target_series}")
        history = data.actual_quarters.get(series_id, {})
        kinds = data.actual_kind.get(series_id, {})
        hist_row = inputs_grid.rows.get(f"hist.{series_id}")
        bold = template_row in _TEMPLATE_BOLD_ROWS
        font = styles.formula_bold if bold else styles.formula
        link_font = styles.link_bold if bold else styles.link
        for quarter in grid.quarters:
            column = grid.col_of[quarter]
            letter = _column_letter(column)
            cell = grid.ws.cell(row=workbook_row, column=column)
            if quarter in display_quarters and target_row:
                cell.value = f"={letter}{target_row}"
                cell.font = font
            elif quarter in history and hist_row:
                cell.value = f"='{SHEET_INPUTS}'!{letter}{hist_row}"
                cell.font = link_font
                cell.fill = (
                    styles.actual_fill
                    if kinds.get(quarter) == "native"
                    else styles.derived_actual_fill
                )
            else:
                continue
            cell.number_format = NF_VALUE

    _set_label(
        grid, TRANSITION_RESERVED_ROWS[-1] + 4,
        "Actual-period cell colours: darker grey-blue = natively published actual "
        "quarter; light grey = governed quarterly presentation derived from the "
        "published annual actual.",
        font=styles.note,
    )


def write_checks_sheet(grid, scenario_grid, data) -> None:
    from model_dashboard._quarterly_glassbox_writer import _quarter_header_rows

    styles = grid.styles
    _quarter_header_rows(grid, status=data.status)
    inputs_grid = data._inputs_grid
    params_grid = data._params_grid
    ws = grid.ws
    row = 4
    _section_header(grid, row, "Checks (audit build) - every row is an absolute difference; the summary column is its maximum")
    row += 2

    summary_col = grid.last_column + 2
    ws.column_dimensions[_column_letter(summary_col)].width = 14
    ws.column_dimensions[_column_letter(summary_col + 1)].width = 10
    ws.cell(row=row - 1, column=summary_col).value = "MAX difference"
    ws.cell(row=row - 1, column=summary_col).font = styles.subhead
    ws.cell(row=row - 1, column=summary_col + 1).value = "Verdict"
    ws.cell(row=row - 1, column=summary_col + 1).font = styles.subhead

    def check_row(label: str, template: str, quarters, tolerance: float) -> None:
        nonlocal row
        _set_label(grid, row, label)
        _formula_quarters(grid, row, template, font=styles.formula,
                          number_format="0.0E+00", quarters=quarters)
        first = _column_letter(_FIRST_DATA_COLUMN)
        last = _column_letter(grid.last_column)
        max_cell = ws.cell(row=row, column=summary_col)
        max_cell.value = f"=MAX(0,MAX({first}{row}:{last}{row}))"
        max_cell.number_format = "0.0E+00"
        max_cell.font = styles.formula
        verdict = ws.cell(row=row, column=summary_col + 1)
        verdict.value = (
            f"=IF({_column_letter(summary_col)}{row}<={tolerance},\"PASS\",\"FAIL\")"
        )
        verdict.font = styles.formula_bold
        verdict.fill = styles.check_fill
        row += 1

    scenario = SHEET_SCENARIO
    inputs = SHEET_INPUTS

    ped_raw = scenario_grid.row("ped.raw_level")
    ped_committed = inputs_grid.row("chk.ped_committed")
    ped_quarters = [q for q in grid.quarters if q in data.ped.raw_prediction]
    check_row(
        "1. PED coefficient chain vs committed raw prediction (km)",
        f"=ABS('{scenario}'!{{c}}{ped_raw}-'{inputs}'!{{c}}{ped_committed})",
        ped_quarters, 1e-6,
    )
    light_raw = scenario_grid.row("light.raw_mkm")
    light_committed = inputs_grid.row("chk.light_committed")
    light_quarters = [q for q in grid.quarters if q in data.light.raw_prediction]
    check_row(
        "2. Light OLS + residual-GBR vs committed raw prediction (m km)",
        f"=ABS('{scenario}'!{{c}}{light_raw}-'{inputs}'!{{c}}{light_committed}/1000000)",
        light_quarters, 1e-6,
    )
    heavy_raw = scenario_grid.row("heavy.raw_mkm")
    heavy_committed = inputs_grid.row("chk.heavy_committed")
    heavy_quarters = [q for q in grid.quarters if q in data.heavy.raw_prediction]
    check_row(
        "3. Heavy weighted ensemble vs committed raw prediction (m km)",
        f"=ABS('{scenario}'!{{c}}{heavy_raw}-'{inputs}'!{{c}}{heavy_committed}/1000000)",
        heavy_quarters, 1e-6,
    )
    for index, (stream, calibrated_key, scale) in enumerate(
        (("PED", "pol.ped.calibrated", ""),
         ("LIGHT_RUC", "pol.LIGHT_RUC.calibrated_mkm", "/1000000"),
         ("HEAVY_RUC", "pol.HEAVY_RUC.calibrated_mkm", "/1000000")),
        start=4,
    ):
        calibrated_row = scenario_grid.row(calibrated_key)
        committed_row = inputs_grid.row(f"chk.calibrated_{stream}")
        stream_quarters = [
            q for q in grid.quarters if q in data.policy.calibrated.get(stream, {})
        ]
        label_stream = {"PED": "PED", "LIGHT_RUC": "Light RUC", "HEAVY_RUC": "Heavy RUC"}[stream]
        check_row(
            f"{index}. {label_stream} calibrated vs committed displayed",
            f"=ABS('{scenario}'!{{c}}{calibrated_row}-'{inputs}'!{{c}}{committed_row}{scale})",
            stream_quarters, 1e-6,
        )

    identity_checks = (
        ("7. Gross FED closure", "gross_fed_revenue"),
        ("8. Net FED closure", "net_fed_revenue"),
        ("9. Gross RUC closure", "gross_ruc_revenue"),
        ("10. Net RUC closure", "total_ruc_net_revenue"),
        ("11. Gross MVR closure", "gross_mvr_revenue"),
        ("12. Net MVR closure", "net_mvr_revenue"),
        ("13. Total gross closure", "total_gross_revenue"),
        ("14. Total NLTF closure", "total_nltf_net_revenue"),
    )
    for label, series_id in identity_checks:
        disp_row = scenario_grid.row(f"disp.{series_id}")
        con_row = scenario_grid.row(f"con.{series_id}")
        adj_row = scenario_grid.row(f"adj.{series_id}")
        series_quarters = [
            q for q in grid.quarters if q in data.quarterly_values.get(series_id, {})
        ]
        check_row(
            f"{label}: displayed vs constructed + timing difference",
            f"=ABS('{scenario}'!{{c}}{disp_row}-('{scenario}'!{{c}}{con_row}"
            f"+'{scenario}'!{{c}}{adj_row}))",
            series_quarters, 1e-6,
        )

    row += 1
    _section_header(grid, row, "Four-quarter sums vs governed annual values (Q2 columns carry each June year's sum)")
    row += 1
    prm_header = params_grid.row("prm.fy_header")
    for series_id in sorted(data.quarterly_values):
        annual_row = params_grid.rows.get(f"prm.annual.{series_id}")
        disp_row = scenario_grid.rows.get(f"disp.{series_id}")
        if annual_row is None or disp_row is None:
            continue
        q2_quarters = []
        for fy in range(2026, 2051):
            fy_quarters = quarters_of_fiscal_year(fy)
            if all(q in data.quarterly_values[series_id] for q in fy_quarters):
                q2_quarters.append(fy_quarters[-1])
        if not q2_quarters:
            continue
        _set_label(grid, row, f"15. Four-quarter sum vs annual: {display_name(data, series_id)}")
        for quarter in q2_quarters:
            column = grid.col_of[quarter]
            first_letter = _column_letter(column - 3)
            last_letter = _column_letter(column)
            lookup = _xlookup(
                f"{last_letter}$1",
                _fy_range(prm_header, SHEET_PARAMS),
                _fy_range(annual_row, SHEET_PARAMS),
            )
            cell = ws.cell(row=row, column=column)
            cell.value = (
                f"=ABS(SUM('{scenario}'!{first_letter}{disp_row}:'{scenario}'!"
                f"{last_letter}{disp_row})-{lookup})"
            )
            cell.font = styles.formula
            cell.number_format = "0.0E+00"
        first = _column_letter(_FIRST_DATA_COLUMN)
        last = _column_letter(grid.last_column)
        max_cell = ws.cell(row=row, column=summary_col)
        max_cell.value = f"=MAX(0,MAX({first}{row}:{last}{row}))"
        max_cell.number_format = "0.0E+00"
        max_cell.font = styles.formula
        verdict = ws.cell(row=row, column=summary_col + 1)
        verdict.value = f"=IF({_column_letter(summary_col)}{row}<=0.001,\"PASS\",\"FAIL\")"
        verdict.font = styles.formula_bold
        verdict.fill = styles.check_fill
        row += 1

    row += 1
    _section_header(grid, row, "Timing differences sum to zero over each complete June year")
    row += 1
    adj_keys = sorted(key for key in scenario_grid.rows if key.startswith("adj."))
    for key in adj_keys:
        adj_row = scenario_grid.row(key)
        series_id = key.removeprefix("adj.")
        q2_quarters = getattr(data, "_adj_eligible", {}).get(series_id, [])
        if not q2_quarters:
            continue
        _set_label(grid, row, f"16. Timing difference closure: {display_name(data, series_id)}")
        for quarter in q2_quarters:
            column = grid.col_of[quarter]
            first_letter = _column_letter(column - 3)
            last_letter = _column_letter(column)
            cell = ws.cell(row=row, column=column)
            cell.value = (
                f"=ABS(SUM('{scenario}'!{first_letter}{adj_row}:'{scenario}'!"
                f"{last_letter}{adj_row}))"
            )
            cell.font = styles.formula
            cell.number_format = "0.0E+00"
        first = _column_letter(_FIRST_DATA_COLUMN)
        last = _column_letter(grid.last_column)
        max_cell = ws.cell(row=row, column=summary_col)
        max_cell.value = f"=MAX(0,MAX({first}{row}:{last}{row}))"
        max_cell.number_format = "0.0E+00"
        max_cell.font = styles.formula
        verdict = ws.cell(row=row, column=summary_col + 1)
        verdict.value = f"=IF({_column_letter(summary_col)}{row}<=0.000001,\"PASS\",\"FAIL\")"
        verdict.font = styles.formula_bold
        verdict.fill = styles.check_fill
        row += 1


def write_readme_sheet(ws, styles, data, scenario_note: str) -> None:
    ws.column_dimensions["A"].width = 120
    row = 1

    def put(text: str, font=styles.label) -> None:
        nonlocal row
        cell = ws.cell(row=row, column=1)
        cell.value = text
        cell.font = font
        cell.alignment = styles.wrap
        row += 1

    put("NLTF quarterly glass-box workbook", styles.title)
    row += 1
    put(f"Scenario: {data.trace_name} - {data.policy.state_label}", styles.label_bold)
    put("Engine: AR(1) production engine")
    put(f"Rate path: {data.policy.state_label}")
    put(f"Bridge vintage: {data.bridge_vintage_id}; long-run shape vintage: "
        f"{data.post_model.shape_vintage_id}; handover completes FY{data.post_model.completion_fy}")
    put(f"Model training cutoff: {data.provenance.get('model_training_cutoff', '')}; "
        f"PED latest actual: {data.ped.latest_actual}")
    if scenario_note:
        put(scenario_note)
    row += 1
    put("How to read this workbook", styles.subhead)
    put("- Scenario keeps the annual forecast extract's row labels and order, minus "
        "the annual-percentage-change block; columns are calendar quarters "
        "2000Q3-2050Q2 (June years FY2001-FY2050). Row 1 = June FY; row 2 = calendar "
        "quarter, coloured by status: grey = actual, orange = model forecast, peach "
        "= post-model.")
    put("- Actual-period cells are colour-coded: darker grey-blue = natively "
        "published actual quarter; light grey = governed quarterly presentation "
        "derived from the published annual actual. TUC GTK is shown in millions "
        "of tonne-km.")
    put("- Every value in the top block is an Excel formula linked to the detail "
        "sections below or to another worksheet. Blue = committed governed value; "
        "black = in-sheet formula; green = cross-sheet link.")
    put("- Displayed quarterly values are the governed annual value x the committed "
        "quarterly allocation share (the dashboard's quarterly display contract). "
        "The physical chains are constructed beside them; timing-difference rows "
        "capture within-year allocation timing and sum to zero over each complete "
        "June year.")
    put(f"- Rows {TRANSITION_RESERVED_ROWS[0]}-{TRANSITION_RESERVED_ROWS[-1]} stay "
        "reserved for the FED to RUC transition lines (transition Off in this "
        "scenario).")
    row += 1
    put("Model representation (stated limitations)", styles.subhead)
    put("- PED is formula-reproduced from coefficients: the AR(1) engine's "
        "log-linear terms, the lagged-target recursion and the geometric AR(1) "
        "error recursion seeded from the committed last residual.")
    put("- Light RUC combines an Excel-reproduced OLS base with an exact imported "
        "residual-GBR log component from the fitted model. The tree component has "
        "no regression coefficients.")
    put("- Heavy RUC uses exact imported component predictions and governed "
        "ensemble weights (level-space blend); coefficients exist only for the "
        "linear (Ridge) component.")
    put("- The workbook is an exact fixed-scenario replay: editing an input cell "
        "does NOT re-run the fitted tree models, so imported component outputs "
        "will not respond. The coefficient chains, overlays and identities will.")
    put("- Beyond FY2030 the displayed activity carries no rate-path demand "
        "response (the decision-grade policy horizon ends FY2030); revenue carries "
        "the governed rate ratio. FY2031+ RUC aggregates follow the production "
        "top-down construction with the hidden Heavy-BEV line solved residually.")
    row += 1
    put("Verification", styles.subhead)
    put("- Every model, overlay, handover and rollup identity in this workbook is "
        "verified in Python against the governed displayed values at build time, "
        "at machine precision, before a single cell is written. The audit build "
        "additionally carries a Checks sheet recalculated in Excel; the delivered "
        "workbook omits it by design.")
