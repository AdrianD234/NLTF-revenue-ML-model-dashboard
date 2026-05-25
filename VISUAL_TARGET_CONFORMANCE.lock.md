# Visual Target Conformance Lock

This dashboard is not complete when data tests pass alone. The four supplied target images are the visual source of truth for layout, chart hierarchy, page structure, and management-ready polish.

The Parquet and diagnostic audit pack remain the data source of truth. Screenshots must never be used as data.

Completion requires:

- Four current after-screenshots exist for Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark.
- The visual reviewer artifacts mark all four pages PASS.
- `PAGE_BY_PAGE_VISUAL_DELTA.lock.md` has no unchecked defects.
- `BUG_BACKLOG.md` has no unchecked defects.
- `scripts/validate_80_gates.py` reports 100/100 PASS, including visual gates 81-100.
- Browser tests confirm the repaired visual structure after screenshots are regenerated.

Do not weaken, delete, or bypass these requirements.
