param(
    [string]$Python = "",
    [int]$Port = 8501,
    [int]$CommandTimeoutSeconds = 900,
    [int]$PreflightTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($Python)) {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $venvPython) {
        $Python = $venvPython
    }
    elseif ($pathPython -and (Test-Path -LiteralPath $pathPython.Source)) {
        $Python = $pathPython.Source
    }
    else {
        $Python = "python"
    }
}

if ($Python -ne "python" -and -not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

$AppUrl = "http://localhost:$Port"
$HealthUrl = "$AppUrl/_stcore/health"
$BoundedScript = Join-Path $ScriptDir "invoke_bounded.ps1"
$LogDir = Join-Path $Root "artifacts\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-StreamlitHealth {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function ConvertTo-CommandText {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    $parts = @($FilePath)
    foreach ($argument in $Arguments) {
        if ($argument -match '[\s"`]') {
            $parts += '"' + ($argument -replace '"', '\"') + '"'
        }
        else {
            $parts += $argument
        }
    }
    return $parts -join " "
}

function Get-RecentLogText {
    param([string]$Label)

    $safeLabel = ($Label -replace '[^A-Za-z0-9_.-]', '_').Trim("_")
    $logs = @(Get-ChildItem -LiteralPath $LogDir -File -Filter "*.$safeLabel.*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 2)

    $chunks = @()
    foreach ($log in $logs) {
        $chunks += "=== $($log.FullName) ==="
        $chunks += (Get-Content -LiteralPath $log.FullName -Tail 120 -ErrorAction SilentlyContinue)
    }
    return ($chunks -join [Environment]::NewLine)
}

function Write-HostBrowserRequired {
    param(
        [string]$FailedCommand,
        [string]$LogText
    )

    Write-Host "HOST_BROWSER_REQUIRED"
    Write-Host "Playwright failed before dashboard access with Windows named-pipe access denial."
    Write-Host "This is a sandbox/host-boundary failure, not a missing dependency or dashboard failure."
    Write-Host "Run this from the user's host PowerShell instead:"
    Write-Host "pwsh -NoProfile -File scripts\verify_browser_host.ps1 -Python python -Port $Port"
    Write-Host "Failed command:"
    Write-Host $FailedCommand
    if (-not [string]::IsNullOrWhiteSpace($LogText)) {
        Write-Host "--- recent Playwright log tail ---"
        Write-Host $LogText
    }
}

function Invoke-HostBrowserCommand {
    param(
        [string]$Label,
        [string[]]$Arguments,
        [int]$TimeoutSeconds
    )

    $commandText = ConvertTo-CommandText -FilePath $Python -Arguments $Arguments
    try {
        if (Test-Path -LiteralPath $BoundedScript) {
            & $BoundedScript `
                -FilePath $Python `
                -Arguments $Arguments `
                -TimeoutSeconds $TimeoutSeconds `
                -WorkingDirectory $Root `
                -Label $Label
        }
        else {
            & $Python @Arguments
            if ($LASTEXITCODE -ne 0) {
                throw "Command failed with exit code ${LASTEXITCODE}: $commandText"
            }
        }
    }
    catch {
        $logText = Get-RecentLogText -Label $Label
        $combined = "$($_.Exception.Message)`n$logText"
        if ($combined -match "WinError\s*5|Access is denied|access denied|named pipe") {
            Write-HostBrowserRequired -FailedCommand $commandText -LogText $logText
            throw "HOST_BROWSER_REQUIRED: pytest-playwright must run from an approved host/outside-sandbox PowerShell."
        }
        throw
    }
}

if (-not (Test-StreamlitHealth -Url $HealthUrl)) {
    throw "Streamlit is not healthy at $HealthUrl. Start or reuse the app before running host browser verification."
}

$env:STAGE1_DASHBOARD_URL = $AppUrl

$preflight = "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print('browser ok'); b.close(); p.stop()"
Invoke-HostBrowserCommand -Label "host-playwright-preflight" -TimeoutSeconds $PreflightTimeoutSeconds -Arguments @("-c", $preflight)

Invoke-HostBrowserCommand -Label "host-playwright-e2e" -TimeoutSeconds $CommandTimeoutSeconds -Arguments @(
    "-m",
    "pytest",
    "-vv",
    "-s",
    "--maxfail=1",
    "-p",
    "no:cacheprovider",
    "-o",
    "addopts=",
    "tests/test_playwright_dashboard.py",
    "tests/test_filter_and_hover.py",
    "tests/test_filters_are_clickable.py",
    "tests/test_reset_filters.py",
    "tests/test_hovers_are_readable.py",
    "-m",
    "e2e"
)

Write-Host "HOST_BROWSER_VERIFICATION_PASSED $AppUrl"
