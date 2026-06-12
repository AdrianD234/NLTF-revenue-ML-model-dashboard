# Run the DEPLOYED code version side by side with your working tree.
#
# Streamlit Cloud serves the last commit pushed to the remote; your local
# working tree is usually ahead of it. The in-app "Cloud runtime preview"
# toggle simulates cloud runtime rules on local code, but it cannot
# time-travel git. This script runs the actually-deployed commit on a second
# port so you can compare the two apps in two browser tabs:
#
#   working tree:      http://localhost:8501   (streamlit run app.py)
#   deployed preview:  http://localhost:8502   (this script)
#
#   pwsh -File scripts\run_deployed_preview.ps1                # origin/main
#   pwsh -File scripts\run_deployed_preview.ps1 -Ref origin/feature/executive-mode
#   pwsh -File scripts\run_deployed_preview.ps1 -Cleanup       # remove the worktree

param(
    [string]$Ref = "origin/main",
    [int]$Port = 8502,
    [switch]$Cleanup,
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$previewDir = Join-Path (Get-Location) ".deploy_preview"

if ($Cleanup) {
    git worktree remove --force $previewDir 2>$null
    if (Test-Path $previewDir) { Remove-Item -Recurse -Force $previewDir }
    git worktree prune
    Write-Host "Deployed-preview worktree removed." -ForegroundColor Green
    exit 0
}

git fetch origin
if (Test-Path $previewDir) {
    git worktree remove --force $previewDir 2>$null
    if (Test-Path $previewDir) { Remove-Item -Recurse -Force $previewDir }
    git worktree prune
}
git worktree add --detach $previewDir $Ref

if (-not (Test-Path $Python)) { $Python = "python" }
$resolved = (git rev-parse --short $Ref)
Write-Host ""
Write-Host "Serving DEPLOYED code ($Ref @ $resolved) on http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Your working tree stays on http://localhost:8501 - compare them in two tabs." -ForegroundColor Cyan
Write-Host "Stop with Ctrl+C; remove the worktree later with: pwsh -File scripts\run_deployed_preview.ps1 -Cleanup" -ForegroundColor DarkGray
Write-Host ""
& $Python -m streamlit run (Join-Path $previewDir "app.py") --server.port $Port --server.headless true
