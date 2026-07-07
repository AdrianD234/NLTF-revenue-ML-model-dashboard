# Revenue Outlook Manifest

- Schema: `revenue-outlook-pack-v1`
- Status: `explicitly_promoted_current_outlook`
- Promoted: `2026-06-25T21:42:25.800323+00:00`
- Output: `data/current_revenue_outlook`

## Equations
- EV_PHEV_MIGRATION: Optimized lambda allocates EV/PHEV uptake between PED/light-petrol and current finalist total Light RUC to match MBU26 light-mobility proportions with a smoothness penalty.
- PED VKT per capita: PED revenue = adjusted PED/light-petrol VKT after optimized EV/PHEV migration * MBU26 litres/100km * MBU26 gross PED rate.
- Light RUC volume: Light RUC revenue = optimized conventional Light RUC km after EV/PHEV migration * MBU26 conventional Light effective rate.
- Heavy RUC volume: Heavy RUC revenue = current finalist net km * MBU26 effective Heavy RUC rate.
- ROLLUPS: Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate optimized PED, conventional Light RUC, Light BEV, PHEV and Heavy RUC replacement lines plus MBU26 fixed components.

## Scenario Roles
- `current_basecase`: `basecase`, workbook `NLTF_forecast_input_template_to_2050Q4_basecase (2) - Copy.xlsx`, SHA256 `d0644d353ee5a073602186cf7ac5c16e707d5350e16fd037b73a65528067cc6a`
- `current_comparison_1`: `comparison`, workbook `NLTF_forecast_input_template_to_2050Q4_high_population (2) - Copy.xlsx`, SHA256 `6213ce565cf1f4a058a3ea9f1af4d5476a8b0423a4d8747905c3cba128380ce1`

## Bridge Status
- PED VKT per capita: available
- Light RUC volume: available
- Heavy RUC volume: available

## Canonical Join Keys
- Columns: `canonical_stream_key, canonical_period_key, canonical_scenario_key, canonical_join_key`
- Rule: Forecast Builder volume packs join to Revenue Outlook rows by canonical stream, period and scenario keys; historical rows use historical_actual.

## Revenue Source Pack
- Version: `MBU26`
- Raw workbook SHA256: `9aaff21f72c0a10cfa972a29d3c4f716495c79cbd72fc28e8008a65558454e12`
- Manifest SHA256: `2c5fb4fec1431ed92de1b3971bacd559e091d58dab08bce60ea53e30b24b8c15`
- Status: `mbu26_annual_spine_vendored`
- Dashboard default series: `Total NLTF revenue`
- Source workbook current series: `None`
