# MBU26 Annual Source Spine

- Schema: `nltf-revenue-mbu26-annual-spine-v1`
- Source release: `MBU26`
- Output: `data/revenue_model_source_pack/mbu26_annual_spine`
- Workbook: `Revenue forecast error, annual view from BEFU 2013-25.xlsx`
- Workbook SHA256: `9aaff21f72c0a10cfa972a29d3c4f716495c79cbd72fc28e8008a65558454e12`
- Worksheet: `MBU26`

The workbook is offline lineage only. Streamlit reads the repo-local CSV/Parquet extracts.

## Formula Policy

MBU26 annual value cells are stored without Excel formulas in the grid; aggregate formula contracts are asserted from MBU26 row identities and residuals are reported without force-balancing.
