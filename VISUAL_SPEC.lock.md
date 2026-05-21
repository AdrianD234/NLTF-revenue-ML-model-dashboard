# VISUAL_SPEC.lock.md

The dashboard must visually approximate the supplied Waka Kotahi/NZTA-style governance dashboard screenshots.

## Overall style

- White or near-white background.
- Dark navy primary colour.
- Lime/green accent colour.
- Teal secondary accent for Heavy RUC.
- Orange accent only for warning/scenario/Schiff comparison states.
- Large page title: "Governance".
- Waka Kotahi/NZTA-style header area using text and neutral marks only unless official assets are provided.
- Horizontal tab navigation with four primary pages: Overview, Diagnostics, Scenario Comparison, Schiff Benchmark.
- Page indicator, for example "Page 1 of 4".
- Filter bar beneath header.
- KPI cards below filters.
- Rounded cards with light grey borders.
- Dashboard-style dense but readable layout.
- Footer strip with model/testbench label and data-as-of date.

## Colours

- Navy: `#002B5C`
- Deep navy: `#003366`
- Lime: `#A7C800`
- Green: `#00843D`
- Teal: `#008C7E`
- Orange: `#F37021`
- Light blue: `#EAF2F8`
- Border grey: `#D9E2EC`
- Text dark: `#102A43`

## Overview page visual targets

Must include filter bar, KPI cards, Finalist Forecast Accuracy, Candidate Search Landscape, Finalist Ensemble Composition, Stress and Horizon Checks, and Distribution of Forecast Error by Horizon Bucket.

## Diagnostics page visual targets

Must include diagnostic KPI cards, stationarity/test matrix where possible, residual diagnostics where possible, residual vs fitted or error scatter where possible, diagnostics summary, and pass/warning/fail indicators. If diagnostics data is missing, show "Not available in this run" gracefully.

## Scenario Comparison page visual targets

Must include Scenario A/B controls, MAPE comparison, error by forecast horizon, improvement vs benchmark, forecast error distribution, model/test summary, and decision lens panel. If no scenario data exists, use selected finalist vs Schiff benchmark.

## Schiff Benchmark page visual targets

Must include benchmark MAPE cards, quarterly vs annual Schiff benchmark chart, cross-validation style charts if available, benchmark comparison summary, paper replication notes, and about-the-Schiff explanation.

## Chart polish

- Charts must have clear titles and units.
- Legends must be readable.
- Values should be labelled where appropriate.
- Long model names should be shortened with lookup tables.
- Candidate landscape must not be flattened by failed/outlier candidates.
- Provide controls to show/hide outliers and focus on the competitive frontier.

## Screenshot standard

Each screenshot must show meaningful content above the fold, no blank/placeholder-heavy page, readable text, no obvious overflow, charts with real data, and at least 9/10 visual-reference score in `artifacts/visual_reference_comparison.md`.
