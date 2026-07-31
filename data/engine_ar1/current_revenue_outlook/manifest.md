# Revenue Outlook Manifest

- Schema: `revenue-outlook-pack-v1`
- Status: `explicitly_promoted_current_outlook`
- Promoted: `2026-07-08T22:20:18.365224+00:00`
- Output: `data/engine_ar1/current_revenue_outlook`

## Equations
- EV_PHEV_MIGRATION: Optimized lambda allocates EV/PHEV uptake between PED/light-petrol and current finalist total Light RUC to match BEFU26 light-mobility proportions with a smoothness penalty.
- PED VKT per capita: PED revenue = adjusted PED/light-petrol VKT after optimized EV/PHEV migration * BEFU26 litres/100km * BEFU26 gross PED rate.
- Light RUC volume: Light RUC revenue = optimized conventional Light RUC km after EV/PHEV migration * BEFU26 conventional Light effective rate.
- Heavy RUC volume: Heavy RUC revenue = current finalist net km * BEFU26 effective Heavy RUC rate.
- ROLLUPS: Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate optimized PED, conventional Light RUC, Light BEV, PHEV and Heavy RUC replacement lines plus BEFU26 fixed components.

## Scenario Roles
- `current_basecase`: `basecase`, workbook `None`, SHA256 `None`
- `current_comparison_1`: `comparison`, workbook `None`, SHA256 `None`

## Bridge Status
- PED VKT per capita: available
- Light RUC volume: available
- Heavy RUC volume: available

## Canonical Join Keys
- Columns: `canonical_stream_key, canonical_period_key, canonical_scenario_key, canonical_join_key`
- Rule: Forecast Builder volume packs join to Revenue Outlook rows by canonical stream, period and scenario keys; historical rows use historical_actual.

## Revenue Source Pack
- Version: `BEFU26`
- Raw workbook SHA256: `7d6e5b19119ca8b5272ca2205c0735719033d82484ce674cfb595e6f45d085ff`
- Manifest SHA256: `93406dc1c609b8792796b5ca6f2ba195eea8d362a90e8ba645c10eece9d9fe20`
- Status: `official_vintage_pack_vendored`
- Dashboard default series: `Total NLTF revenue`
- Source workbook current series: `None`
