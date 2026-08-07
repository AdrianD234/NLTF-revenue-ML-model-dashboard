<#
.SYNOPSIS
    Smoke-test the GitHub workflow's wiring locally with act.

.DESCRIPTION
    Catches the class of mistake that is embarrassing to discover on a hosted
    runner: YAML that does not parse, a job that needs an output nobody sets, a
    condition that can never be true, a bash syntax error in a run block.

    This is a WIRING check. It is not evidence about numbers, timings, Windows
    replay, or clean-room independence. See .actrc for why, and ci/README.md for
    what is authoritative locally.

    By default it only lists and dry-runs jobs, which needs no containers at all
    and is fast. -Execute actually runs the plan and fast jobs.

.EXAMPLE
    pwsh -File scripts/ci_act_smoke.ps1
    pwsh -File scripts/ci_act_smoke.ps1 -Event push
    pwsh -File scripts/ci_act_smoke.ps1 -Execute -Job plan
#>
[CmdletBinding()]
param(
    [ValidateSet('pull_request', 'push', 'workflow_dispatch', 'schedule')]
    [string]$Event = 'pull_request',

    [string]$Job = '',
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not (Get-Command act -ErrorAction SilentlyContinue)) {
    Write-Host @'
act is not installed.

It is optional. Install it only if you want to smoke-test workflow wiring
locally:

  winget install nektos.act

The Docker CI in ci/ is the local authority for model behaviour; act tells you
nothing about that.
'@ -ForegroundColor Yellow
    exit 0
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'act needs Docker. Start Docker Desktop and re-run.' -ForegroundColor Yellow
    exit 0
}

Push-Location $RepoRoot
try {
    Write-Host "`n=== Workflow graph ($Event) ===" -ForegroundColor Cyan
    # -l parses every workflow and resolves the job graph. A malformed `needs:`
    # or an unparseable file fails right here, in about a second.
    & act $Event -l
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'act could not parse the workflows. Fix the YAML above.' -ForegroundColor Red
        exit 1
    }

    Write-Host "`n=== Dry run ($Event) ===" -ForegroundColor Cyan
    $dryArgs = @($Event, '-n')
    if ($Job) { $dryArgs += @('-j', $Job) }
    & act @dryArgs
    $dryStatus = $LASTEXITCODE

    if (-not $Execute) {
        Write-Host "`nDry run finished with exit code $dryStatus." -ForegroundColor Cyan
        Write-Host 'Pass -Execute to actually run the plan/fast jobs in containers.'
        exit $dryStatus
    }

    Write-Host "`n=== Executing ($Event) ===" -ForegroundColor Cyan
    Write-Host 'Reminder: results here are about wiring, not about governed numbers.' -ForegroundColor Yellow
    $runArgs = @($Event)
    $runArgs += if ($Job) { @('-j', $Job) } else { @('-j', 'plan', '-j', 'fast') }
    & act @runArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
