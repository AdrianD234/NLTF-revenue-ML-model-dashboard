# Governance Story Review

Status: PASS WITH EXPLICIT CAVEATS

Generated: 2026-07-07T07:22:43.877498+00:00
Commit reviewed: `05a8067`

Evidence reviewed:

- `docs/revenue_source_pack_contract.md` documents the governed Revenue Outlook architecture.
- `data/revenue_model_source_pack/2026_05_19/source_gap_register.csv` records runtime source gaps.
- `data/revenue_model_source_pack/2026_05_19/remaining_decisions_handoff.csv` links unresolved decisions to dashboard treatment.
- `data/current_revenue_outlook/manifest.json` records promoted-pack source policy, workbook hashes, bridge statuses, and output hashes.

Findings:

- The dashboard defaults to Total NLTF revenue while preserving the workbook's legacy Total RUC+PED current-selection provenance.
- Direct modeled activity streams and revenue bridge roles are separated for PED, Light RUC, and Heavy RUC.
- Missing release values, FED path values, PED bridge history, and top-up rows remain visible governed gaps.
- The R2 ladder and reproducibility pages distinguish training-fit, calibration, and forecast/net R2.

Residual risk:

- Native Playwright verification must pass before calling the entire dashboard release-ready under AGENTS.md.

Semantic validation excerpt:

```text

```
