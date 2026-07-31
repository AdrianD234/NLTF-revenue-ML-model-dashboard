# Revenue Outlook Manifest

- Schema: `revenue-outlook-pack-v1`
- Status: `explicitly_promoted_current_outlook`
- Promoted: `2026-07-27T03:59:12.371742+00:00`
- Output: `data/current_revenue_outlook`

## Equations
- EV_PHEV_CLASS_COMPOSITION: The Light RUC model output is the CONVENTIONAL class. The class pool is expanded from it by the MoT VFM 202405 Base uptake shares (conventional_anchor_vfm_composition_v1); Light BEV and PHEV are allocated from that pool, never added on.
- PED VKT per capita: PED revenue = raw AR(1) PED/light-petrol VKT x scenario population * BEFU26 litres/100km * BEFU26 gross PED rate.
- Light RUC volume: Light RUC revenue = conventional Light RUC km (preserved exactly under the Base uptake basis) * BEFU26 conventional Light effective rate.
- Heavy RUC volume: Heavy RUC revenue = current finalist net km * BEFU26 effective Heavy RUC rate.
- ROLLUPS: Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate optimized PED, conventional Light RUC, Light BEV, PHEV and Heavy RUC replacement lines plus BEFU26 fixed components.

## Scenario Roles
- `current_basecase`: `basecase`, workbook `NLTF_forecast_input_template_to_2050Q4_basecase _2_ - Copy.xlsx`, SHA256 `d0644d353ee5a073602186cf7ac5c16e707d5350e16fd037b73a65528067cc6a`
- `current_comparison_1`: `comparison`, workbook `NLTF_forecast_input_template_to_2050Q4_high_population _2_ - Copy.xlsx`, SHA256 `6213ce565cf1f4a058a3ea9f1af4d5476a8b0423a4d8747905c3cba128380ce1`

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
