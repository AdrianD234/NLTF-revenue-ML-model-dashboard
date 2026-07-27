*! replicate_ped_ar1.do
*! Independent specification check for the PED VKT-per-capita AR(1) model.
*!
*! Run from the extracted package folder. All paths are relative.
*!
*!   cd "<extracted folder>"
*!   do replicate_ped_ar1.do
*!
*! IMPORTANT: Stata's Prais-Winsten / Cochrane-Orcutt will NOT be bit-identical
*! to statsmodels GLSAR iterative_fit. The authoritative production
*! coefficients are supplied in ped_ar1_production_coefficients.csv and the
*! production fitted values in ped_ar1_training_reference.csv. What follows is
*! an INDEPENDENT check of whether the specification is sound, not an attempt
*! to reproduce the production numbers to the last digit.

version 14
clear all
set more off
capture mkdir results
log using "results/replicate_ped_ar1.log", replace text

*-----------------------------------------------------------------------
* 1. Load and declare the time series
*-----------------------------------------------------------------------
use "ped_ar1_estimation_data.dta", clear
tsset qdate, quarterly
describe
summarize

*-----------------------------------------------------------------------
* 2. Regenerate every transformation from raw columns and assert equality
*    against the supplied ones. If these assertions fail, the pack and the
*    documentation disagree - stop and report it.
*-----------------------------------------------------------------------
gen double chk_ln_vktpc   = ln(vktpc)
gen double chk_ln_petrol  = ln(petrol_real_cpl)
gen double chk_ln_gdp_pc  = ln(gdp_pc_real)
gen double chk_ln_lag     = L.chk_ln_vktpc
gen double chk_post2011_t = post2011 * trend

* unemp_rate is a DECIMAL FRACTION (0.053 = 5.3%), not percentage points.
gen double chk_unemp      = unemp_pct / 100

foreach v in ln_vktpc ln_petrol ln_gdp_pc {
    gen double d_`v' = abs(chk_`v' - `v')
    quietly summarize d_`v' if estimation_sample == 1
    display as text "max |chk_`v' - `v'| = " as result r(max)
    assert r(max) < 1e-9 if estimation_sample == 1
}
quietly summarize d_ln_vktpc if estimation_sample == 1
gen double d_lag = abs(chk_ln_lag - ln_vktpc_l1)
quietly summarize d_lag if estimation_sample == 1
display as text "max |chk lag - supplied lag| = " as result r(max)
assert r(max) < 1e-9 if estimation_sample == 1

gen double d_p11 = abs(chk_post2011_t - post2011_trend)
quietly summarize d_p11 if estimation_sample == 1
assert r(max) < 1e-9 if estimation_sample == 1

gen double d_un = abs(chk_unemp - unemp_rate)
quietly summarize d_un if estimation_sample == 1
display as text "max |unemp_pct/100 - unemp_rate| = " as result r(max)
assert r(max) < 1e-9 if estimation_sample == 1

display as text "All transformation checks passed."

*-----------------------------------------------------------------------
* 3. The regressor list, in production order
*-----------------------------------------------------------------------
local X ln_petrol ln_gdp_pc unemp_rate trend post2011_trend post2020 covid2020 q2 q3 q4
local XL `X' ln_vktpc_l1

*-----------------------------------------------------------------------
* 4. Estimations
*-----------------------------------------------------------------------

* (a) Dynamic OLS benchmark - no AR(1) error correction.
regress ln_vktpc `XL' if estimation_sample == 1
estimates store ols_dynamic
estat ic
predict double fit_ols if e(sample), xb
predict double res_ols if e(sample), residuals

* (b) Prais-Winsten - closest widely available analogue to GLSAR AR(1).
capture noisily prais ln_vktpc `XL' if estimation_sample == 1, rhotype(regress)
if _rc == 0 {
    estimates store prais_pw
    display as text "Prais-Winsten rho = " as result e(rho)
}

* (c) Cochrane-Orcutt robustness variant.
capture noisily prais ln_vktpc `XL' if estimation_sample == 1, corc rhotype(regress)
if _rc == 0 estimates store prais_corc

* (d) ARIMA with AR(1) errors - a third route to the same structure.
capture noisily arima ln_vktpc `XL' if estimation_sample == 1, ar(1)
if _rc == 0 estimates store arima_ar1

*-----------------------------------------------------------------------
* 5. Compact coefficient comparison
*-----------------------------------------------------------------------
capture noisily estimates table ols_dynamic prais_pw prais_corc arima_ar1, ///
    b(%9.6f) se star stats(N r2 ll)

*-----------------------------------------------------------------------
* 6. Diagnostics on the dynamic OLS residuals
*
*    NOTE: the governed diagnostic battery in the repository is computed on
*    HORIZON-1 ROLLING-ORIGIN FORECAST residuals, not on these in-sample
*    regression residuals. See ped_ar1_diagnostic_pairs_h1.csv. The two are
*    not interchangeable; both are informative.
*-----------------------------------------------------------------------
estimates restore ols_dynamic

* Serial correlation. Durbin's alternative is appropriate with a lagged
* dependent variable; Durbin-Watson is biased toward 2 in that case.
capture noisily estat durbinalt, lags(1 4 8)
capture noisily estat dwatson
capture noisily wntestq res_ols, lags(4)
capture noisily wntestq res_ols, lags(8)
capture noisily wntestq res_ols, lags(12)

* Heteroskedasticity.
capture noisily estat hettest, rhs
capture noisily estat imtest, white

* ARCH.
capture noisily estat archlm, lags(1 4)

* Normality.
capture noisily sktest res_ols
capture noisily swilk res_ols

* Unit roots on the levels used in the equation.
foreach v in ln_vktpc ln_petrol ln_gdp_pc unemp_rate {
    display as text _n "=== ADF: `v' ==="
    capture noisily dfuller `v' if estimation_sample == 1, trend lags(4)
}

* KPSS needs a community package; skip gracefully if absent.
capture which kpss
if _rc {
    display as text "kpss not installed - skipping. To add it: ssc install kpss"
}
else {
    foreach v in ln_vktpc ln_petrol ln_gdp_pc {
        capture noisily kpss `v' if estimation_sample == 1, maxlag(8)
    }
}

*-----------------------------------------------------------------------
* 7. Mincer-Zarnowitz style calibration on in-sample fitted values
*    (actual = a + b*fitted; sound calibration implies a=0, b=1)
*-----------------------------------------------------------------------
capture noisily regress ln_vktpc fit_ols if estimation_sample == 1
capture noisily test (_cons = 0) (fit_ols = 1)

*-----------------------------------------------------------------------
* 8. Export
*-----------------------------------------------------------------------
capture noisily estimates restore ols_dynamic
capture noisily estimates save "results/ols_dynamic.ster", replace
capture noisily estimates restore prais_pw
capture noisily estimates save "results/prais_pw.ster", replace

preserve
    keep if estimation_sample == 1
    keep period vktpc ln_vktpc fit_ols res_ols
    export delimited using "results/stata_fitted_residuals.csv", replace
restore

display as text _n "Done. Outputs in results/."
log close
