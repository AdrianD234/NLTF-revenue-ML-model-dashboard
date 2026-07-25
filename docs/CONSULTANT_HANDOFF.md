# Consultant handoff — the MoT-shape question

> **Latest continuation (25 July 2026):** for the Treasury BEFU26 baseline,
> Middle East conflict fuel/GDP scenarios, 12 c/L Original/Deferred/Off policy
> matrix, reconciliation fixes and final validation, continue with
> [`CONSULTANT_HANDOFF_TREASURY_CONFLICT_SCENARIOS_2026-07-25.md`](CONSULTANT_HANDOFF_TREASURY_CONFLICT_SCENARIOS_2026-07-25.md).

**Repo:** https://github.com/AdrianD234/NLTF-revenue-ML-model-dashboard (branch `main`)
**Prepared:** 11 July 2026
**Scope of this document:** the line of work that connects our revenue model's EV/PHEV
fleet-transition assumptions to the Ministry of Transport's models (VFM 202405 and MBU26),
what evidence stands behind that connection, every commit in the trail, and what has been
attempted so far — including the approaches we retired.

---

## 1. What we are trying to achieve

We forecast NLTF revenue (fuel excise, road user charges, registration, track user charges)
with our own statistical models. Three activity streams are modelled directly — petrol
travel per person (PED), light RUC kilometres, heavy RUC kilometres — and everything else
(class mix, fuel intensity, effective rates, non-modelled lines) is taken from MoT's
published MBU26 baseline so results are like-for-like comparable with the official numbers.

The contested piece is the **electric-vehicle transition**: how the light fleet's travel
splits over time between petrol, conventional RUC (diesel), battery-electric and plug-in
hybrid vehicles. That split reshapes revenue materially (BEV km earn RUC; petrol km earn
excise), so its trajectory must be:

1. **traceable to MoT** — our numbers should map onto MoT's own projections
   (VFM 202405 scenarios; MBU26 official class mix), row by row;
2. **independent of MoT's internal machinery** — we do not adopt their weights,
   allocation functions, or any parameter we cannot explain; and
3. **defensible in its own right** — the S-shaped adoption curve we use must be shown to
   be a property of the data, not an artefact of choosing a formula that happens to fit
   ("with enough coefficients you can mimic anything").

Objectives 1 and 2 are delivered by the glass-box Excel walkthrough (section 5). Objective 3
is delivered by the uptake shape lab (section 6). The dashboard consumes the same curves.

## 2. Background: why the λ-migration framing was retired

The runtime data pipeline needs to allocate each year's EV/PHEV kilometres between two
modelled pools (the petrol pool and the light-RUC pool) so the combined class mix matches
MBU26. The original implementation did this with a fitted allocation parameter, λ, chosen
by a smoothness-penalised optimisation. It works and remains inside the committed pipeline
as the pack-construction mechanism — but as a *story* it was indefensible in front of an
external audience: an optimiser's output presented as an assumption.

Two moves replaced it as the user-facing rationale:

- **The uptake lever engine** (commits `283e5fa`, `373d334`): the dashboard's EV
  transition is driven by named, plain-language dials (peak uptake speed, year of fastest
  uptake, 2050 share, ...) whose preset values track MoT's VFM 202405 Base/Fast/Slow
  scenarios. λ was retired from the UI in `2577388`.
- **The explicit-assumption presentation** (commit `35a8c6e`): in the Excel walkthrough,
  the allocation appears as one readable assumption column ("EV switch drawn from RUC
  pool") with a per-year check showing the resulting mix stays within a fraction of a
  share point of MoT's official proportions.

## 3. The current defensibility argument, in one page

The obvious critique of the lever engine: the dials parameterise a logistic S-curve fitted
to VFM's outputs, and *a fitted curve proves nothing*. The shape lab answers with four
falsifiable tests, none of which involves our formula:

| # | Test | Result | Where to see it |
|---|------|--------|-----------------|
| 1 | **Growth-rate signature** (no fitting): saturating adoption implies the relative growth rate falls linearly as the share rises; the line's intercept/x-intercept ARE the speed and ceiling | R² = 0.96 (base), 0.96 (fast), 0.90 (slow); measured speed/ceiling 0.191/0.902 vs our dials 0.185/0.920 | Workbook sheet 3, computed live in-cell with SLOPE/INTERCEPT/RSQ; `artifacts/uptake_shape_lab/growth_rate_regression.csv` |
| 2 | **Form tournament**: nine functional forms fit on 2001–2040, judged on the unseen 2041–2050 decade | In-sample champions (cubic 0.34pp, Gompertz 0.35pp, Richards 0.37pp) miss the holdout by 12–27pp; the logistic holds both (0.72pp fit, 2.6pp holdout); exponential misses by 75pp | Workbook sheet 3; `artifacts/uptake_shape_lab/tournament_light_bev_*.csv` |
| 3 | **Mechanism** (no curve at all): from a single 2023 seed, integrate MoT's own new-registration mix through ~8%/yr fleet turnover | Reproduces the 30-year S within ~7pp, biased low exactly as neutral scrappage predicts | Workbook sheet 3 as a live Excel recursion; `artifacts/uptake_shape_lab/stock_flow_*.csv` |
| 4 | **Observed outturns** (outside VFM): NZ's actual light BEV shares from MBU26 actuals | FY2024 3.8% and FY2025 6.1% sit on the projected toe, gap closing (−2.2pp → −1.1pp). Only two points exist (MBU26 splits the BEV class from FY2024) — honestly a consistency check that strengthens annually | Workbook sheet 3; `artifacts/uptake_shape_lab/observed_vs_vfm.csv` |

The consequent framing shift: **the dials are measurements of MoT's series, not free
coefficients** — the growth-rate line's endpoints agree with the dial values — and the
S-shape itself is fleet-turnover arithmetic, corroborated by the technology-substitution
literature (Fisher & Pry 1971) and by fleets further along the curve (Norway).

Known honest edges: the slow scenario's signature is weaker (R² 0.90; measured ceiling
0.918 vs dial 0.883); the mechanism test is neutral-scrappage (hence the documented ~4pp
mean undershoot); only two observed NZ points exist so far.

