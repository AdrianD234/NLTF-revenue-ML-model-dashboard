# Reproducibility UI Contract Pack

This pack prevents the dashboard from mislabelling component weights as feature importances.
It is not a replacement for the Light/PED/Heavy reproducibility packs.

Use:
- `reproducibility_panel_contract.parquet` or `.csv` to decide which panels are available per stream.
- If status is `component_weight_only`, display as component contribution, not variable importance.
- If status is `unavailable`, render a missing-data card.
- If status is `available`, render the relevant panel from that stream's reproducibility pack.

The contract is especially important for:
- PED: C1=100% is a stored component replay, not feature importance.
- Heavy RUC: C1-C4 are ensemble component weights/contributions, not feature importances inside each component.