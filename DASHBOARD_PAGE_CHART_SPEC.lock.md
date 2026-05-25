# DASHBOARD_PAGE_CHART_SPEC.lock.md

The primary dashboard navigation is locked to four pages only:

1. Overview
2. Diagnostics
3. Scenario Comparison
4. Schiff Benchmark

Each page must keep a KPI row and no more than four main chart/object panels below it. Supporting operational detail may exist only in collapsed expanders or explicit drilldowns.

## Overview

- KPI cards: Quarterly MAPE, Annual MAPE, Plotted candidates, Benchmark Pass.
- Chart 1: Finalist Forecast Accuracy, grouped quarterly/annual MAPE bars by stream.
- Chart 2: Candidate Search Frontier, cone sample scatter with finalist, pure Schiff, PDF reference, frontier and distribution roles.
- Chart 3: Finalist Ensemble Composition, component weights where available.
- Chart 4: Stress and Horizon Checks, six-bucket line chart by stream.

## Diagnostics

- KPI cards: Diagnostics Coverage, Mean Durbin-Watson, Mean calibration R2, Heteroscedasticity Pass.
- Chart 1: Residual Autocorrelation by Lag.
- Chart 2: Residual vs Fitted.
- Chart 3: Diagnostic Pass Matrix.
- Chart 4: Error Distribution by Horizon.

## Scenario Comparison

- KPI cards: Quarterly MAPE, Annual MAPE, Gain vs Schiff, Decision Status.
- Chart 1: Stream Comparison, Scenario A vs Scenario B.
- Chart 2: Improvement vs Benchmark.
- Chart 3: Horizon Comparison.
- Chart 4: Decision Summary.

## Schiff Benchmark

- KPI cards: Pure-Schiff Streams, Best Pure-Schiff Qtr MAPE, Best Finalist Qtr MAPE, Paired Comparisons.
- Chart 1: Schiff vs Finalist MAPE.
- Chart 2: Benchmark Horizon Profiles.
- Chart 3: Full-sample Gain vs Schiff.
- Chart 4: Benchmark Summary.

## Semantic Locks

- Full-sample gains and paired common-grid metrics must not be merged under the same label.
- The Schiff Benchmark gain chart is titled Full-sample Gain vs Schiff when it shows full-sample Schiff MAPE minus finalist MAPE.
- Decision tables label Full-sample Qtr Gain, Full-sample Annual Gain and Paired Win Rate separately.
- Calibration or Mincer-Zarnowitz R2 must not be labelled adjusted R2.
- The Overview candidate count is labelled Plotted candidates when it counts the default curated cone rows.
