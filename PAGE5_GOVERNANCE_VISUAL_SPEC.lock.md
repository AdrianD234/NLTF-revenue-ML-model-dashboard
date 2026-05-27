# Page 5 Governance Visual Spec

Status: LOCKED

This page is complete only when Page 5 renders as a polished Waka Kotahi / NZTA-style executive dashboard page and remains read-only audit evidence. It must not alter finalist metrics, score-basis logic, evidence-pack scoring, KPI values, scenario comparison, diagnostics, stress charts, or main chart-source calculations.

## Required Structure

- [x] Header and navigation use the existing NTLF Revenue Modelling theme, with Governance & Reproducibility active.
- [x] Page label reads `Page 5 of 5 - Governance & Reproducibility`.
- [x] Filter strip title reads `Governance & Reproducibility Filters`.
- [x] Stream control is segmented: All streams, PED, Light RUC, Heavy RUC.
- [x] Reproducibility pack selector is visible.
- [x] Workbook availability/provenance card is visible and read-only.
- [x] Read-only status card is visible.
- [x] Reset Filters button is visible.
- [x] Downloads dropdown is visible.
- [x] Top status cards cover repro packs loaded, workbook provenance, chart-source isolation, and page role.
- [x] Reproducibility status cards cover PED, Light RUC, and Heavy RUC.
- [x] Build-flow story is visual process cards/arrows, not a plain table.
- [x] Glossary is chip/card styling, not a plain table.
- [x] Registry panel uses `model_registry.parquet`.
- [x] Component trace uses visual diagrams for PED, Light RUC, and Heavy RUC.
- [x] Lower panels include feature importance, coefficients, scenario sensitivities, training-window trace, downloads, and SHAP unavailable note.
- [x] Footer is dark navy and states the page is read-only and does not feed KPI, finalist, scenario, diagnostic, stress, or chart-source calculations.

## Wording Locks

- Light RUC wording: `Two-stage OLS base plus GBM residual correction, exactly replayed against evidence predictions.`
- Heavy RUC wording: `Four-component weighted ensemble exactly replayed against evidence predictions.`
- PED wording: `PED finalist exactly replays the stored HPO/static-solver component prediction; inner HPO/static-solver rebuild remains a future audit layer.`
- Scenario sensitivity wording uses `impact on dependent variable / model target`.
- SHAP wording is `SHAP not yet generated`; no fabricated SHAP output is permitted.
