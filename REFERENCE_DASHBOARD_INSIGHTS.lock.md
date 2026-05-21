# REFERENCE_DASHBOARD_INSIGHTS.lock.md

This file locks the dashboard to the core management insights shown in the reference screenshots.

The dashboard should be curated, not a raw data dump.

## Top-level pages

1. Overview
2. Diagnostics
3. Scenario Comparison
4. Schiff Benchmark

Supporting modules may remain, but they must not dominate the main governance story.

## Overview

Must include:

- Finalist Forecast Accuracy
- Candidate Search Landscape / optimisation cone
- Finalist Ensemble Composition
- Stress and Horizon Checks
- Distribution of Forecast Error by Horizon Bucket

The Overview finalist values must show the latest arbitration run:

- PED: `2.47%` quarterly and `2.39%` annual
- Light RUC: `9.15%` quarterly and `6.00%` annual
- Heavy RUC: `3.56%` quarterly and `3.17%` annual

## Diagnostics

Must include:

- Feature/test matrix or run diagnostic equivalent
- Autocorrelation diagnostics or forecast-error lag view
- Heteroscedasticity / run error diagnostics
- Residual-vs-fitted equivalent or forecast error scatter
- Error distribution
- Diagnostics summary

## Scenario Comparison

Must compare:

- Scenario A: latest arbitration finalist
- Scenario B: pure Schiff benchmark or previous PDF/reference finalist

Must include:

- Accuracy comparison
- Error by forecast horizon
- Improvement vs benchmark
- Forecast error distribution
- Model/test summary
- Decision lens

## Schiff Benchmark

Must include:

- Pure Schiff structural benchmark MAPE
- Cross-validation / horizon results where available
- Benchmark comparison summary
- Paper replication / structural benchmark explanation
- Clear separation of pure Schiff, Schiff residual correction, Schiff blend, and solver/challenger models

## De-emphasis rule

Remove or de-emphasise stale insights that do not support these pages.

The dashboard must not show obsolete values from older AutoGluon balanced runs as latest recommended finalists.
