param(
    [string]$Python = "C:\Users\Adrian Desilvestro\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [int]$Port = 8501,
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

$runDir = $env:MODEL_RUN_DIR
if ([string]::IsNullOrWhiteSpace($runDir)) {
    $runDir = "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339"
}
$env:MODEL_RUN_DIR = $runDir

New-Item -ItemType Directory -Force -Path "artifacts/logs" | Out-Null

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

Write-Host "Running backend performance benchmark"
& $Python scripts\benchmark_dashboard.py --run-dir "$runDir" --out-dir artifacts --repeats 3 |
    Tee-Object -FilePath "artifacts/logs/performance_benchmark.log"
if ($LASTEXITCODE -ne 0) {
    throw "Backend performance benchmark failed."
}

$healthUrl = "http://localhost:$Port/_stcore/health"
$appUrl = "http://localhost:$Port"
$serverProcess = $null
$serverLog = Join-Path $Root "streamlit.performance.out.log"
$serverErr = Join-Path $Root "streamlit.performance.err.log"

Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -gt 0 } |
    ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }

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
    Write-Host "Running browser performance tests"
    Invoke-Checked -FilePath $Python -Arguments @(
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        "tests/test_playwright_performance.py",
        "-m",
        "e2e"
    )

    $required = @(
        "PERFORMANCE_SPEC.lock.md",
        "PERF_DEFECT_BACKLOG.lock.md",
        "artifacts/performance_latest.json",
        "artifacts/performance_baseline.json",
        "artifacts/performance_history.json",
        "artifacts/performance_review.md",
        "artifacts/performance_improvement_loops.json",
        "artifacts/browser_performance_latest.json",
        "artifacts/reviews/performance_bottleneck_review.md",
        "artifacts/reviews/cache_review.md",
        "artifacts/reviews/rerun_review.md",
        "artifacts/reviews/frontend_render_review.md"
    )
    foreach ($file in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $file))) {
            throw "Missing required performance artifact: $file"
        }
    }

    $loops = @(Get-Content -LiteralPath (Join-Path $Root "artifacts/performance_improvement_loops.json") -Raw | ConvertFrom-Json)
    if ($loops.Count -lt 15) {
        throw "Fewer than 15 performance improvement loops documented."
    }
    foreach ($loop in $loops) {
        foreach ($field in @("loop", "bottleneck", "files_changed", "timing_before", "timing_after", "improvement_or_regression", "tests_added_or_updated", "verification", "next_bottleneck")) {
            if ($null -eq $loop.$field) {
                throw "Performance loop entry missing field: $field"
            }
        }
    }

    $latest = Get-Content -LiteralPath (Join-Path $Root "artifacts/performance_latest.json") -Raw | ConvertFrom-Json
    if (-not $latest.benchmarks -or $latest.benchmarks.Count -lt 3) {
        throw "Performance benchmark did not record enough backend measurements."
    }

    $browserLatest = Get-Content -LiteralPath (Join-Path $Root "artifacts/browser_performance_latest.json") -Raw | ConvertFrom-Json
    if ($browserLatest.cold_load_sec -gt 5) {
        throw "Browser cold-load target failed: $($browserLatest.cold_load_sec)s"
    }
    if ($browserLatest.warm_load_sec -gt 2) {
        throw "Browser warm-load target failed: $($browserLatest.warm_load_sec)s"
    }
    if ($browserLatest.max_tab_switch_sec -gt 1.5) {
        throw "Browser tab-switch target failed: $($browserLatest.max_tab_switch_sec)s"
    }
    if ($browserLatest.primary_filter_reset_sec -gt 2) {
        throw "Browser primary filter-change target failed: $($browserLatest.primary_filter_reset_sec)s"
    }
    if ($browserLatest.primary_filter_select_sec -gt 2) {
        throw "Browser primary filter-select target failed: $($browserLatest.primary_filter_select_sec)s"
    }

    $stretchReached = (
        $browserLatest.cold_load_sec -le 3 -and
        $browserLatest.warm_load_sec -le 1 -and
        $browserLatest.max_tab_switch_sec -le 0.75 -and
        $browserLatest.primary_filter_reset_sec -le 1 -and
        $browserLatest.primary_filter_select_sec -le 1
    )

    $benchmarkByLabel = @{}
    foreach ($benchmark in $latest.benchmarks) {
        $benchmarkByLabel[$benchmark.label] = $benchmark
    }
    function Assert-BenchmarkTarget {
        param(
            [string]$Label,
            [double]$MaxSeconds,
            [string]$Name
        )
        if (-not $benchmarkByLabel.ContainsKey($Label)) {
            throw "Missing benchmark label: $Label"
        }
        if ([double]$benchmarkByLabel[$Label].max_sec -gt $MaxSeconds) {
            throw "$Name target failed: $($benchmarkByLabel[$Label].max_sec)s"
        }
    }

    Assert-BenchmarkTarget -Label "overview_page_render_proxy" -MaxSeconds 2 -Name "Overview page render"
    Assert-BenchmarkTarget -Label "plot_candidate_landscape" -MaxSeconds 2 -Name "Candidate Landscape render"
    Assert-BenchmarkTarget -Label "plot_ensemble_composition" -MaxSeconds 2 -Name "Ensemble Composition render"
    Assert-BenchmarkTarget -Label "forecasts_and_errors_render_proxy" -MaxSeconds 2 -Name "Forecasts and Errors render"
    Assert-BenchmarkTarget -Label "plot_stress_checks" -MaxSeconds 2 -Name "Stress Checks render"
    Assert-BenchmarkTarget -Label "plot_inventory_family_performance" -MaxSeconds 2 -Name "Model Inventory render"
    Assert-BenchmarkTarget -Label "run_audit_prep" -MaxSeconds 2 -Name "Run Audit render"

    $backendStretchReached = $true
    foreach ($label in @(
        "overview_page_render_proxy",
        "plot_candidate_landscape",
        "plot_ensemble_composition",
        "forecasts_and_errors_render_proxy",
        "plot_stress_checks",
        "plot_inventory_family_performance",
        "run_audit_prep"
    )) {
        if (-not $benchmarkByLabel.ContainsKey($label) -or [double]$benchmarkByLabel[$label].max_sec -gt 1) {
            $backendStretchReached = $false
        }
    }
    $stretchReached = $stretchReached -and $backendStretchReached
    if ($loops.Count -lt 50 -and -not $stretchReached) {
        throw "Fewer than 50 performance loops completed and stretch-target early-exit evidence is not met."
    }

    if ($benchmarkByLabel["plot_error_distribution_json_bytes"].result_value -gt 100000) {
        throw "Forecast error distribution payload is too large: $($benchmarkByLabel["plot_error_distribution_json_bytes"].result_value) bytes"
    }
    if ($benchmarkByLabel["plot_residual_vs_fitted_json_bytes"].result_value -gt 2000000) {
        throw "Residual diagnostics payload is too large: $($benchmarkByLabel["plot_residual_vs_fitted_json_bytes"].result_value) bytes"
    }

    $backlog = Get-Content -LiteralPath (Join-Path $Root "PERF_DEFECT_BACKLOG.lock.md") -Raw
    if ($backlog -match "\[ \]") {
        throw "PERF_DEFECT_BACKLOG.lock.md still has unresolved items."
    }

    Write-Host "Performance verification passed."
}
finally {
    if ($serverProcess -ne $null) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
