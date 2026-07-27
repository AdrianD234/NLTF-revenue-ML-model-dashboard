*  Petrol vehicle travel model - starter script
*
*  Optional. Run it if it saves you time, ignore it if you would rather
*  start from scratch with the data.
*
*  To run: put this file and ped-vkt-data.dta in the same folder, then
*
*      cd "that folder"
*      do run-in-stata.do
*
*  A note before you start. Our production model was fitted in Python.
*  Stata's own routines for this kind of model use slightly different
*  arithmetic, so your coefficients will land close to ours but not
*  identical. That is expected. The numbers in READ-ME-FIRST.txt are the
*  official ones. What follows is an independent check of whether the
*  specification holds up, not an attempt to match to the last decimal.

version 14
clear all
set more off

use "ped-vkt-data.dta", clear
tsset qdate, quarterly

*  The 95 quarters the model actually uses
keep if insample == 1

*  The right hand side, in the order we use it
local rhs lnpetrol lngdppc unemprate trend post2011trend post2020 covid2020 q2 q3 q4 lnvktpclag1


*  ---------------------------------------------------------------
*  1. Plain regression first, so you can see the raw picture
*  ---------------------------------------------------------------
regress lnvktpc `rhs'
estimates store plain


*  ---------------------------------------------------------------
*  2. The same thing, but allowing errors to carry over quarter to
*     quarter. This is the closest Stata equivalent of what we run.
*  ---------------------------------------------------------------
capture noisily prais lnvktpc `rhs'
if _rc == 0 {
    estimates store carryover
    display as text "Error carry-over estimated by Stata: " as result e(rho)
    display as text "Ours is 0.5233 - close is expected, identical is not."
}


*  ---------------------------------------------------------------
*  3. Side by side
*  ---------------------------------------------------------------
capture noisily estimates table plain carryover, b(%9.4f) se stats(N r2)


*  ---------------------------------------------------------------
*  4. Fitted values and residuals, if you want them for your own checks
*  ---------------------------------------------------------------
estimates restore plain
predict double fitted, xb
predict double resid, residuals

*  Everything past here is yours to drive. Diagnostics deliberately left
*  out - run whatever you normally would.

summarize fitted resid

*  If you want the residuals outside Stata:
*  export delimited period vktpc lnvktpc fitted resid using "my-residuals.csv", replace
