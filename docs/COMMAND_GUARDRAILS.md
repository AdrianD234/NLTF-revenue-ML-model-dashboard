# Command Guardrails

Use checked-in bounded launchers for shell commands that can hang or wait on
external state. Avoid pasting long multi-line PowerShell launch loops into a
terminal; a missing quote or continuation prompt can leave the shell sitting
while the underlying server is already healthy.

## Default Timeout Pattern

- Streamlit startup and health checks: 90 seconds.
- Fast import, compile, or health checks: 30 to 90 seconds.
- Dependency installs, `pip`, `npm`, `npx`, or network-bound commands: 120 to
  300 seconds unless a longer timeout is intentionally chosen.
- Broad `pytest`, Playwright, or `verify_dashboard.ps1` runs: bounded with an
  explicit longer timeout, and split into focused tests first when stale
  selectors or repeated `F` output are suspected.

## Streamlit

Start the dashboard with:

```powershell
pwsh -NoProfile -File scripts\start_streamlit_bounded.ps1 -Port 8501 -StartupTimeoutSeconds 90
```

If a known dashboard is already healthy on the port:

```powershell
pwsh -NoProfile -File scripts\start_streamlit_bounded.ps1 -Port 8501 -ReuseHealthy
```

The script writes `.streamlit_<port>.pid`, redirects logs to `artifacts/logs`,
and stops only the process tree it launched on startup failure.

## Generic Commands

Run risky commands through the bounded wrapper:

```powershell
& .\scripts\invoke_bounded.ps1 -Label verify-dashboard -TimeoutSeconds 900 -FilePath pwsh -Arguments @("-NoProfile", "-File", "scripts\verify_dashboard.ps1")
```

Use this wrapper for dependency installs, browser automation, broad test runs,
and validation bundles. On timeout or non-zero exit, it prints log tails and
throws with a clear failure reason.

`scripts\verify_dashboard.ps1` also uses the bounded wrapper internally. Its
per-command default is 900 seconds and can be changed with
`-CommandTimeoutSeconds` when a longer run is intentional.

When a known dashboard is already healthy and should not be restarted, reuse it:

```powershell
& .\scripts\invoke_bounded.ps1 -Label verify-dashboard-reuse -TimeoutSeconds 900 -FilePath pwsh -Arguments @("-NoProfile", "-File", "scripts\verify_dashboard.ps1", "-Port", "8501", "-ReuseExistingServer")
```

## Triage Rules

- Use focused tests before a broad Playwright or dashboard verification run.
- When a timeout fires, inspect the captured logs and exact process command
  line before retrying.
- Stop only the process tree launched by the wrapper. Do not kill unrelated
  user Chrome, Excel, Python, or Streamlit processes blindly.
- If the health endpoint is already `200 OK`, treat the server as running and
  investigate the waiting shell separately.
