# Streamlit Cloud Deployment

## Deployment Fields

- Repo: `https://github.com/AdrianD234/NLTF-revenue-ML-model-dashboard`
- Branch: `main`
- Main file path: `app.py`
- Secrets: none required
- Data source: bundled `data/dashboard_evidence_pack`

## Runtime

Streamlit Cloud installs `requirements.txt` and uses `runtime.txt`.

- Runtime Python: `python-3.11`
- Runtime dependencies: `streamlit`, `pandas`, `plotly`, `pyarrow`, `openpyxl`, `pillow`
- Developer/test dependencies live in `requirements-dev.txt`

`.streamlit/config.toml` keeps theme and browser settings only. It must not force `[server].port`; Streamlit Cloud chooses the port.

## Evidence-Pack Update Process

Run the governed update script from the repo root:

```powershell
pwsh -File scripts\update_evidence_pack.ps1 `
  -SourcePack "C:\Users\Adrian Desilvestro\Downloads\stage1_dashboard_evidence_pack_dual_scorecard_gbm_light_v6_balanced_frontier\dashboard_evidence_pack" `
  -Verify
```

The script:

- validates `manifest.json` and `data/*.parquet`;
- rejects raw-output folders such as `sources/`, `tables_csv/`, `logs/`, and `screenshots/`;
- rejects files over 50 MB;
- replaces `data/dashboard_evidence_pack` safely;
- optionally runs `scripts\verify_dashboard.ps1`;
- prints exact `git add` and `git commit` commands.

After verification:

```powershell
git add -- data/dashboard_evidence_pack scripts/update_evidence_pack.ps1 scripts/check_streamlit_deploy_readiness.py requirements.txt requirements-dev.txt runtime.txt .streamlit/config.toml docs/STREAMLIT_CLOUD_DEPLOYMENT.md README.md app.py model_dashboard/evidence_pack.py
git commit -m "Prepare Streamlit Cloud evidence pack deployment"
git push origin main
```

Streamlit Cloud redeploys from GitHub after the push.

## Confirm Cloud Matches Local

1. Run local verification:

```powershell
python scripts\check_streamlit_deploy_readiness.py
pwsh -File scripts\verify_dashboard.ps1 -DataRoot "data\dashboard_evidence_pack" -Port 8501
```

2. Open the local app and note the footer:

`Data pack version: <schema_version> | created <created_at> | root <resolved_root> | candidate rows <n> | hash <hash>`

3. Open the Streamlit Cloud app and compare:

- `schema_version`
- `created_at`
- candidate row count
- evidence hash

The `resolved_root` path will differ between local Windows and Streamlit Cloud Linux, but the schema, created date, row count, and hash should match.
