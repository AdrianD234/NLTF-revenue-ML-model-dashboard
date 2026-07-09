# Uptake shape lab - is the S-curve in the data?

## 1. Functional-form tournament (light BEV share of the light RUC pool)

Fit on 2001-2040 (history included), judged on held-out 2041-2050.

Base scenario (percentage points):

                    form  params  rmse_fit_pp  rmse_holdout_pp        aicc  pred_2050_pp
      logistic (S-curve)       3     0.723645         2.574319 -387.623312     79.299269
                   power       2     2.020498         4.968733 -307.821764     93.356835
               quadratic       3     2.155422         8.122450 -300.308031     99.986758
      Richards (S-curve)       4     0.371746        11.700548 -438.434394    104.324072
      Gompertz (S-curve)       3     0.350380        12.686669 -445.645825    106.171934
Bass diffusion (S-curve)       3     3.783329        20.372449 -255.298596     55.117075
                   cubic       4     0.338106        26.967255 -446.022427    132.872039
                  linear       2     8.593168        31.172929 -192.011897     48.498795
             exponential       2     1.920793        75.183399 -311.870254    226.715402

## 2. Growth-rate signature (no curve fitting)

s'/s regressed on s: linear decline is the structural signature of saturating
adoption; the x-intercept is the ceiling, the intercept the speed constant.
'proj' restricts to the projection era (2024+); 'all' includes the policy-era history.

scenario  r2_all  r2_proj  n_proj  ceiling_measured  ceiling_preset  speed_measured  speed_preset
 Base_EV   0.662    0.966      31             0.911           0.920           0.189         0.185
 Fast_EV   0.714    0.963      31             0.917           0.912           0.207         0.208
 Slow_EV   0.568    0.904      31             0.918           0.883           0.167         0.192

## 3. Stock-flow mechanism (VFM's own arithmetic)

fleet(t+1) = fleet(t) + turnover(t) x (new-entry share(t) - fleet(t)),
with turnover = light registrations / light stock, both from the VFM workbook.

- Base_EV: max |reconstruction - VFM fleet share| = 6.76 pp, mean bias -4.15 pp (mean turnover 7.8%/yr)
- Fast_EV: max |reconstruction - VFM fleet share| = 6.87 pp, mean bias -4.48 pp (mean turnover 8.0%/yr)
- Slow_EV: max |reconstruction - VFM fleet share| = 6.53 pp, mean bias -3.81 pp (mean turnover 7.6%/yr)

## 4. Observed New Zealand history (outside VFM)

MBU26 actual light BEV share: FY2024-FY2025, ending at 6.07%.

  FY  observed_pct  vfm_base_pct    gap_pp
2024      3.771601      5.943072 -2.171471
2025      6.065462      7.213194 -1.147731
