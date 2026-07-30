# Corrected MBU26 reconciliation (post-P0 baseline)

Current values are the real app-supported final stage (pack -> Treasury macro -> exact-VFM composition -> policy applied once) at merged main f8719f3. Official values are the MBU26 spine and its governed rate-only policy counterfactual.

## Headline

- **Policy-normalised model gap** (both sides published): within roughly **+-$62m** over FY2026-FY2030.
- **The actual default UI shows a much larger FY2027 difference** (-387.1m): the displayed Current trace is on the DELAYED policy while MBU26 remains PUBLISHED, so most of that gap is a policy-basis mismatch (-344.2m), not model performance.
- **The policy-aligned delayed comparison** removes that basis mismatch by delaying both sides (FY2027 gap -26.5m).
- None of these comparisons proves that either the current model or MBU26 is correct; they measure difference, not truth.

The earlier -8.7% figure was the **superseded pre-P0 stored-pack reconciliation**: it described the retired post-lambda pack layer, not the true former final front end, and must not be quoted as the pre-P0 model gap.

## policy_normalised

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   54.715 |   72.082 |  -17.366 |   -7.340 |    1.872 |    0.499 |  -12.400 | -6.03e-12 |
| 2027 |  -42.855 |    8.694 |  -51.549 |   -3.040 |   -2.271 |   -0.787 |  -44.825 | -6.42e-12 |
| 2028 |  -39.990 |    2.212 |  -42.202 |    9.308 |    4.696 |    1.060 |  -56.801 | 3.41e-13 |
| 2029 |  -29.346 |    5.910 |  -35.256 |   17.638 |   16.679 |    4.303 |  -73.514 | 6.82e-13 |
| 2030 |  -25.791 |   10.164 |  -35.955 |   13.541 |   32.655 |    8.428 |  -90.196 | 4.60e-12 |

## actual_default_ui

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   54.715 |   72.082 |  -17.366 |   -7.340 |    1.872 |    0.499 |  -12.400 | -6.03e-12 |
| 2027 | -387.060 | -158.497 | -228.563 |  -74.061 |  -11.085 |   -3.212 | -139.579 | -6.20e-12 |
| 2028 |  -39.990 |    2.212 |  -42.202 |    9.308 |    4.696 |    1.060 |  -56.801 | 3.41e-13 |
| 2029 |  -29.346 |    5.910 |  -35.256 |   17.638 |   16.679 |    4.303 |  -73.514 | 6.82e-13 |
| 2030 |  -25.791 |   10.164 |  -35.955 |   13.541 |   32.655 |    8.428 |  -90.196 | 4.60e-12 |

## policy_aligned_delayed

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   54.715 |   72.082 |  -17.366 |   -7.340 |    1.872 |    0.499 |  -12.400 | -6.03e-12 |
| 2027 |  -26.451 |   15.202 |  -41.653 |    0.420 |   -2.037 |   -0.710 |  -38.699 | -6.20e-12 |
| 2028 |  -39.990 |    2.212 |  -42.202 |    9.308 |    4.696 |    1.060 |  -56.801 | 3.41e-13 |
| 2029 |  -29.346 |    5.910 |  -35.256 |   17.638 |   16.679 |    4.303 |  -73.514 | 6.82e-13 |
| 2030 |  -25.791 |   10.164 |  -35.955 |   13.541 |   32.655 |    8.428 |  -90.196 | 4.60e-12 |

Fixed shared components (Heavy BEV under published, admin, refunds, MVR, TUC, LPG, CNG) contribute zero by construction where both sides are published; in policy_aligned_delayed the official side reprices its class leaves (including Heavy BEV) while the current side holds fixed components at published values, and that difference is carried explicitly in the stream gaps, not hidden. Unavailable official drivers (GDP, unemployment, fuel price, fleet-model internals, judgment) receive NO fabricated dollar attribution; see driver_availability_matrix.csv. Current population is the direct governed scenario input; the official population is derived from published outputs and labelled derived_from_official_outputs_not_independently_published.
