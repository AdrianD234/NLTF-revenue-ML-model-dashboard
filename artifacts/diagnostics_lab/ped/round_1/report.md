# Diagnostics Lab - PED - round 1

Finalist reference: `PED__VNEXT_SOLVED_CONVEX_TOP2` - paper horizon-mean MAPE 3.13% / annual 1.95% - core passes 4/6 - Overall Fail.

New candidates this round: 19; cumulative: 19.

Core-status key (DW/ADF/KPSS/BP/White/Coint): P=Pass F=Fail. JB is advisory.

| # | model | arm | core | status | JB | MAPE (paper) | vs finalist | annual | h1-4/5-8/9-12 |
|---|-------|-----|------|--------|----|--------------|-------------|--------|----------------|
| 1 | `PED__DIAGLAB__B__glsar__ar1__wexp__core` | B | 5/6 | FPPPPP | W | 2.90% | -0.23pp | 1.92% | 1.96%/2.34%/4.40% |
| 2 | `PED__DIAGLAB__B__glsar__ar2__wexp__core` | B | 5/6 | FPPPPP | W | 3.02% | -0.11pp | 2.34% | 1.96%/2.71%/4.40% |
| 3 | `PED__DIAGLAB__B__glsar__ar2__wexp__rich` | B | 5/6 | FPPPPP | W | 3.41% | +0.28pp | 2.39% | 2.07%/2.62%/5.55% |
| 4 | `PED__DIAGLAB__B__glsar__ar1__wexp__rich` | B | 5/6 | FPPPPP | W | 3.50% | +0.37pp | 2.34% | 2.09%/2.69%/5.74% |
| 5 | `PED__DIAGLAB__D__ecm__wexp` | D | 5/6 | FPPPPP | W | 3.99% | +0.86pp | 2.61% | 1.88%/2.31%/7.80% |
| 6 | `PED__DIAGLAB__D__ecm__w56` | D | 5/6 | FPPPPP | W | 4.02% | +0.88pp | 2.82% | 1.83%/2.61%/7.62% |
| 7 | `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[0,0,0,0]__wexp` | C | 3/6 | PFPPFF | W | 3.96% | +0.83pp | 2.97% | 1.73%/3.49%/6.66% |
| 8 | `PED__DIAGLAB__A__arx__ylag1-4__wexp__core` | A | 3/6 | FPPFFP | W | 3.99% | +0.86pp | 3.07% | 2.12%/3.15%/6.70% |
| 9 | `PED__DIAGLAB__A__arx__ylag1__wexp__core` | A | 3/6 | FPPFFP | W | 4.12% | +0.99pp | 3.07% | 1.99%/3.07%/7.30% |
| 10 | `PED__DIAGLAB__A__arx__ylag1-4__w56__core` | A | 3/6 | FPPFFP | W | 6.02% | +2.89pp | 5.22% | 2.41%/5.03%/10.61% |
| 11 | `PED__DIAGLAB__A__arx__ylag1__w56__core` | A | 3/6 | FPPFFP | W | 6.35% | +3.22pp | 5.54% | 2.35%/5.14%/11.57% |
| 12 | `PED__DIAGLAB__A__arx__ylag1-4__w56__rich` | A | 3/6 | FPPFFP | W | 7.92% | +4.79pp | 6.62% | 2.37%/5.27%/16.12% |
| 13 | `PED__DIAGLAB__A__arx__ylag1__w56__rich` | A | 3/6 | FPPFFP | W | 9.23% | +6.10pp | 7.73% | 2.26%/5.72%/19.72% |
| 14 | `PED__DIAGLAB__A__arx__ylag1-4__wexp__rich` | A | 3/6 | FPPFFP | W | 12.05% | +8.92pp | 10.16% | 2.21%/7.16%/26.79% |
| 15 | `PED__DIAGLAB__A__arx__ylag1__wexp__rich` | A | 3/6 | FPPFFP | W | 12.77% | +9.63pp | 10.76% | 2.05%/7.21%/29.03% |
| 16 | `PED__DIAGLAB__C__sarimax__order[2,0,0]_seasonal[0,0,0,0]__wexp` | C | 2/6 | PFPFFF | W | 4.00% | +0.87pp | 2.99% | 1.81%/3.50%/6.70% |
| 17 | `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[1,0,0,4]__wexp` | C | 1/6 | FFPFFF | W | 3.94% | +0.81pp | 2.97% | 1.63%/3.53%/6.66% |
| 18 | `PED__DIAGLAB__C__sarimax__order[1,0,1]_seasonal[0,0,0,0]__wexp` | C | 1/6 | FFPFFF | W | 4.07% | +0.94pp | 3.02% | 1.83%/3.43%/6.96% |
| 19 | `PED__DIAGLAB__C__sarimax__order[1,0,1]_seasonal[1,0,0,4]__wexp` | C | 1/6 | FFPFFF | W | 4.11% | +0.98pp | 3.08% | 1.65%/3.56%/7.12% |

## Arm summary

- **A** (8 configs): best 3/6 core [FPPFFP] at 3.99% - `PED__DIAGLAB__A__arx__ylag1-4__wexp__core`
- **B** (4 configs): best 5/6 core [FPPPPP] at 2.90% - `PED__DIAGLAB__B__glsar__ar1__wexp__core`
- **C** (5 configs): best 3/6 core [PFPPFF] at 3.96% - `PED__DIAGLAB__C__sarimax__order[1,0,0]_seasonal[0,0,0,0]__wexp`
- **D** (2 configs): best 5/6 core [FPPPPP] at 3.99% - `PED__DIAGLAB__D__ecm__wexp`

## Headline

No all-core-pass candidate yet.