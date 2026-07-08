# Diagnostics Lab - LIGHT_RUC - round 1

Finalist reference: `dynamic_RESID_GBR_n150_d1_lr0.05_w36` - paper horizon-mean MAPE 5.36% / annual 1.27% - core passes 6/6 - Overall Watch.

New candidates this round: 16; cumulative: 16.

Core-status key (DW/ADF/KPSS/BP/White/Coint): P=Pass F=Fail. JB is advisory.

| # | model | arm | core | status | JB | DW | LB8 p | MAPE (paper) | vs finalist | annual | h1-4/5-8/9-12 |
|---|-------|-----|------|--------|----|----|-------|--------------|-------------|--------|----------------|
| 1 | `LIGHT_RUC__DIAGLAB__A__arx__w36__pulse__base` | A | 6/6 | PPPPPP | P | 1.57 | 0.423 | 8.34% | +2.97pp | 5.79% | 5.19%/6.71%/13.12% |
| 2 | `LIGHT_RUC__DIAGLAB__B__glsar__ar1__w36__pulse__base` | B | 6/6 | PPPPPP | P | 1.64 | 0.126 | 11.50% | +6.14pp | 8.75% | 5.98%/11.50%/17.03% |
| 3 | `LIGHT_RUC__DIAGLAB__B__glsar__ar1__wexp__base` | B | 6/6 | PPPPPP | P | 1.59 | 0.237 | 11.73% | +6.37pp | 7.26% | 5.40%/9.78%/20.02% |
| 4 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w36` | R | 6/6 | PPPPPP | W | 1.84 | 0.087 | 5.42% | +0.05pp | 2.28% | 4.25%/3.94%/8.06% |
| 5 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w36__pulse` | R | 6/6 | PPPPPP | W | 1.91 | 0.056 | 5.42% | +0.05pp | 2.28% | 4.25%/3.94%/8.06% |
| 6 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w36__covid_down` | R | 6/6 | PPPPPP | W | 1.79 | 0.055 | 5.46% | +0.10pp | 2.13% | 4.32%/4.18%/7.89% |
| 7 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w36__covid_down__pulse` | R | 6/6 | PPPPPP | W | 1.87 | 0.040 | 5.46% | +0.10pp | 2.13% | 4.32%/4.18%/7.89% |
| 8 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w44` | R | 6/6 | PPPPPP | W | 1.61 | 0.111 | 7.09% | +1.72pp | 2.59% | 4.19%/5.42%/11.65% |
| 9 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w44__pulse` | R | 6/6 | PPPPPP | W | 1.62 | 0.108 | 7.20% | +1.84pp | 2.70% | 4.19%/5.63%/11.79% |
| 10 | `LIGHT_RUC__DIAGLAB__A__arx__w36__base` | A | 5/6 | PPPPFP | P | 1.56 | 0.556 | 8.34% | +2.97pp | 5.79% | 5.19%/6.71%/13.12% |
| 11 | `LIGHT_RUC__DIAGLAB__B__glsar__ar1__w36__base` | B | 5/6 | PPPPFP | P | 1.64 | 0.165 | 11.50% | +6.14pp | 8.75% | 5.98%/11.50%/17.03% |
| 12 | `LIGHT_RUC__DIAGLAB__R__light_recipe__w36__regime_var` | R | 5/6 | PFPPPP | W | 1.77 | 0.015 | 5.39% | +0.03pp | 2.09% | 4.24%/4.16%/7.77% |
| 13 | `LIGHT_RUC__DIAGLAB__A__arx__ylag1__w36__pulse__base` | A | 4/6 | PPPFFP | W | 1.87 | 0.166 | 11.02% | +5.65pp | 8.04% | 6.63%/9.50%/16.93% |
| 14 | `LIGHT_RUC__DIAGLAB__A__arx__ylag1__w36__base` | A | 4/6 | PPPFFP | W | 1.87 | 0.156 | 11.07% | +5.70pp | 8.08% | 6.62%/9.52%/17.05% |
| 15 | `LIGHT_RUC__DIAGLAB__A__arx__wexp__base` | A | 4/6 | PPPFFP | W | 1.75 | 0.152 | 11.40% | +6.03pp | 6.18% | 7.02%/10.42%/16.75% |
| 16 | `LIGHT_RUC__DIAGLAB__A__arx__ylag1__wexp__base` | A | 4/6 | PPPFFP | W | 1.89 | 0.142 | 11.90% | +6.54pp | 9.10% | 5.98%/10.74%/18.97% |

## Arm summary

- **A** (6 configs): best 6/6 core [PPPPPP] at 8.34% - `LIGHT_RUC__DIAGLAB__A__arx__w36__pulse__base`
- **B** (3 configs): best 6/6 core [PPPPPP] at 11.50% - `LIGHT_RUC__DIAGLAB__B__glsar__ar1__w36__pulse__base`
- **R** (7 configs): best 6/6 core [PPPPPP] at 5.42% - `LIGHT_RUC__DIAGLAB__R__light_recipe__w36`

## Headline

Best all-core-pass candidate: `LIGHT_RUC__DIAGLAB__A__arx__w36__pulse__base` at 8.34% (+2.97pp vs finalist).