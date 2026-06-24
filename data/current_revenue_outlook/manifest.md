# Revenue Outlook Manifest

- Schema: `revenue-outlook-pack-v1`
- Status: `explicitly_promoted_current_outlook`
- Promoted: `2026-06-24T09:50:46.982869+00:00`
- Output: `data/current_revenue_outlook`

## Equations
- Light RUC volume: Light RUC revenue = net km / 1,000 * nominal effective average Light RUC rate.
- Heavy RUC volume: Heavy RUC revenue = net km / 1,000 * nominal effective average Heavy RUC rate.
- PED VKT per capita: PED revenue = litres * nominal PED base rate / 100. Litres must come from a source-backed PED litres bridge, not from the VKT/capita activity model alone.

## Scenario Roles
- `current_basecase`: `basecase`, workbook `NLTF_forecast_input_template_to_2050Q4_basecase (2) - Copy.xlsx`, SHA256 `d0644d353ee5a073602186cf7ac5c16e707d5350e16fd037b73a65528067cc6a`
- `current_comparison_1`: `comparison`, workbook `NLTF_forecast_input_template_to_2050Q4_high_population (2) - Copy.xlsx`, SHA256 `6213ce565cf1f4a058a3ea9f1af4d5476a8b0423a4d8747905c3cba128380ce1`

## Bridge Status
- Heavy RUC volume: nominal_rate_missing
- Light RUC volume: nominal_rate_missing
- PED VKT per capita: ped_bridge_source_history_missing

## Canonical Join Keys
- Columns: `canonical_stream_key, canonical_period_key, canonical_scenario_key, canonical_join_key`
- Rule: Forecast Builder volume packs join to Revenue Outlook rows by canonical stream, period and scenario keys; historical rows use historical_actual.

## Revenue Source Pack
- Version: `2026_05_19`
- Raw workbook SHA256: `00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b`
- Manifest SHA256: `00f5547b4c54f5fc9bfa4fc2a3f3b470cab89be56d87265a3491b7b003b72fd6`
- Status: `source_pack_vendored`
- Dashboard default series: `Total NLTF revenue`
- Source workbook current series: `Total RUC+PED revenue`
