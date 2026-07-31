# Corrected MBU26 reconciliation (post-P0 baseline)

Current values are the real app-supported final stage (pack -> Treasury macro -> exact-VFM composition -> policy applied once) at merged main f8719f3. Official values are the MBU26 spine and its governed rate-only policy counterfactual.

## Headline

- **Policy-normalised model gap** (both sides published): within roughly **+-$62m** over FY2026-FY2030.
- **The actual default UI shows a much larger FY2027 difference** (-397.1m): the displayed Current trace is on the DELAYED policy while MBU26 remains PUBLISHED, so most of that gap is a policy-basis mismatch (-345.6m), not model performance.
- **The policy-aligned delayed comparison** removes that basis mismatch by delaying both sides (FY2027 gap -36.5m).
- None of these comparisons proves that either the current model or MBU26 is correct; they measure difference, not truth.

The earlier -8.7% figure was the **superseded pre-P0 stored-pack reconciliation**: it described the retired post-lambda pack layer, not the true former final front end, and must not be quoted as the pre-P0 model gap.

## policy_normalised

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   26.344 |   74.633 |  -17.034 |   -7.341 |    1.872 |    0.499 |  -12.399 | -5.97e-12 |
| 2027 |  -51.492 |   10.821 |  -50.210 |   -2.569 |   -2.271 |   -0.787 |  -44.802 | -6.71e-12 |
| 2028 |  -38.676 |    2.994 |  -41.670 |    9.457 |    4.696 |    1.060 |  -56.757 | 2.16e-12 |
| 2029 |  -29.007 |    6.116 |  -35.123 |   17.685 |   16.679 |    4.303 |  -73.502 | 2.50e-12 |
| 2030 |  -25.876 |   10.119 |  -35.995 |   13.571 |   32.655 |    8.428 |  -90.188 | 5.06e-12 |

## actual_default_ui

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   26.344 |   74.633 |  -17.034 |   -7.341 |    1.872 |    0.499 |  -12.399 | -5.97e-12 |
| 2027 | -397.115 | -157.070 | -227.941 |  -73.901 |  -11.117 |   -3.221 | -139.919 | -6.48e-12 |
| 2028 |  -38.676 |    2.994 |  -41.670 |    9.457 |    4.696 |    1.060 |  -56.757 | 2.16e-12 |
| 2029 |  -29.007 |    6.116 |  -35.123 |   17.685 |   16.679 |    4.303 |  -73.502 | 2.50e-12 |
| 2030 |  -25.876 |   10.119 |  -35.995 |   13.571 |   32.655 |    8.428 |  -90.188 | 5.06e-12 |

## policy_aligned_delayed

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   26.344 |   74.633 |  -17.034 |   -7.341 |    1.872 |    0.499 |  -12.399 | -5.97e-12 |
| 2027 |  -36.506 |   16.628 |  -41.031 |    0.579 |   -2.070 |   -0.719 |  -39.039 | -6.48e-12 |
| 2028 |  -38.676 |    2.994 |  -41.670 |    9.457 |    4.696 |    1.060 |  -56.757 | 2.16e-12 |
| 2029 |  -29.007 |    6.116 |  -35.123 |   17.685 |   16.679 |    4.303 |  -73.502 | 2.50e-12 |
| 2030 |  -25.876 |   10.119 |  -35.995 |   13.571 |   32.655 |    8.428 |  -90.188 | 5.06e-12 |

Fixed shared components (Heavy BEV under published, admin, refunds, MVR, TUC, LPG, CNG) contribute zero by construction where both sides are published; in policy_aligned_delayed the official side reprices its class leaves (including Heavy BEV) while the current side holds fixed components at published values, and that difference is carried explicitly in the stream gaps, not hidden. Unavailable official drivers (GDP, unemployment, fuel price, fleet-model internals, judgment) receive NO fabricated dollar attribution; see driver_availability_matrix.csv. Current population is the direct governed scenario input; the official population is derived from published outputs and labelled derived_from_official_outputs_not_independently_published.
