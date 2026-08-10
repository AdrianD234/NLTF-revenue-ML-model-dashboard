# The app-boot write path (issue #31)

Every hop verified on origin/main at `46d1f87`.

```
app.py:18353            if __name__ == "__main__": main()
app.py:4129             main()
app.py:4147               active_path = render_run_sidebar()
app.py:4193-4216            render_run_sidebar() -> engine_evidence_root()   [model_dashboard/engine.py:57]
                            engine unset -> engine_default() == "ar1"       [model_dashboard/engine.py:38-40]
                            -> data/engine_ar1/dashboard_evidence_pack
app.py:4148               loaded = load_active_run(active_path)
app.py:4219-4229            load_active_run() -> cached_load_evidence_pack(...)
app.py:558-567              @st.cache_data cached_load_evidence_pack -> load_evidence_pack(data_root, repo_root)
model_dashboard/evidence_pack.py:101        load_evidence_pack()
model_dashboard/evidence_pack.py:245          write_chart_source_tables(repo_path, data)      <-- THE WRITE
model_dashboard/data/chart_sources.py:171       write_chart_source_tables()
model_dashboard/data/chart_sources.py:181         resolve_chart_source_output_dir(repo_root, None)
                                                  -> no arg, no env override
                                                  -> <repo_root>/artifacts/chart_sources
model_dashboard/data/chart_sources.py:184-185     _write_csv_atomic() per table, 22 files
```

`repo_root` is `Path(app.py).resolve().parent` (`app.py:4221`), i.e. the checkout
itself, so the destination is the tracked directory.

## What is and is not involved

- **Not the cache warmer.** `_start_revenue_outlook_cache_warmer` (`app.py:4109`,
  called at `app.py:4155`) runs *after* the pack is loaded and never touches
  chart sources. Disabling it does not prevent the write; the reproduction was
  run with the warmer both on and off.
- **Not page construction.** The write happens during `main()` before any page
  renders. The reproduction confirmed initial boot alone is sufficient.
- **Cache-miss only.** `st.cache_data(max_entries=2)` at `app.py:558` means a
  warm rerun skips `load_evidence_pack` and therefore skips the write. The write
  recurs on any cold start, cache eviction, or evidence-pack signature change.

## Why AR(1) while the canonical evidence is ensemble

`engine_default()` returns `ar1` whenever `DASHBOARD_ENGINE_DEFAULT` is unset
(`model_dashboard/engine.py:38-40`), which is the normal local and deployed
state. The committed tables carry the ensemble identity, produced from
`data/dashboard_evidence_pack`. So the boot wrote a different, individually
valid identity over the governed one, and last-writer-wins decided the published
number.

The ladder itself mixes an engine-selected half with an engine-fixed half:
`model_dashboard/r2_ladder.py:149-165` combines `_diagnostics_summary(data)`
(engine-dependent) with `reproducibility_component_r2_frame(root)` over the
static `CURRENT_REPRO_PACK_DIRS` (`governance_constants.py:38-42`).

## Second writer, same shape

```
model_dashboard/data/parquet_loader.py:119   _build_dashboard_frames(...)
model_dashboard/data/parquet_loader.py:236     _write_reconciliation_source_tables(repo_root, data)
model_dashboard/data/parquet_loader.py:627       write_chart_source_tables(repo_root, data)
```

Reached through `load_parquet_dashboard`, the legacy curated-CSV loader. Not on
the app path today (`cached_load_curated_run` at `app.py:534` is never called),
but it is the same unconditional side effect and was gated identically.

## Does rendering need the files?

No. The dashboard recomputes in memory: `app.py:5383` calls
`r2_ladder_summary_frame(loaded.data, ...)` and never opens the CSV. The single
read is a **count**, not content: `app.py:14374` globs the directory and
`app.py:14867` renders "{n} main chart-source CSVs guarded". See
`read_write_contract.md` for the consequence.
