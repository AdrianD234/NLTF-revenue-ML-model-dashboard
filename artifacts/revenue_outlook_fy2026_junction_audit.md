# FY2026 Revenue Outlook Junction Audit

Status: verified in worktree, pending commit and push.

## Junction Finding

FY uses June-year semantics: `FYyyyy = yyyy-1 Q3 + yyyy-1 Q4 + yyyy Q1 + yyyy Q2`.

The workbook FY2026 annual `Actual` point is actual-to-date, not a complete annual actual:

- FY2026 actual value: `3,528.410251`
- Workbook formula evidence: `AZ163 + BA163 + BB163`
- Missing fourth-quarter cell: `BC163`
- Selected dashboard/model FY2026 path: `4,709.942175`
- Official BEFU25 Total net revenues FY2026: `4,569.881668`, status `ST_FORECAST`

## FY2024-FY2027 Completeness Table

| FY | Expected quarters | Actual quarters used for complete annual coverage | Coverage | Status | Chart treatment | Actual value | Selected model | BEFU25 |
| ---: | --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| 2024 | 2023Q3; 2023Q4; 2024Q1; 2024Q2 | 2023Q3; 2023Q4; 2024Q1; 2024Q2 | 4 | complete_actual | complete_actual_line | 4,231.953291 | 4,272.837558 | 4,042.285462 |
| 2025 | 2024Q3; 2024Q4; 2025Q1; 2025Q2 | 2024Q3; 2024Q4; 2025Q1; 2025Q2 | 4 | complete_actual | complete_actual_line | 4,493.732302 | 4,441.492066 | 4,272.297778 |
| 2026 | 2025Q3; 2025Q4; 2026Q1; 2026Q2 | 2025Q3; 2025Q4; 2026Q1 | 3 | partial_actual_to_date | partial_actual_marker_not_connected | 3,528.410251 | 4,709.942175 | 4,569.881668 |
| 2027 | 2026Q3; 2026Q4; 2027Q1; 2027Q2 |  | 0 | forecast_only | forecast_path_only |  | 5,212.758720 | 5,049.738899 |

## Chart Coordinate Evidence

Before this fix, the source Total NLTF path used a single connected `Actual / benchmark` trace. The FY2026 point at `(2026, 3,528.410251)` was therefore connected to the complete actual line after FY2025.

After this fix:

- `Actual` trace data coordinates: `(2023, 3,052.436064)`, `(2024, 4,231.953291)`, `(2025, 4,493.732302)`.
- `Actual to date (3 of 4 quarters)` marker: `(2026, 3,528.410251)`.
- Forecast-start marker: `FY2026`.
- Selected-FY marker: `FY2031`.
- Selected MOT/BEFU release path starts at `FY2026`: `4,569.881668`.
- Selected dashboard basis starts at `FY2026`: `4,709.942175`.
- In-house forecast starts at `FY2026`: `4,709.942175`.
- Aaron Schiff starts at `FY2026`: `4,745.203539`.
- Hybrid replacement-only outlook starts at `FY2026`: `4,735.389872`.

## Screenshot Evidence

- Fresh Revenue Outlook screenshot: `artifacts/screenshots/final-05-revenue-outlook.png`
- Fresh browser page screenshot mirror: `artifacts/screenshots/mcp-05-revenue-outlook.png`
- Prior geometry reference retained: `artifacts/screenshots/revenue-outlook-after-1680x940.png`
- Prior mobile geometry reference retained: `artifacts/screenshots/revenue-outlook-after-820x940.png`

## Validation Evidence

- `compileall-fy2026-junction`: PASS.
- `pytest-fy2026-junction-focused`: PASS, `41 passed`.
- `pytest-full-fy2026-junction-rerun`: PASS, `357 passed, 50 skipped, 39 deselected`.
- `validate-dashboard-data-fy2026`: PASS.
- `validate-chart-sources-fy2026`: PASS.
- `validate-semantic-labels-fy2026`: PASS.
- `verify-dashboard-skip-browser-fy2026-junction`: PASS.
- `host-playwright-fy2026-junction`: PASS, `38 passed`.

## Files

- Loader-derived audit: `data/revenue_model_source_pack/2026_05_19/annual_completeness_audit.csv`
- Loader manifest includes SHA256 for `annual_completeness_audit.csv`.
- Raw extracted CSV rows were preserved; the new audit is derived from quarterly coverage/status and annual source metadata.
