# Browser acceptance — Fleet efficiency / PT mode shift through FY2050

Desktop width, `localhost:8537`, promoted ensemble pack, rendered Plotly
calcdata (not helpers). Values are the Current finalist Base case trace on the
Revenue Outlook Total path chart with the full overlay chain (macro replay,
MoT VFM base uptake, deferred-6m 12c policy) active. No browser console
errors, no Streamlit exceptions, no duplicate traces, no disconnected FY2031
segment, no zero-filled extension at any step.

## A. Off baseline (Total NLTF revenue, $b)

| FY | value |
|----|-------|
| 2026 | 4.589495642256075 |
| 2030 | 6.408493240540763 (within-model seam == post-model seam) |
| 2031 | 6.727050913569904 |
| 2040 | 9.460836516573753 |
| 2050 | 12.997261591337160 |

50% and 80% bands drawn; horizon note confirms FY2050 / 2050Q2.

## B. Fleet efficiency

**Med 1.0%** — Total NLTF falls continuously: FY2030 −0.1331, FY2031 −0.1647,
FY2050 −0.2611 $b vs baseline (delta grows smoothly across the seam; no
reset). BEFU26 official identical to baseline at every probe FY. Bands
withheld with the note "Modelled uncertainty is governed for the baseline
computation and is withheld for this analyst sensitivity…".

**VKT invariance** — Light petrol VKT under Fleet Med is bit-identical to Off
at FY2026/2030/2031/2040/2050 (e.g. 9629.378316419868 M km at FY2050 both
ways).

**Custom 10%** — PED volume ratio vs Off baseline:

| FY | ratio | expected 0.9^n |
|----|-------|-----------------|
| 2026 | 0.900000 | 0.9^1 |
| 2030 | 0.590490 | 0.9^5 |
| 2031 | 0.531441 | 0.9^6 — previously reset to 1.0 here |
| 2040 | 0.205891 | 0.9^15 |
| 2050 | 0.071790 | 0.9^25 |

The extreme decline continues mathematically through FY2050 with no jump back
to the unsensitised post-model path.

## C. PT mode shift (Med 0.5%, Fleet Off)

Light petrol VKT ratio vs Off: 0.995000 (FY2026 — effect begins in the first
forecast year), 0.975249 (FY2030), 0.970373 (FY2031 — no seam reset),
0.927569 (FY2040), 0.882220 (FY2050) = 0.995^n exactly. PED volume carries
the identical factors through FY2050 (previously its PT effect died at
FY2031). Selector label reads "Med (0.5% p.a. from FY2026)". Heavy RUC
non-movement and equal scaling of all four light powertrain families are
pinned by the frame-level test module and the nonmovement audit.

## D. Combined (Fleet Med + PT Med)

PED volume ratio vs Off = (0.995 × 0.99)^n exactly: 0.985050 (FY2026),
0.927452 (FY2030), 0.913586 (FY2031), 0.797763 (FY2040), 0.686210 (FY2050).
Product of the two factors; neither lever applied twice.

## E. A/B comparison

* Scenario A mirrors the Single scenario configuration bit-for-bit
  (combined-lever and fleet-only values matched the Single chart exactly).
* "Reset B to current page (A)" then A == B at every probe FY
  (both 3020.6375840741575 … 525.4254361812843) — zero deltas.
* Changing only B's Fleet lever to High left A bit-identical and moved B to
  the exact Fleet-High contract (0.985^n of the same Off baseline:
  0.985000 at FY2026, 0.913308 at FY2031, 0.685340 at FY2050) — B matches
  the equivalent Single scenario computation.

**Noted limitation (pre-existing, out of scope):** Scenario B's PT and
freight levers are method-detail-gated and pinned to neutral "Off" while
hidden (app.py, `_comparison_scenario_controls`). With method detail off, an
A-side PT selection therefore cannot be mirrored in B; the A/B zero-delta
contract holds over B's governed lever set (scenario, fleet, 12c policy).
This behaviour predates this branch (lever-trim commit 9b75bd9).

## F. Uncertainty

Bands withheld while either lever is non-Off, with the governed note; bands
return when both levers are Off (verified in step A). No stale baseline band
was drawn around any adjusted path.
