# Hover Review

Status: **passed** for the Parquet backed dashboard browser run on 2026-05-23.

All major Plotly hover checks passed through Playwright. Tooltip text is management readable, uses clean labels, keeps MAPE and bias values to two decimals, keeps weights to one decimal, suppresses trace names, and does not expose raw source fields.

| Chart | Screenshot evidence | Tooltip evidence | Status |
|---|---|---|---|
| Finalist Forecast Accuracy | `artifacts/screenshots/hover-finalist-accuracy.png` | Stream, model, source, quarterly MAPE, annual MAPE, and bias are formatted for management review. | Pass |
| Candidate Search Frontier | `artifacts/screenshots/hover-candidate-landscape.png` | Stream, short model, role, quarterly MAPE, annual MAPE, bias, source family, feature set, and inclusion reason are readable. | Pass |
| Finalist Ensemble Composition | `artifacts/screenshots/hover-ensemble-composition.png` | Stream, ensemble, component, and weight use compact labels and one decimal weight formatting. | Pass |
| Stress and Horizon Checks | `artifacts/screenshots/hover-stress-checks.png` | Stream, stress window, MAPE, model, and row count use readable labels and clean decimals. | Pass |

Browser evidence:

- Candidate frontier hover passed with no raw field labels.
- Finalist accuracy hover passed with clean MAPE labels.
- Ensemble composition hover passed with one decimal weight formatting.
- Stress and horizon hover passed with readable stress window labels.
