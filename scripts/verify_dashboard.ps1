param(
    [string]$Python = "",
    [string]$DataRoot = "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack",
    [int]$Port = 8501,
    [int]$StartupTimeoutSeconds = 90
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
        $Python = "C:\Users\Adrian Desilvestro\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$env:MODEL_DIAGNOSTIC_DATA_ROOT = $DataRoot

Invoke-Checked -FilePath $Python -Arguments @("-m", "compileall", ".")
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q")
Invoke-Checked -FilePath $Python -Arguments @("scripts\inspect_parquet_schema.py", "--data-root", $DataRoot)
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_dashboard_data.py", "--data-root", $DataRoot)
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_chart_sources.py", "--data-root", $DataRoot)
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_semantic_labels.py", "--data-root", $DataRoot)
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests/test_chart_data_reconciliation.py")
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests/test_chart_source_tables.py")
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests")

$healthUrl = "http://localhost:$Port/_stcore/health"
$appUrl = "http://localhost:$Port"
$serverProcess = $null
$serverLog = Join-Path $Root "streamlit.test.out.log"
$serverErr = Join-Path $Root "streamlit.test.err.log"

function Test-StreamlitHealth {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Stop-PortListeners {
    param([int]$Port)

    $pids = @()
    $pids += Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" -or $_.State -eq "Bound" } |
        Select-Object -ExpandProperty OwningProcess -Unique

    $netstatOutput = & netstat -ano 2>$null
    foreach ($line in $netstatOutput) {
        if ($line -notmatch ":$Port\s") {
            continue
        }
        $parts = @($line -split "\s+" | Where-Object { $_ })
        if ($parts.Count -ge 5 -and $parts[3] -eq "LISTENING") {
            $pids += [int]$parts[4]
        }
    }

    $pids |
        Where-Object { $_ -and $_ -gt 0 } |
        Select-Object -Unique |
        ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
}

Stop-PortListeners -Port $Port

$serverProcess = Start-Process -FilePath $Python -ArgumentList @(
    "-m",
    "streamlit",
    "run",
    "app.py",
    "--server.port",
    "$Port",
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false"
) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $serverLog -RedirectStandardError $serverErr -PassThru

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if ((Test-StreamlitHealth -Url $healthUrl) -or (Test-StreamlitHealth -Url $appUrl)) {
        break
    }
    Start-Sleep -Seconds 2
}

try {
    if (-not ((Test-StreamlitHealth -Url $healthUrl) -or (Test-StreamlitHealth -Url $appUrl))) {
        throw "Streamlit did not become healthy at $appUrl"
    }

    $env:STAGE1_DASHBOARD_URL = $appUrl
    Invoke-Checked -FilePath $Python -Arguments @(
        "-m",
        "pytest",
        "-q",
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

    Write-Host "Running Playwright/browser frontend interaction tests..."
    $env:STAGE1_REQUIRE_FRONTEND_INTERACTIONS = "1"
    & $Python -m pytest -q tests/test_playwright_frontend_interactions.py

    if ($LASTEXITCODE -ne 0) {
        throw "Playwright frontend interaction tests failed."
    }

    $requiredFrontendScreenshots = @(
        "artifacts/screenshots/final-overview.png",
        "artifacts/screenshots/final-diagnostics.png",
        "artifacts/screenshots/final-scenario-comparison.png",
        "artifacts/screenshots/final-schiff-benchmark.png"
    )

    foreach ($shot in $requiredFrontendScreenshots) {
        if (!(Test-Path $shot)) {
            throw "Missing required browser screenshot: $shot"
        }
    }

    $sessionStateDefaultWarning = "created with a default value but also had its value set via the Session State API"
    $streamlitLogs = @($serverLog, $serverErr)
    foreach ($logPath in $streamlitLogs) {
        if ((Test-Path -LiteralPath $logPath) -and ((Get-Content -LiteralPath $logPath -Raw) -like "*$sessionStateDefaultWarning*")) {
            throw "Streamlit widget session-state/default-value warning found in $logPath."
        }
    }

    Write-Host "Playwright frontend interaction tests passed."

    Invoke-Checked -FilePath $Python -Arguments @("scripts/visual_reference_check.py")
    Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_visual_conformance.py")

    $requiredScreenshots = @(
        "artifacts/screenshots/final-01-overview.png",
        "artifacts/screenshots/final-02-diagnostics.png",
        "artifacts/screenshots/final-03-scenario-comparison.png",
        "artifacts/screenshots/final-04-schiff-benchmark.png"
    )
    foreach ($artifact in $requiredScreenshots) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $artifact))) {
            throw "Missing required page screenshot: $artifact"
        }
    }

    Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_80_gates.py", "--data-root", $DataRoot)
    Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_120_gates.py", "--data-root", $DataRoot)

    $backlog = Get-Content -LiteralPath (Join-Path $Root "BUG_BACKLOG.md") -Raw
    if ($backlog -match "- \[ \]") {
        throw "BUG_BACKLOG.md contains unchecked items."
    }

    Write-Host "Parquet-backed dashboard verification passed with the 100-gate visual conformance suite."
}
finally {
    Stop-PortListeners -Port $Port
    if ($serverProcess -ne $null) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