## 4. How to read the commit trail

Each commit message is written as a self-contained explanation — read them with
`git log`, `git show <hash>`, or on GitHub at
`https://github.com/AdrianD234/NLTF-revenue-ML-model-dashboard/commit/<hash>`.
Suggested reading order (chronological by theme):

### Chapter 1 — grounding the EV transition in MoT's VFM

| Commit | Title | What to look at |
|--------|-------|-----------------|
| `2a9f64f` | Add PED-Light EV migration audit | The original λ-migration allocation, fully audited (`ev_phev_ped_light_drift_assumptions.csv`) |
| `283e5fa` | EV/PHEV uptake lever engine grounded in MoT VFM 202405 | Vendors the MoT workbook (SHA-pinned), extracts scenario VKT shares (`scripts/extract_vfm_uptake_shares.py` → `data/vfm_202405/`), introduces the dial engine (`model_dashboard/ev_uptake_levers.py`) |
| `373d334` | Extend uptake levers to PED petrol displacement and heavy BEV share | The other two curves the dashboard bends |
| `c808727` | Decompose PED into activity × intensity | Why the levers and the Fleet-efficiency sensitivity compose without double counting |
| `2577388` | Default EV uptake basis to MoT VFM base; retire λ-migration from the UI | The framing pivot: λ becomes internal machinery only |
| `690a5dd` | MoT VFM fleet-transition cone | Fast/slow scenarios rendered as an uncertainty envelope on the dashboard |
| `b702173` | e-RUC transition simulator | Petrol fleet migrating from excise to RUC as a what-if lever |

### Chapter 2 — glass-box transparency end to end

| Commit | Title | What to look at |
|--------|-------|-----------------|
| `8355d2b` | Glass-box diagnostic drilldown | The same transparency philosophy applied to model diagnostics |
| `1718b83` / `782cc69` | AR(1) engine as default (+ restore merge) | The production PED model the workbook reconciles against (all six core diagnostics pass) |
| `35a8c6e` | **Glass-box Excel walkthrough: VFM assumptions to dashboard revenue** | `deliverables/NLTF_revenue_glass_box.xlsx` + `scripts/build_glass_box_workbook.py`. Nine sheets from MoT sources to NLTF revenue, every derived cell an Excel formula, MBU26 source cells quoted per line, reconciliation to the dashboard exact (sheet 8) |

### Chapter 3 — defending the shape itself

| Commit | Title | What to look at |
|--------|-------|-----------------|
| `f04f05a` | **Uptake shape lab: prove the S-curve is in the data, not the formula** | `scripts/uptake_shape_lab.py`, `artifacts/uptake_shape_lab/` (all CSVs + `report.md`), and the rebuilt workbook sheet 3 ("Why an S-curve") |
| `5886e6b` | Uptake help text leads with the measured-shape evidence | Dashboard tooltip now cites the evidence rather than the fit |

## 5. Deliverable 1 — the glass-box workbook

`deliverables/NLTF_revenue_glass_box.xlsx` (regenerate with
`scripts/build_glass_box_workbook.py`; requires `scripts/uptake_shape_lab.py` run first).

Sheet map: **1** Read me (colour code: blue = sourced input with source cell quoted,
black = same-sheet formula, green = cross-sheet link; SHA-pinned provenance);
**2** MoT VFM curves (official scenario shares, straight from the vendored workbook);
**3** Why an S-curve (the four tests, then the dials); **4** Engine forecasts (quarterly
model outputs + population); **5** Light fleet split (pool → MBU26 class mix → class km,
identity checks); **6** Rates & revenue (every rate = MoT revenue ÷ MoT volume, so the
legislated FY2027 +6c / FY2028 +12c duty steps are embedded); **7** NLTF rollup;
**8** Reconciliation (12 series × 25 years vs the committed dashboard pack — every
difference exactly zero, verdict cell reads MATCH); **9** Mapping & glossary.

