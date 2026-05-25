# Semantic Label Validation Report

Status: **passed**.

| Check | Status | Evidence |
| --- | --- | --- |
| Candidate count label is precise | PASS | Overview KPI should identify plotted/default candidate rows rather than a vague candidate count. |
| Calibration R2 is not labelled adjusted R2 | PASS | Diagnostics KPI title inspected in app.py. |
| Full-sample gain chart is not labelled paired | PASS | Schiff gain chart title inspected in app.py. |
| Decision table separates full-sample gains from paired win rate | PASS | Scenario and Schiff summary labels inspected in app.py. |
| Residual vs fitted axis does not use misleading million-unit label | PASS | Residual axis title inspected in app.py/plot helpers. |
| Light RUC paired weakness is not hidden by full-sample gain label | PASS | paired_gain=-1.1591198726710292; full_sample_gain=2.399240961876965 |
| Dashboard chart spec uses current semantic labels | PASS | No stale chart-spec labels found. |
| Screenshot review does not describe the full-sample chart as paired | PASS | artifacts/screenshot_review.md label wording inspected. |
