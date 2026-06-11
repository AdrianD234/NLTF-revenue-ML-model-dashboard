# Runs the full vNext production model pipeline locally.
#
#   pwsh -File scripts\run_vnext_pipeline.ps1
#   pwsh -File scripts\run_vnext_pipeline.ps1 -Stage search -Stream HEAVY_RUC
#   pwsh -File scripts\run_vnext_pipeline.ps1 -Stage forecast -Workbook "templates\my_scenario.xlsx"
#
# Stages: search -> select -> finalize -> scorecards -> forecast -> evidence
# The search stage is resumable; rerun it if interrupted.

param(
    [string]$Stage = "all",
    [string]$Stream = "ALL",
    [string]$Workbook = "",
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path $Python)) {
    Write-Host "Python venv not found at $Python; falling back to 'python'" -ForegroundColor Yellow
    $Python = "python"
}

$args_ = @("-m", "pipeline.vnext_run", $Stage, "--stream", $Stream)
if ($Workbook -ne "") {
    $args_ += @("--workbook", $Workbook)
}

Write-Host "Running: $Python $($args_ -join ' ')" -ForegroundColor Cyan
& $Python @args_
if ($LASTEXITCODE -ne 0) { throw "vNext pipeline stage '$Stage' failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "Stage '$Stage' complete." -ForegroundColor Green
Write-Host "Run the governance test suite with:" -ForegroundColor Cyan
Write-Host "  $Python -m pytest tests\test_vnext_parity.py -v"