Verification levels: the builder's Python mirror reproduces the committed pack to ~4e-12
before writing; a forced LibreOffice full recalculation reports zero formula errors; the
recalculated reconciliation deltas are exactly zero.

## 6. Deliverable 2 — the uptake shape lab

`scripts/uptake_shape_lab.py` → `artifacts/uptake_shape_lab/` (committed):
`report.md` (summary), `tournament_light_bev_{Base,Fast,Slow}_EV.csv`,
`growth_rate_regression.csv` + per-scenario point files, `stock_flow_*.csv`,
`observed_nz_bev_share.csv`, `observed_vs_vfm.csv`. Section 3's table summarises the
results; the CSVs carry every underlying number.

## 7. What has been attempted, in order (including retired approaches)

1. **λ-migration as the presented rationale** — retired for presentation (kept as internal
   pack machinery). A smoothness-penalised optimiser is not an assumption anyone can defend.
2. **Fixed MBU26 add-on split** (`ev_phev_split_assumptions.csv`) — superseded; retained
   in the packs as a legacy comparator audit.
3. **Preset dials fitted to VFM scenarios** — the current dashboard mechanism, but the
   original *justification* ("reproduces the official curves within ~1.5pp") was
   correctly challenged as curve-mimicry. Retained, reframed by (5).
4. **Glass-box workbook** — mapping and auditability solved: every number from MoT source
   cell to dashboard revenue in linked formulas, reconciling exactly.
5. **Shape lab** — the defensibility gap closed with four formula-free tests
   (section 3). The dials are now presented as measured properties of MoT's own series.
6. **Not pursued (yet):** vendoring international adoption datasets (e.g. Norway's fleet
   statistics) for a hash-pinned external overlay — cited qualitatively instead; an
   age-structured scrappage version of the mechanism test (would tighten the ~7pp gap);
   applying the same evidence battery to the PHEV hump and heavy-BEV curves (the lab
   currently runs the battery on the primary light-BEV curve; PHEV/heavy are covered by
   the preset-vs-VFM gap table only).

## 7a. A definitional trap, pre-cleared: "BEV share" has three denominators

Every "BEV share" in the S-curve work is the share of the **light RUC pool**
(conventional diesel + BEV + PHEV — the pool the class split reallocates). The same
kilometres give very different ratios against other totals: FY2025's 820.6m BEV km are
6.07% of the pool, 1.81% of all light travel including petrol, and 1.67% of all road
travel across MBU26's six volume rows. Also note MBU26's "Light RUC net km" row is
conventional (diesel) ONLY — BEV and PHEV are separate rows. The dashboard's **Fleet mix
explorer** (bottom of the Revenue Outlook page; commit `5fee9fb`) makes all of this
explicit: MoT's six rows across MBU26 / VFM / the committed pack, with a mandatory
"as a share of" denominator picker and a definitions table mapping each MBU26 row to its
VFM power types and dashboard series. `tests/test_fleet_mix.py` pins the three-denominator
example as a regression test.

## 8. Suggested review angles for the consultant

- Re-run everything (commands below) and check the workbook's sheet 8 verdict and the
  sheet 3 summary cells recompute on your machine.
- Interrogate the tournament design: training window (2001–2040), holdout (2041–2050),
  the nine forms, AICc reporting. Would a different split change the ranking?
- Stress the growth-rate regression: it excludes shares < 0.5% (noise guard) and the
  policy-era scatter (2013–2023 Clean Car Discount on/off) is visible in the all-years
  R² (0.57–0.71) vs projection-era (0.90–0.97). Is that exclusion defensible for your
  audience?
- The λ machinery still produces the committed packs. If the residual optimiser bothers
  you, the workbook shows the pure-MoT-proportion alternative differs by under a share
  point — is that gap worth eliminating at source?
- The observed-outturn test has n=2. MoT/NZTA fleet statistics could extend it backwards
  (pre-FY2024) if a governed source is vendored.

## 9. Reproducing everything

```powershell
git clone https://github.com/AdrianD234/NLTF-revenue-ML-model-dashboard.git
cd NLTF-revenue-ML-model-dashboard
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt scipy openpyxl
.venv\Scripts\python.exe scripts\uptake_shape_lab.py            # evidence CSVs + report
.venv\Scripts\python.exe scripts\build_glass_box_workbook.py    # rebuilds the workbook
.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/test_playwright_smoke.py
```

The dashboard itself: `streamlit run app.py` (deployed at
https://nltf-revenue-ml-model-dashboard.streamlit.app/, viewer sign-in required).
Key source files for this topic: `model_dashboard/ev_uptake_levers.py` (dial engine),
`model_dashboard/mbu26_source_spine.py` (MBU26 arithmetic incl. the λ allocation),
`scripts/extract_vfm_uptake_shares.py` (VFM extraction), `docs/ALTERNATE_ENGINE.md`
(the AR(1) production engine).
