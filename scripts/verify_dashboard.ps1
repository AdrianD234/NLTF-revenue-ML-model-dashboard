param(
    [string]$Python = "",
    [string]$DataRoot = "",
    [int]$Port = 8501,
    [int]$StartupTimeoutSeconds = 90,
    [int]$CommandTimeoutSeconds = 900,
    [switch]$ReuseExistingServer
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

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = $env:DASHBOARD_EVIDENCE_PACK_ROOT
}
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = $env:STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT
}
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = "data\dashboard_evidence_pack"
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = $CommandTimeoutSeconds,
        [string]$Label = ""
    )

    $boundedScript = Join-Path $ScriptDir "invoke_bounded.ps1"
    if (Test-Path -LiteralPath $boundedScript) {
        if ([string]::IsNullOrWhiteSpace($Label)) {
            $commandName = Split-Path -Leaf $FilePath
            if ([string]::IsNullOrWhiteSpace($commandName)) {
                $commandName = $FilePath
            }
            $argLabel = ($Arguments | Select-Object -First 4) -join "_"
            $Label = "verify-$commandName-$argLabel"
        }

        & $boundedScript `
            -FilePath $FilePath `
            -Arguments $Arguments `
            -TimeoutSeconds $TimeoutSeconds `
            -WorkingDirectory $Root `
            -Label $Label
        return
    }

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$env:DASHBOARD_EVIDENCE_PACK_ROOT = $DataRoot

Invoke-Checked -FilePath $Python -Arguments @("-m", "compileall", "app.py", "model_dashboard", "scripts") -Label "verify-compileall"
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q") -Label "verify-pytest-all"
Invoke-Checked -FilePath $Python -Arguments @("scripts\inspect_parquet_schema.py", "--data-root", $DataRoot) -Label "verify-parquet-schema"
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_dashboard_data.py", "--data-root", $DataRoot) -Label "verify-dashboard-data"
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_chart_sources.py", "--data-root", $DataRoot) -Label "verify-chart-sources"
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_semantic_labels.py", "--data-root", $DataRoot) -Label "verify-semantic-labels"
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_reproducibility_audit_pack.py", "--data-root", $DataRoot) -Label "verify-reproducibility-pack"
Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_light_ruc_reproducibility.py", "--data-root", $DataRoot) -Label "verify-light-ruc-reproducibility"
Invoke-Checked -FilePath $Python -Arguments @("scripts\check_streamlit_deploy_readiness.py") -Label "verify-streamlit-deploy-readiness"
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests/test_chart_data_reconciliation.py") -Label "verify-chart-data-reconciliation"
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests/test_chart_source_tables.py") -Label "verify-chart-source-tables"
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests") -Label "verify-pytest-tests"

$healthUrl = "http://localhost:$Port/_stcore/health"
$appUrl = "http://localhost:$Port"
$serverProcess = $null
$usingExistingServer = $false
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

if ($ReuseExistingServer -and ((Test-StreamlitHealth -Url $healthUrl) -or (Test-StreamlitHealth -Url $appUrl))) {
    Write-Host "STREAMLIT_REUSE $appUrl"
    $usingExistingServer = $true
}
else {
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
    ) -Label "verify-playwright-e2e"

    Write-Host "Running Playwright/browser frontend interaction tests..."
    $env:STAGE1_REQUIRE_FRONTEND_INTERACTIONS = "1"
    Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q", "tests/test_playwright_frontend_interactions.py") -Label "verify-playwright-frontend-interactions"

    $requiredFrontendScreenshots = @(
        "artifacts/screenshots/final-overview.png",
        "artifacts/screenshots/final-diagnostics.png",
        "artifacts/screenshots/final-scenario-comparison.png",
        "artifacts/screenshots/final-schiff-benchmark.png",
        "artifacts/screenshots/final-revenue-outlook.png",
        "artifacts/screenshots/final-governance-reproducibility.png"
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

    Invoke-Checked -FilePath $Python -Arguments @("scripts/visual_reference_check.py") -Label "verify-visual-reference"
    Invoke-Checked -FilePath $Python -Arguments @("scripts\write_visual_review_evidence.py") -Label "verify-write-visual-review-evidence"
    Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_visual_conformance.py") -Label "verify-visual-conformance"

    $requiredScreenshots = @(
        "artifacts/screenshots/final-01-overview.png",
        "artifacts/screenshots/final-02-diagnostics.png",
        "artifacts/screenshots/final-03-scenario-comparison.png",
        "artifacts/screenshots/final-04-schiff-benchmark.png",
        "artifacts/screenshots/final-05-revenue-outlook.png",
        "artifacts/screenshots/final-06-governance-reproducibility.png"
    )
    foreach ($artifact in $requiredScreenshots) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $artifact))) {
            throw "Missing required page screenshot: $artifact"
        }
    }

    Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_80_gates.py", "--data-root", $DataRoot) -Label "verify-80-gates"
    Invoke-Checked -FilePath $Python -Arguments @("scripts\validate_120_gates.py", "--data-root", $DataRoot) -Label "verify-120-gates"

    $backlog = Get-Content -LiteralPath (Join-Path $Root "BUG_BACKLOG.md") -Raw
    if ($backlog -match "- \[ \]") {
        throw "BUG_BACKLOG.md contains unchecked items."
    }

    Write-Host "Parquet-backed dashboard verification passed with the 120-gate visual conformance suite."
}
finally {
    if (-not $usingExistingServer) {
        Stop-PortListeners -Port $Port
    }
    if ((-not $usingExistingServer) -and $serverProcess -ne $null) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
