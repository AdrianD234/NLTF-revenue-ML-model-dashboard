# Corrected MBU26 reconciliation (post-P0 baseline)

Current values are the real app-supported final stage (pack -> Treasury macro -> exact-VFM composition -> policy applied once) at merged main f8719f3. Official values are the MBU26 spine and its governed rate-only policy counterfactual.

## Headline

- **Policy-normalised model gap** (both sides published): within roughly **+-$62m** over FY2026-FY2030.
- **The actual default UI shows a much larger FY2027 difference** (-402.2m): the displayed Current trace is on the DELAYED policy while MBU26 remains PUBLISHED, so most of that gap is a policy-basis mismatch (-342.9m), not model performance.
- **The policy-aligned delayed comparison** removes that basis mismatch by delaying both sides (FY2027 gap -41.6m).
- None of these comparisons proves that either the current model or MBU26 is correct; they measure difference, not truth.

The earlier -8.7% figure was the **superseded pre-P0 stored-pack reconciliation**: it described the retired post-lambda pack layer, not the true former final front end, and must not be quoted as the pre-P0 model gap.

## policy_normalised

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   61.676 |   72.082 |  -10.405 |    3.708 |    2.935 |    0.784 |  -17.833 | -6.48e-12 |
| 2027 |  -59.264 |    8.694 |  -67.958 |  -16.661 |   -3.898 |   -1.234 |  -45.539 | -6.88e-12 |
| 2028 |  -40.190 |    2.212 |  -42.402 |    9.308 |    4.696 |    1.060 |  -57.001 | 3.41e-13 |
| 2029 |  -29.345 |    5.910 |  -35.255 |   17.638 |   16.679 |    4.303 |  -73.513 | 1.14e-12 |
| 2030 |  -25.791 |   10.164 |  -35.955 |   13.541 |   32.655 |    8.428 |  -90.196 | 4.15e-12 |

## actual_default_ui

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   61.676 |   72.082 |  -10.405 |    3.708 |    2.935 |    0.784 |  -17.833 | -6.48e-12 |
| 2027 | -402.184 | -158.497 | -243.687 |  -86.613 |  -12.584 |   -3.625 | -140.239 | -7.11e-12 |
| 2028 |  -40.190 |    2.212 |  -42.402 |    9.308 |    4.696 |    1.060 |  -57.001 | 3.41e-13 |
| 2029 |  -29.345 |    5.910 |  -35.255 |   17.638 |   16.679 |    4.303 |  -73.513 | 1.14e-12 |
| 2030 |  -25.791 |   10.164 |  -35.955 |   13.541 |   32.655 |    8.428 |  -90.196 | 4.15e-12 |

## policy_aligned_delayed

| FY | NLTF gap | Net FED | Total RUC | of which Lt conv | Lt BEV | PHEV | Heavy | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 |   61.676 |   72.082 |  -10.405 |    3.708 |    2.935 |    0.784 |  -17.833 | -6.48e-12 |
| 2027 |  -41.575 |   15.202 |  -56.777 |  -12.132 |   -3.537 |   -1.122 |  -39.359 | -7.11e-12 |
| 2028 |  -40.190 |    2.212 |  -42.402 |    9.308 |    4.696 |    1.060 |  -57.001 | 3.41e-13 |
| 2029 |  -29.345 |    5.910 |  -35.255 |   17.638 |   16.679 |    4.303 |  -73.513 | 1.14e-12 |
| 2030 |  -25.791 |   10.164 |  -35.955 |   13.541 |   32.655 |    8.428 |  -90.196 | 4.15e-12 |

Fixed shared components (Heavy BEV under published, admin, refunds, MVR, TUC, LPG, CNG) contribute zero by construction where both sides are published; in policy_aligned_delayed the official side reprices its class leaves (including Heavy BEV) while the current side holds fixed components at published values, and that difference is carried explicitly in the stream gaps, not hidden. Unavailable official drivers (GDP, unemployment, fuel price, fleet-model internals, judgment) receive NO fabricated dollar attribution; see driver_availability_matrix.csv. Current population is the direct governed scenario input; the official population is derived from published outputs and labelled derived_from_official_outputs_not_independently_published.
