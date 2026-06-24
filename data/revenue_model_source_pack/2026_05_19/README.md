# NLTF Revenue Model Distilled Source Pack

## NLTF Revenue Model — Distilled Source Pack

- **Purpose:** Human-readable index to the normalized CSV/JSON source pack.
- **Recommended repo path:** data/revenue_model_source_pack/2026_05_19/
- **Raw workbook:** Keep outside Git; use the SHA256 below for reproducibility.
- **Directly modeled:** PED VKT per capita, Light RUC net km, Heavy RUC net km.
- **PED bridge:** VKTpc → total VKT → PED litres → nominal PED revenue.
- **RUC bridge:** Net km ÷ 1,000 × nominal effective average RUC rate.
- **Pass-through:** LPG, CNG, refunds, MVR and TUC require explicit official paths or governed assumptions.
- **Legacy label:** Total RUC+PED revenue = Net FED + Net RUC subtotal, not Total NLTF.
- **Source SHA256:** 00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b
- **Large data:** Use the CSV files in the ZIP for release paths, forecast archive and formula lineage.
