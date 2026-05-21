# REFERENCE_PAGE_WIREFRAMES.lock.md

## Overview wireframe

Header:
- Logo left
- Large "Governance" title
- Lime underline
- Top nav right
- Page 1 of 4

Filter row:
- Stream
- Model Family
- Baseline
- Horizon
- Forecast Vintage
- Date Window
- Reset Filters

KPI row:
- Quarterly MAPE
- Annual MAPE
- R2 or candidate count / model fit proxy
- Governance Score

Main grid:
- Left: Finalist Forecast Accuracy
- Middle: Candidate Search Landscape
- Right: Finalist Ensemble Composition
- Bottom left: Stress and Horizon Checks
- Bottom right: Distribution of Forecast Error by Horizon Bucket

Footer:
- Transport Revenue Model Testbench
- Refined Finalist Models
- Data as of date

## Diagnostics wireframe

Header and filters as above.

KPI row:
- Adjusted R2 or model-fit proxy
- Mean Durbin-Watson if available
- Stationarity pass rate if available
- Heteroscedasticity/error pass rate if available

Grid:
- Test matrix / run diagnostics
- Autocorrelation/error diagnostics
- Heteroscedasticity/error diagnostics
- Residuals vs fitted or forecast error scatter
- Normality/error distribution
- Diagnostics summary table

If diagnostic data is not available, show clearly labelled cards explaining which output files are needed.

## Scenario Comparison wireframe

Scenario A vs Scenario B selectors:
- Scenario A: refined finalist
- Scenario B: Schiff benchmark
- Baseline

KPI row:
- Quarterly MAPE
- Annual MAPE
- Model fit proxy
- Governance score

Grid:
- Scenario accuracy comparison
- Error by forecast horizon
- Improvement vs benchmark
- Forecast error distribution
- Model/test summary
- Decision lens

## Schiff Benchmark wireframe

KPI row:
- Quarterly MAPE
- Annual MAPE
- Replication / match score
- R2 or benchmark-fit proxy

Grid:
- Schiff structural benchmark MAPE chart
- Cross-validation results by stream
- Benchmark comparison summary
- Paper replication notes
- About the Schiff benchmark
