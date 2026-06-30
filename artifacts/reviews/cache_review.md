# Cache Review

Status: pass with watch items.

Reviewed cache contracts:
- Run and evidence-pack loaders are keyed by file signatures and loader schema version.
- Revenue Outlook view, detail-frame, fan, composition-stack, composition-figure and composition-table helpers use `st.cache_data(show_spinner=False)`.
- The default sensitivity path avoids recomputing the sensitivity impact audit when all sensitivity controls are off.

Findings:
- Cache keys include runtime pack signatures and selected controls, which preserves invalidation when committed pack files or user-visible selections change.
- Mutable global state is not cached directly; cached helpers return derived frames/figures.
- Continue watching broad DataFrame hashing cost before adding more cache wrappers.

