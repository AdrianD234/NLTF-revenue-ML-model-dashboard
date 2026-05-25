param(
    [int]$MaxPasses = 120,
    [string]$Python = "C:\Users\Adrian Desilvestro\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [string]$DataRoot = "C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\model_diagnostic_audit_pack",
    [int]$VerifierPort = 8501
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

New-Item -ItemType Directory -Force -Path "artifacts/logs" | Out-Null
New-Item -ItemType Directory -Force -Path "artifacts/screenshots" | Out-Null

function Invoke-Logged {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$PassLog,
        [switch]$Append
    )

    $teeArgs = @{ FilePath = $PassLog }
    if ($Append) {
        $teeArgs["Append"] = $true
    }

    Write-Host "Running $Label"
    "================================================================================" | Tee-Object @teeArgs | Out-Null
    "Running $Label" | Tee-Object -FilePath $PassLog -Append | Out-Null
    "Command: $FilePath $($Arguments -join ' ')" | Tee-Object -FilePath $PassLog -Append | Out-Null
    & $FilePath @Arguments 2>&1 | Tee-Object -FilePath $PassLog -Append | Out-Null
    $code = $LASTEXITCODE
    "Exit code: $code" | Tee-Object -FilePath $PassLog -Append | Out-Null
    return [pscustomobject]@{
        Label = $Label
        ExitCode = $code
        Passed = ($code -eq 0)
    }
}

function Write-AgentState {
    param(
        [int]$PassNumber,
        [string]$PassLog,
        [string]$NextDefect = "Inspect failed gates and repair the highest-value dashboard defect."
    )

    $passed = 0
    $failed = "unknown"
    $failedList = @()
    $resultsPath = "artifacts/80_gate_validation_results.json"
    if (Test-Path -LiteralPath $resultsPath) {
        try {
            $results = Get-Content $resultsPath -Raw | ConvertFrom-Json
            $passed = $results.passed_gates
            $failed = $results.failed_gates
            $failedList = @($results.gates | Where-Object { $_.status -ne "PASS" } | Select-Object -First 12)
        }
        catch {
            $failed = "unreadable"
        }
    }

    $backlogItems = @()
    if (Test-Path -LiteralPath "BUG_BACKLOG.md") {
        $backlogItems = @(Select-String -LiteralPath "BUG_BACKLOG.md" -Pattern "- \[ \]" | ForEach-Object { $_.Line.Trim() })
    }

    $failedText = if ($failedList.Count -gt 0) {
        ($failedList | ForEach-Object { "- Gate $($_.id): $($_.evidence)" }) -join [Environment]::NewLine
    } else {
        "- No failed-gate detail available yet."
    }
    $backlogText = if ($backlogItems.Count -gt 0) {
        ($backlogItems | ForEach-Object { "- $_" }) -join [Environment]::NewLine
    } else {
        "- No open backlog items detected."
    }

    $state = @"
# Agent State

Status: IN PROGRESS
Current loop number: $PassNumber of $MaxPasses executed in the latest run
Passed gates: $passed
Failed gates: $failed
Latest log: $PassLog
Retained CSV-preview smoke-test run: run_20260520_002339

## Failed Gates

$failedText

## Open Backlog Items

$backlogText

## Next Exact Command

``````powershell
            pwsh -File scripts\run_recursive_dashboard_validation.ps1 -MaxPasses 120 -Python "$Python" -DataRoot "$DataRoot" -VerifierPort $VerifierPort
``````

## Next Defect To Fix

$NextDefect
"@
    Set-Content -Path ".agent_state.md" -Value $state -Encoding utf8
}

for ($i = 1; $i -le $MaxPasses; $i++) {
    Write-Host "================================================================================"
    Write-Host "Recursive validation pass $i of $MaxPasses"
    Write-Host "================================================================================"

    $passLog = "artifacts/logs/recursive_pass_$i.log"

    try {
        $commandResults = @()
        $commandResults += Invoke-Logged -Label "compileall" -FilePath $Python -Arguments @("-m", "compileall", ".") -PassLog $passLog
        $commandResults += Invoke-Logged -Label "inspect_parquet_schema" -FilePath $Python -Arguments @("scripts\inspect_parquet_schema.py", "--data-root", $DataRoot) -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "validate_dashboard_data" -FilePath $Python -Arguments @("scripts\validate_dashboard_data.py", "--data-root", $DataRoot) -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "validate_chart_sources" -FilePath $Python -Arguments @("scripts\validate_chart_sources.py", "--data-root", $DataRoot) -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "validate_semantic_labels" -FilePath $Python -Arguments @("scripts\validate_semantic_labels.py", "--data-root", $DataRoot) -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "pytest" -FilePath $Python -Arguments @("-m", "pytest", "-q") -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "validate_100_gates" -FilePath $Python -Arguments @("scripts\validate_80_gates.py", "--data-root", $DataRoot) -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "validate_120_gates" -FilePath $Python -Arguments @("scripts\validate_120_gates.py", "--data-root", $DataRoot) -PassLog $passLog -Append
        $commandResults += Invoke-Logged -Label "verify_dashboard" -FilePath "pwsh" -Arguments @("-File", "scripts\verify_dashboard.ps1", "-Python", $Python, "-DataRoot", $DataRoot, "-Port", "$VerifierPort") -PassLog $passLog -Append

        $resultsPath = "artifacts/80_gate_validation_results.json"
        if (!(Test-Path $resultsPath)) {
            throw "Missing $resultsPath"
        }

        $results = Get-Content $resultsPath -Raw | ConvertFrom-Json
        $failed = @($results.gates | Where-Object { $_.status -ne "PASS" })
        $failedCommands = @($commandResults | Where-Object { -not $_.Passed })

        $backlogText = Get-Content "BUG_BACKLOG.md" -Raw
        $openBacklog = $backlogText -match "- \[ \]"

        if ($failed.Count -eq 0 -and $failedCommands.Count -eq 0 -and -not $openBacklog) {
            Write-Host "All 120 validation gates passed and BUG_BACKLOG.md has no open items."
            Write-Host "Completed after pass $i."
            exit 0
        }

        Write-Host "Validation did not fully pass. Failed commands: $($failedCommands.Count). Failed gates: $($failed.Count). Open backlog: $openBacklog"
        Write-Host "Codex must inspect artifacts and repair before rerunning."
        $nextDefect = if ($failedCommands.Count -gt 0) {
            "First failed command: $($failedCommands[0].Label) exited $($failedCommands[0].ExitCode). Review $passLog and artifacts/80_gate_validation_results.json."
        } else {
            "Review non-PASS gates in artifacts/80_gate_validation_results.json."
        }
        Write-AgentState -PassNumber $i -PassLog $passLog -NextDefect $nextDefect
    }
    catch {
        Write-Host "Validation pass $i failed: $($_.Exception.Message)"
        Write-Host "Codex must inspect logs and repair."
        Write-AgentState -PassNumber $i -PassLog $passLog -NextDefect $_.Exception.Message
    }
}

throw "Reached $MaxPasses validation passes without all 120 gates passing."
