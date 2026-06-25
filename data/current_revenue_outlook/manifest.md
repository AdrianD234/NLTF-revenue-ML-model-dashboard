# Revenue Outlook Manifest

- Schema: `revenue-outlook-pack-v1`
- Status: `explicitly_promoted_current_outlook`
- Promoted: `2026-06-25T21:42:25.800323+00:00`
- Output: `data/current_revenue_outlook`

## Equations
- PED VKT per capita: PED revenue = current finalist VKT/capita * MBU26 population -> total VKT * MBU26 litres/100km * MBU26 gross PED rate.
- Light RUC volume: Light RUC revenue = current finalist net km * MBU26 effective Light RUC rate.
- Heavy RUC volume: Heavy RUC revenue = current finalist net km * MBU26 effective Heavy RUC rate.
- ROLLUPS: Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate three replacement lines plus MBU26 fixed components.

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
- Manifest SHA256: `fee4c2bde49bc381266aaec41c0e1762c5e529a5c948a59f592f8224fa91f836`
- Status: `mbu26_annual_spine_vendored`
- Dashboard default series: `Total NLTF revenue`
- Source workbook current series: `None`
