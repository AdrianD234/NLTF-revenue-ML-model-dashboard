param(
    [string]$Python = "C:\Users\Adrian Desilvestro\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [int]$Port = 8501,
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

$LatestRun = "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339"
$CuratedDir = Join-Path $Root "artifacts\curated_data"
$env:MODEL_RUN_DIR = $LatestRun
$env:STAGE1_MODEL_RUN_DIR = $LatestRun

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

Invoke-Checked -FilePath $Python -Arguments @("-m", "compileall", "-q", "app.py", "model_dashboard", "scripts", "tests")
Invoke-Checked -FilePath $Python -Arguments @(
    "scripts\build_curated_dashboard_data.py",
    "--run-dir",
    $LatestRun,
    "--out-dir",
    $CuratedDir,
    "--max-candidate-rows",
    "400"
)
Invoke-Checked -FilePath $Python -Arguments @(
    "scripts\verify_curated_dashboard_data.py",
    "--curated-dir",
    $CuratedDir
)
Invoke-Checked -FilePath $Python -Arguments @("-m", "pytest", "-q")

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
    Invoke-Checked -FilePath $Python -Arguments @("scripts/visual_reference_check.py")

    $requiredArtifacts = @(
        "REQUIREMENTS.lock.md",
        "LATEST_RUN_SOURCE_OF_TRUTH.lock.md",
        "CURATED_DATA_CONTRACT.lock.md",
        "CANDIDATE_LANDSCAPE_SAMPLING_SPEC.lock.md",
        "CONE_LANDSCAPE_VALIDATION.lock.md",
        "DATA_VALIDATION_SPRINT.lock.md",
        "REFERENCE_DASHBOARD_INSIGHTS.lock.md",
        "VISUAL_SPEC.lock.md",
        "VISUAL_DEFECT_BACKLOG.lock.md",
        "FILTER_AND_HOVER_DEFECTS.lock.md",
        "REFERENCE_PAGE_WIREFRAMES.lock.md",
        "INTERACTION_SPEC.lock.md",
        "PERFORMANCE_SPEC.lock.md",
        "PERF_DEFECT_BACKLOG.lock.md",
        "IMPROVEMENT_TARGETS.lock.md",
        "PRODUCT_HARDENING_SPRINT.lock.md",
        "ORIGINAL_DASHBOARD_SPEC.lock.md",
        "BUG_BACKLOG.md",
        "QUALITY_RUBRIC.md",
        "artifacts/requirement_coverage.md",
        "artifacts/deep_quality_review.md",
        "artifacts/visual_reference_comparison.md",
        "artifacts/data_validation_review.md",
        "artifacts/cone_landscape_review.md",
        "artifacts/filter_interaction_review.md",
        "artifacts/improvement_loops.json",
        "artifacts/recursive_audit_loops.json",
        "artifacts/product_improvements.md",
        "artifacts/spec_conformance_matrix.md",
        "artifacts/management_readiness_report.md",
        "artifacts/screenshot_review.md",
        "artifacts/quality_rubric.md",
        "artifacts/product_review_loops.md",
        "artifacts/test_summary.md",
        "artifacts/hover_review.md",
        "artifacts/reviews/data_correctness.md",
        "artifacts/reviews/cone_landscape_review.md",
        "artifacts/reviews/ux_screenshot.md",
        "artifacts/reviews/governance_story.md",
        "artifacts/reviews/layout_grid.md",
        "artifacts/reviews/visual_styling.md",
        "artifacts/reviews/interaction_filter.md",
        "artifacts/reviews/data_correctness_review.md",
        "artifacts/reviews/ux_screenshot_review.md",
        "artifacts/reviews/governance_story_review.md",
        "artifacts/reference_screenshots/README.md",
        "artifacts/screenshots/final-01-overview.png",
        "artifacts/screenshots/final-02-diagnostics.png",
        "artifacts/screenshots/final-03-scenario-comparison.png",
        "artifacts/screenshots/final-04-schiff-benchmark.png",
        "artifacts/screenshots/mcp-01-overview.png",
        "artifacts/screenshots/mcp-02-diagnostics.png",
        "artifacts/screenshots/mcp-03-scenario-comparison.png",
        "artifacts/screenshots/mcp-04-schiff-benchmark.png",
        "artifacts/screenshots/hover-candidate-landscape.png",
        "artifacts/screenshots/hover-finalist-accuracy.png",
        "artifacts/screenshots/hover-ensemble-composition.png",
        "artifacts/screenshots/hover-stress-checks.png",
        "artifacts/curated_data/curation_manifest.json",
        "artifacts/curated_data/finalist_accuracy.csv",
        "artifacts/curated_data/candidate_landscape_sample.csv",
        "artifacts/curated_data/schiff_benchmark.csv",
        "artifacts/curated_data/pdf_comparison.csv",
        "artifacts/curated_data/stress_horizon.csv",
        "artifacts/curated_data/ensemble_composition.csv",
        "artifacts/curated_data/annual_predictions_selected.csv",
        "artifacts/curated_data/quarterly_predictions_selected.csv",
        "artifacts/curated_data/data_quality_report.md",
        "artifacts/curated_data/verification_report.md"
    )

    foreach ($artifact in $requiredArtifacts) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $artifact))) {
            throw "Missing required verification artifact: $artifact"
        }
    }

    $finalists = Import-Csv -LiteralPath (Join-Path $Root "artifacts/curated_data/finalist_accuracy.csv")
    $expectedFinalists = @{
        "PED"       = @{ Model = "PED__solver_static_convex_top18"; Quarterly = 2.47358; Annual = 2.38709 }
        "LIGHT_RUC" = @{ Model = "LIGHT_RUC__solver_static_convex_top18"; Quarterly = 9.14755; Annual = 5.99950 }
        "HEAVY_RUC" = @{ Model = "HEAVY_RUC__solver_static_convex_top18"; Quarterly = 3.56092; Annual = 3.17141 }
    }
    foreach ($stream in $expectedFinalists.Keys) {
        $row = @($finalists | Where-Object { $_.stream -eq $stream -and $_.model -eq $expectedFinalists[$stream].Model })
        if ($row.Count -ne 1) {
            throw "Latest finalist row is missing or duplicated for $stream."
        }
        $quarterly = [double]$row[0].quarterly_mape
        $annual = [double]$row[0].annual_mape
        if ([math]::Abs($quarterly - [double]$expectedFinalists[$stream].Quarterly) -gt 0.01) {
            throw "Latest quarterly MAPE does not reconcile for $stream."
        }
        if ([math]::Abs($annual - [double]$expectedFinalists[$stream].Annual) -gt 0.01) {
            throw "Latest annual MAPE does not reconcile for $stream."
        }
    }
    foreach ($stale in @(5.49, 11.55, 12.38)) {
        foreach ($row in $finalists) {
            if ([math]::Abs(([double]$row.quarterly_mape) - $stale) -lt 0.01) {
                throw "Stale AutoGluon finalist value $stale is present in finalist_accuracy.csv."
            }
        }
    }

    $candidateRows = @(Import-Csv -LiteralPath (Join-Path $Root "artifacts/curated_data/candidate_landscape_sample.csv"))
    if ($candidateRows.Count -gt 400) {
        throw "Candidate landscape curated sample exceeds the 400-row hard cap."
    }
    foreach ($role in @("Recommended finalist", "Pure Schiff benchmark", "Distribution sample")) {
        if (-not @($candidateRows | Where-Object { $_.candidate_role -eq $role }).Count) {
            throw "Candidate landscape sample is missing required role: $role"
        }
    }

    $schiffRows = @(Import-Csv -LiteralPath (Join-Path $Root "artifacts/curated_data/schiff_benchmark.csv"))
    $badSchiffRows = @($schiffRows | Where-Object { $_.model -match "(?i)(RESID|residual|fixedblend|solver|convex|ensemble|top|median|mean|GBM|blended)" })
    if ($badSchiffRows.Count -gt 0) {
        throw "Pure Schiff benchmark includes residual/blend/solver-like rows."
    }

    $stressRows = @(Import-Csv -LiteralPath (Join-Path $Root "artifacts/curated_data/stress_horizon.csv"))
    foreach ($bucket in @("1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual")) {
        if (-not @($stressRows | Where-Object { $_.stress_bucket -eq $bucket }).Count) {
            throw "Stress/horizon curated data is missing bucket: $bucket"
        }
    }

    $ensembleRows = @(Import-Csv -LiteralPath (Join-Path $Root "artifacts/curated_data/ensemble_composition.csv"))
    if ($ensembleRows.Count -eq 0) {
        throw "Ensemble composition curated data is empty."
    }
    $nonPositiveWeights = @($ensembleRows | Where-Object { [double]$_.weight -le 0 })
    if ($nonPositiveWeights.Count -gt 0) {
        throw "Ensemble composition contains non-positive weights."
    }

    $coverage = Get-Content -LiteralPath (Join-Path $Root "artifacts/requirement_coverage.md") -Raw
    if ($coverage -match "(?i)\b(Missing|Partial|Weak|Not Verified|TODO|Not implemented)\b") {
        throw "Requirement coverage contains unresolved items."
    }

    $rubric = Get-Content -LiteralPath (Join-Path $Root "artifacts/quality_rubric.md") -Raw
    if ($rubric -match "Score:\s*[0-3]/5") {
        throw "Quality rubric has a score below 4/5."
    }

    $rootRubric = Get-Content -LiteralPath (Join-Path $Root "QUALITY_RUBRIC.md") -Raw
    if ($rootRubric -match "(?i)\b([0-3]/5)\b") {
        throw "Root quality rubric has a score below 4/5."
    }

    $backlog = Get-Content -LiteralPath (Join-Path $Root "BUG_BACKLOG.md") -Raw
    if ($backlog -match "- \[ \]") {
        throw "BUG_BACKLOG.md contains unchecked items."
    }

    $defects = Get-Content -LiteralPath (Join-Path $Root "VISUAL_DEFECT_BACKLOG.lock.md") -Raw
    if ($defects -match "\[ \]") {
        throw "VISUAL_DEFECT_BACKLOG.lock.md still has unresolved items."
    }

    $filterHoverBacklog = Join-Path $Root "FILTER_AND_HOVER_DEFECTS.lock.md"
    if (-not (Test-Path -LiteralPath $filterHoverBacklog)) {
        throw "Missing FILTER_AND_HOVER_DEFECTS.lock.md"
    }
    $filterHoverText = Get-Content -LiteralPath $filterHoverBacklog -Raw
    if ($filterHoverText -match "\[ \]") {
        throw "Unresolved filter/hover defects remain."
    }
    $performanceBacklog = Join-Path $Root "PERF_DEFECT_BACKLOG.lock.md"
    if (Test-Path -LiteralPath $performanceBacklog) {
        $performanceText = Get-Content -LiteralPath $performanceBacklog -Raw
        if ($performanceText -match "\[ \]") {
            throw "PERF_DEFECT_BACKLOG.lock.md still has unresolved items."
        }
    }
    $playwrightLog = Join-Path $Root "artifacts/logs/playwright.log"
    if (Test-Path -LiteralPath $playwrightLog) {
        $log = Get-Content -LiteralPath $playwrightLog -Raw
        if ($log -match "filter|dropdown|hover") {
            Write-Host "Filter/hover browser checks present in Playwright log."
        }
    }
    $testSummary = Join-Path $Root "artifacts/test_summary.md"
    if (Test-Path -LiteralPath $testSummary) {
        $summary = Get-Content -LiteralPath $testSummary -Raw
        if (-not ($summary -match "primary filters.*clickable" -and $summary -match "hover.*human-readable")) {
            throw "Test summary does not confirm clickable filters and human-readable hovers."
        }
    }

    $productLoops = Get-Content -LiteralPath (Join-Path $Root "artifacts/product_review_loops.md") -Raw
    foreach ($loopName in @("Data Correctness Review", "Visual/Product Review", "Governance/Story Review")) {
        if ($productLoops -notmatch [regex]::Escape($loopName)) {
            throw "Missing product-review loop documentation: $loopName"
        }
    }

    $loopsPath = Join-Path $Root "artifacts/improvement_loops.json"
    if (-not (Test-Path -LiteralPath $loopsPath)) {
        throw "Missing improvement loop log: artifacts/improvement_loops.json"
    }
    $loops = @(Get-Content -LiteralPath $loopsPath -Raw | ConvertFrom-Json)
    if ($loops.Count -lt 50) {
        throw "Fewer than 50 visual/product improvement loops completed."
    }
    foreach ($loop in $loops) {
        if (-not $loop.loop -or -not $loop.target -or -not $loop.change -or -not $loop.test_added -or -not $loop.verification) {
            throw "Improvement loop log contains an incomplete entry."
        }
        if ($loop.verification -notmatch "(?i)^passed$") {
            throw "Improvement loop $($loop.loop) is not marked passed."
        }
    }

    $recursivePath = Join-Path $Root "artifacts/recursive_audit_loops.json"
    if (-not (Test-Path -LiteralPath $recursivePath)) {
        throw "Missing recursive audit loop log: artifacts/recursive_audit_loops.json"
    }
    $recursiveLoops = @(Get-Content -LiteralPath $recursivePath -Raw | ConvertFrom-Json)
    if ($recursiveLoops.Count -lt 1) {
        throw "Recursive audit loop log is empty."
    }
    if ($recursiveLoops.Count -lt 20) {
        throw "Fewer than 20 recursive audit loops completed."
    }
    foreach ($loop in $recursiveLoops) {
        foreach ($field in @("loop", "timestamp", "defect_targeted", "files_changed", "tests_added_or_strengthened", "data_check_result", "browser_check_result", "screenshot_evidence", "remaining_defects")) {
            if ($null -eq $loop.$field) {
                throw "Recursive audit loop entry is missing field: $field"
            }
        }
        if ($loop.data_check_result -match "(?i)\b(Pending|Fail|Failed|Not Verified)\b") {
            throw "Recursive audit loop $($loop.loop) does not have a passed data-check result."
        }
        if ($loop.browser_check_result -match "(?i)\b(Pending|Fail|Failed|Not Verified)\b") {
            throw "Recursive audit loop $($loop.loop) does not have a passed browser-check result."
        }
    }

    $deep = Get-Content -LiteralPath (Join-Path $Root "artifacts/deep_quality_review.md") -Raw
    foreach ($loop in 1..50) {
        if ($deep -notmatch "\|\s*$loop\s*\|") {
            throw "Deep quality review does not document improvement loop $loop."
        }
    }
    if ($deep -match "Score:\s*([0-8](?:\.\d+)?|9\.[0-4])/10") {
        throw "At least one dashboard page has a deep-quality score below 9.5/10."
    }
    $pageMatrixMatch = [regex]::Match($deep, "(?s)## Page Score Matrix\s*(.*?)## Completed Improvement Loops")
    if (-not $pageMatrixMatch.Success) {
        throw "Deep quality review is missing the page score matrix."
    }
    $scoreLines = $pageMatrixMatch.Groups[1].Value -split "`r?`n" | Where-Object { $_ -match "^\|\s*[^|]+\s*\|\s*\d" }
    foreach ($line in $scoreLines) {
        $cells = $line -split "\|" | ForEach-Object { $_.Trim() }
        $scoreValues = @()
        foreach ($cell in $cells) {
            if ($cell -match "^\d+(?:\.\d+)?$") {
                $scoreValues += [double]$cell
            }
        }
        foreach ($score in $scoreValues) {
            if ($score -lt 9.5) {
                throw "At least one dashboard page has a deep-quality score below 9.5/10."
            }
        }
    }
    if ($deep -match "(?i)\b(Pending|Fail|Below threshold|Placeholder|Not Verified)\b") {
        throw "Deep quality review contains unresolved improvement status."
    }

    $improvements = Get-Content -LiteralPath (Join-Path $Root "artifacts/product_improvements.md") -Raw
    $improvementCount = ([regex]::Matches($improvements, "^- \[x\]", "Multiline")).Count
    if ($improvementCount -lt 50) {
        throw "Fewer than 50 material product improvements documented."
    }

    $assertionInventory = Join-Path $Root "artifacts/assertion_inventory.md"
    if (-not (Test-Path -LiteralPath $assertionInventory)) {
        throw "Missing assertion inventory: artifacts/assertion_inventory.md"
    }
    $assertions = Get-Content -LiteralPath $assertionInventory -Raw
    $assertionCount = ([regex]::Matches($assertions, "^- \[x\]", "Multiline")).Count
    if ($assertionCount -lt 50) {
        throw "Fewer than 50 new or strengthened assertions documented."
    }

    $visual = Get-Content -LiteralPath (Join-Path $Root "artifacts/visual_reference_comparison.md") -Raw
    if ($visual -match "Score:\s*([0-8](?:\.\d+)?|9\.[0-4])/10") {
        throw "At least one page has visual reference score below 9.5/10."
    }

    $screenshots = Get-ChildItem -LiteralPath (Join-Path $Root "artifacts/screenshots") -Filter "*.png" -ErrorAction SilentlyContinue
    if ($screenshots.Count -lt 8) {
        throw "Fewer than 8 screenshots found."
    }
    $nonImageScreenshotArtifacts = @(
        Get-ChildItem -LiteralPath (Join-Path $Root "artifacts/screenshots") -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension.ToLowerInvariant() -notin @(".png", ".jpg", ".jpeg") }
    )
    if ($nonImageScreenshotArtifacts.Count -gt 0) {
        throw "Non-image artifacts found in screenshots directory: $($nonImageScreenshotArtifacts.Name -join ', ')"
    }

    $management = Get-Content -LiteralPath (Join-Path $Root "artifacts/management_readiness_report.md") -Raw
    if ($management -match "(?i)\b(Pending|Open|Incomplete|Not ready|TODO)\b") {
        throw "Management readiness report contains unresolved status."
    }
    if ($management -match "Validation run:.*autogluon_balanced_test\\run_20260519_085639") {
        throw "Management readiness report still names the older balanced run as the validation run."
    }

    $performanceReviewPath = Join-Path $Root "artifacts/performance_review.md"
    if (Test-Path -LiteralPath $performanceReviewPath) {
        $performanceReview = Get-Content -LiteralPath $performanceReviewPath -Raw
        if ($performanceReview -match 'Configured run:\s*`run_20260519_085639`') {
            throw "Performance review still names the older balanced run as the configured run."
        }
    }

    $readmePath = Join-Path $Root "README.md"
    if (Test-Path -LiteralPath $readmePath) {
        $readme = Get-Content -LiteralPath $readmePath -Raw
        if ($readme -match "current .*validation.*autogluon_balanced_test\\run_20260519_085639") {
            throw "README still presents the older balanced run as the current validation run."
        }
        if ($readme -notmatch "run_20260520_002339") {
            throw "README does not name the latest arbitration source-of-truth run."
        }
    }

    $performanceLoopsPath = Join-Path $Root "artifacts/performance_improvement_loops.json"
    if (Test-Path -LiteralPath $performanceLoopsPath) {
        $performanceLoopsText = Get-Content -LiteralPath $performanceLoopsPath -Raw
        if ($performanceLoopsText -match "run_20260519_085639") {
            throw "Performance improvement loop log still names the older balanced run in active evidence."
        }
    }

    Write-Host "Strict visual-fidelity verification passed."
}
finally {
    if ($serverProcess -ne $null) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
