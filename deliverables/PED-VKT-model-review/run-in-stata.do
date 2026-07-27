*  Petrol vehicle travel model - starter script
*
*  Optional. Provided to save setup time only.
*
*      cd "<folder containing this file>"
*      do run-in-stata.do
*
*  The production model was fitted in Python using feasible GLS with AR(1)
*  errors. Stata's prais uses a different iteration scheme and a different
*  rho estimator, so coefficients will be close but not identical. The
*  official figures are in READ-ME-FIRST.txt.

version 14
clear all
set more off

use "ped-vkt-data.dta", clear
tsset qdate, quarterly
keep if insample == 1          //  95 quarters, 2002 Q2 to 2025 Q4

local rhs lnpetrol lngdppc unemprate trend post2011trend post2020 covid2020 q2 q3 q4 lnvktpclag1


*  OLS, no correction for serial correlation
regress lnvktpc `rhs'
estimates store ols


*  Feasible GLS with AR(1) errors - nearest Stata equivalent to production
capture noisily prais lnvktpc `rhs'
if _rc == 0 {
    estimates store ar1
    display as text "Stata rho: " as result e(rho) as text "   production rho: 0.5233"
}


*  Side by side
capture noisily estimates table ols ar1, b(%9.4f) se stats(N r2)


*  Fitted values and residuals for any further work
estimates restore ols
predict double fitted, xb
predict double resid, residuals
summarize fitted resid

*  export delimited period vktpc lnvktpc fitted resid using "residuals.csv", replace
