# Diagnostics Lab - PED - round 2

Finalist reference: `PED__VNEXT_SOLVED_CONVEX_TOP2` - paper horizon-mean MAPE 3.13% / annual 1.95% - core passes 4/6 - Overall Fail.

New candidates this round: 10; cumulative: 29.

Core-status key (DW/ADF/KPSS/BP/White/Coint): P=Pass F=Fail. JB is advisory.

| # | model | arm | core | status | JB | DW | LB8 p | MAPE (paper) | vs finalist | annual | h1-4/5-8/9-12 |
|---|-------|-----|------|--------|----|----|-------|--------------|-------------|--------|----------------|
| 1 | `PED__DIAGLAB__B__glsar__ylag1__ar1__wexp` | B | 6/6 | PPPPPP | W | 1.56 | 0.176 | 3.22% | +0.09pp | 2.17% | 1.89%/2.35%/5.43% |
| 2 | `PED__DIAGLAB__B__glsar__ylag1-4__ar1__wexp` | B | 6/6 | PPPPPP | W | 1.51 | 0.183 | 3.51% | +0.38pp | 2.43% | 1.94%/2.43%/6.16% |
| 3 | `PED__DIAGLAB__D__ecm__dylag1__wexp` | D | 6/6 | PPPPPP | W | 1.91 | 0.042 | 3.58% | +0.45pp | 2.56% | 1.95%/2.57%/6.22% |
| 4 | `PED__DIAGLAB__B__glsar__ar1__wexp__core` | B | 5/6 | FPPPPP | W | 1.31 | 0.054 | 2.90% | -0.23pp | 1.92% | 1.96%/2.34%/4.40% |
| 5 | `PED__DIAGLAB__B__glsar__ar2__wexp__core` | B | 5/6 | FPPPPP | W | 1.37 | 0.015 | 3.02% | -0.11pp | 2.34% | 1.96%/2.71%/4.40% |
| 6 | `PED__DIAGLAB__B__glsar__ar2__wexp` | B | 5/6 | FPPPPP | W | 1.37 | 0.015 | 3.02% | -0.11pp | 2.34% | 1.96%/2.71%/4.40% |
| 7 | `PED__DIAGLAB__B__glsar__ar1__wexp__pulse` | B | 5/6 | FPPPPP | W | 1.24 | 0.013 | 3.03% | -0.10pp | 2.17% | 1.93%/2.55%/4.62% |
| 8 | `PED__DIAGLAB__B__glsar__ar1__w56` | B | 5/6 | FPPPPP | W | 1.30 | 0.046 | 3.24% | +0.11pp | 2.24% | 1.99%/2.67%/5.06% |
| 9 | `PED__DIAGLAB__B__glsar__ar2__wexp__rich` | B | 5/6 | FPPPPP | W | 1.15 | 0.002 | 3.41% | +0.28pp | 2.39% | 2.07%/2.62%/5.55% |
| 10 | `PED__DIAGLAB__B__glsar__ar1__wexp__rich` | B | 5/6 | FPPPPP | W | 1.11 | 0.026 | 3.50% | +0.37pp | 2.34% | 2.09%/2.69%/5.74% |
| 11 | `PED__DIAGLAB__D__ecm__wexp` | D | 5/6 | FPPPPP | W | 1.47 | 0.038 | 3.99% | +0.86pp | 2.61% | 1.88%/2.31%/7.80% |
| 12 | `PED__DIAGLAB__D__ecm__w56` | D | 5/6 | FPPPPP | W | 1.42 | 0.045 | 4.02% | +0.88pp | 2.82% | 1.83%/2.61%/7.62% |
| 13 | `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[0,0,0,0]__wexp` | C | 3/6 | PFPPFF | W | 1.55 | 0.003 | 3.96% | +0.83pp | 2.97% | 1.73%/3.49%/6.66% |
| 14 | `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[0,0,0,0]__wexp__covid_down` | C | 3/6 | PFPPFF | W | 1.55 | 0.003 | 3.96% | +0.83pp | 2.97% | 1.73%/3.49%/6.66% |
| 15 | `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[0,0,0,0]__wexp__regime_var` | C | 3/6 | PFPPFF | W | 1.55 | 0.003 | 3.96% | +0.83pp | 2.97% | 1.73%/3.49%/6.66% |
| 16 | `PED__DIAGLAB__A__arx__ylag1-4__wexp__core` | A | 3/6 | FPPFFP | W | 1.34 | 0.022 | 3.99% | +0.86pp | 3.07% | 2.12%/3.15%/6.70% |
| 17 | `PED__DIAGLAB__A__arx__ylag1__wexp__core` | A | 3/6 | FPPFFP | W | 1.28 | 0.015 | 4.12% | +0.99pp | 3.07% | 1.99%/3.07%/7.30% |
| 18 | `PED__DIAGLAB__A__arx__ylag1-4__wexp__covid_down` | A | 3/6 | FPPFFP | W | 1.46 | 0.022 | 4.15% | +1.01pp | 3.31% | 2.26%/3.51%/6.67% |
| 19 | `PED__DIAGLAB__A__arx__ylag1-4__wexp__regime_var` | A | 3/6 | FPPFFP | W | 1.43 | 0.019 | 4.15% | +1.02pp | 3.29% | 2.28%/3.54%/6.64% |
| 20 | `PED__DIAGLAB__A__arx__ylag1-4__w56__core` | A | 3/6 | FPPFFP | W | 1.42 | 0.212 | 6.02% | +2.89pp | 5.22% | 2.41%/5.03%/10.61% |

## Arm summary

- **A** (10 configs): best 3/6 core [FPPFFP] at 3.99% - `PED__DIAGLAB__A__arx__ylag1-4__wexp__core`
- **B** (9 configs): best 6/6 core [PPPPPP] at 3.22% - `PED__DIAGLAB__B__glsar__ylag1__ar1__wexp`
- **C** (7 configs): best 3/6 core [PFPPFF] at 3.96% - `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[0,0,0,0]__wexp`
- **D** (3 configs): best 6/6 core [PPPPPP] at 3.58% - `PED__DIAGLAB__D__ecm__dylag1__wexp`

## Headline

Best all-core-pass candidate: `PED__DIAGLAB__B__glsar__ylag1__ar1__wexp` at 3.22% (+0.09pp vs finalist).