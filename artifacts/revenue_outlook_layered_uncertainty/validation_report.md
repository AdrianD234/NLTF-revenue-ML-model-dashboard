# Validation report — layered scenarios and uncertainty

Branch `feature/revenue-outlook-layered-scenarios-uncertainty`, base `28ee2e3`.

---

## 1. Gates

| gate | result |
|---|---|
| `python -m compileall -q .` | **PASS** |
| Complete local pytest suite | **1 430 passed, 0 failed, 50 skipped, 41 deselected** (34m 48s) |
| Conflict scenario extract validation | **21/21** |
| Streamlit deployment readiness | **PASS** |
| GDP sign-guard binding register | rebuilt, **PASS** |
| Replay seed diagnostic | **PASS** — 0 missing supported keys, 0 reclassified |
| Replay parity fingerprint | `6849a6da0fcae038d9e72c0203356b21a7394c28fd312baccba66debeb11cac7` — **exact match** to the recorded baseline |
| Browser console errors | **0** at 1920×1080 and 1440×900 |

The replay fingerprint matching the committed baseline byte for byte is the
strongest single statement that no model or replay value moved.

---

## 2. A regression the full suite caught, and the fix

The first complete run failed two tests in `test_scenario_comparison.py`:

```
assert toggled["b"].loc[2030] == pytest.approx(5663.618433259718)
Obtained: 6434.36939164909
```

**Cause.** Historic keys wrote the FED policy as a `0`/`1` toggle, and
`_normalise_fed_policy_state` has always carried the legacy semantics
(`0` → delayed, `1` → no uplift). My typed key stores policy as **text**, and
the legacy adapter stringified those ints to `"0"`/`"1"` before the normaliser
could see them — so the MBU26 no-uplift counterfactual silently reverted to the
published path, a ~771 $m difference at FY2030.

**Fix.** The adapter now resolves non-text policy values through a
`policy_normaliser` supplied by the caller (`app._scenario_key` passes
`_normalise_fed_policy_state`), and **fails closed** when a numeric policy
arrives with no normaliser rather than guessing. Four parametrised regression
tests pin every 0/1 combination, plus one asserting the bare adapter raises.

This is the same class of defect as the original slot-6 collision — a value
silently meaning something else — so it is fixed the same way: refuse to guess.

**Re-verified after the fix:** scenario comparison, typed key and canonical
base composition — 70 passed. The uncertainty pack rebuilt to a byte-identical
hash (`e38a79b8667352ff…`), so no band value moved.

---

## 3. Central-value movement

Exactly one intended movement, from P0:

| | |
|---|---|
| rows moved | **100** |
| series | `heavy_ruc_net_km`, `heavy_ruc_net_revenue` only |
| engines | both |
| unexpected rows | **0** (the builder exits non-zero if any appear) |
| aggregates moved | **none** — the overlay is a value-preserving reclassification |
| official published rows | **unchanged**, byte-equal to the committed CSVs |

Gate A: 2 250 rows across chart · line reconciliation · stack components ·
`FORMULA_DEFINITIONS` recomputed from leaves — **zero residuals above 1e-6**.

---

## 4. Draw-level identity closure

| | |
|---|---|
| identity checks | 350 (14 governed formulas × 25 June years) |
| draws per check | **10 000** |
| failures | **0** |
| worst residual | **0.000e+00** |

Aggregate bands are computed from aggregate draws; a test proves the drawn
Total RUC band is strictly narrower than summed component endpoints, which is
what ρ(LIGHT, HEAVY) = 0.472 implies.

---

## 5. Coverage and proxies

Every chartable series has 50% and 80% rows for every June year FY2026–FY2050:
**1 000 rows, 40 series, no gaps**, asserted directly.

Tier-5 contribution to the Total NLTF 80% span:

| component | FY2030 | FY2050 |
|---|---|---|
| heavy_bev proxy | 0.21% | **1.63%** |
| MVR proxy | <0.2% | 0.08% |
| TUC (fixed) | 0 | 0 |

None dominates.

---

## 6. Determinism and idempotency

- Uncertainty pack byte-identical across rebuilds, and unchanged by the policy
  fix.
- Every builder rerun back to back: **22 of 23 governed files byte-identical**.
  Only `performance_timings.csv` differs — it records wall-clock measurements.
- The draw engine is seeded (`20260801`) and asserted deterministic; the
  origin-clustered bootstrap is seeded and asserted reproducible frame-for-frame.

---

## 7. Performance

| stage | mean ms |
|---|---|
| pack load (cold, once per process) | 26.7 |
| band lookup per series | **0.144** |
| layer catalogue build | 0.014 |
| figure assembly, default | 89.6 |
| figure assembly, all layers | 89.4 |
| **whole render path** | **93.1** |

Target ≤ 100 ms met. A test asserts the runtime contains no draw-engine symbols
— no simulation, no workbook load, no model fit at render time.

---

## 8. New test coverage

| suite | tests |
|---|---|
| `test_revenue_scenario_key.py` | 37 |
| `test_revenue_uncertainty_basis.py` | 11 |
| `test_revenue_uncertainty_draws.py` | 20 |
| `test_revenue_chart_layers.py` | 19 |
| `test_revenue_outlook_vfm_envelope.py` | 39 (1 added) |

Existing suites updated rather than weakened: the smoke pins now assert the
unified selector and the new audit toggle; the envelope tests request the
envelope layer explicitly, with a new test proving it is absent unless selected.
No numerical tolerance was widened anywhere.
