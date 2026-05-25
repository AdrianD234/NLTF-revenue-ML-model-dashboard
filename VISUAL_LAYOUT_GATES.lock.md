# Visual Layout Gates Lock

The validator must fail when any item below is not evidenced as PASS.

1. Current screenshots for all four pages are present.
2. No primary page has more than four main chart/object panels below the KPI row.
3. Overview stress x-axis order is exactly: `1-4 qtrs`, `5-8 qtrs`, `9-12 qtrs`, `2024+`, `2022-23`, `Annual`.
4. Candidate frontier chart has no giant ellipse or circle overlays.
5. Candidate frontier shows current finalist markers.
6. Candidate frontier shows pure Schiff markers.
7. Diagnostics matrix is not a plain unstyled text-only table.
8. Diagnostics matrix has pass/caution/fail visual treatment.
9. Diagnostics page shows R2, Durbin-Watson and heteroscedasticity metrics.
10. Scenario stream comparison section labels do not overlap.
11. Scenario horizon comparison shows all three streams when Stream filter is All Streams.
12. Schiff MAPE chart separates Quarterly and Annual sections clearly.
13. Schiff horizon profiles show all three streams when Stream filter is All Streams.
14. Plotly hovers contain no underscores or raw internal column names.
15. Top navigation labels are not clipped.
16. `BUG_BACKLOG.md` has no unchecked visual defects.

Where automated pixel detection is brittle, `artifacts/visual_delta_review.md` and `artifacts/target_vs_current_screenshot_matrix.md` must explicitly mark PASS with screenshot evidence.
