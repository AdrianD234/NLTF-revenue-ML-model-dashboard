param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [string[]]$Arguments = @(),

    [int]$TimeoutSeconds = 90,

    [string]$WorkingDirectory = "",

    [string]$Label = "bounded-command",

    [string]$LogDirectory = ""
)

$ErrorActionPreference = "Stop"

if ($TimeoutSeconds -le 0) {
    throw "TimeoutSeconds must be positive."
}

if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
    $WorkingDirectory = (Get-Location).Path
}

if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
    throw "WorkingDirectory does not exist: $WorkingDirectory"
}

if ([string]::IsNullOrWhiteSpace($LogDirectory)) {
    $LogDirectory = Join-Path $WorkingDirectory "artifacts\logs"
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null

$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]', '_').Trim("_")
if ([string]::IsNullOrWhiteSpace($safeLabel)) {
    $safeLabel = "bounded-command"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $LogDirectory "$stamp.$safeLabel.out.log"
$stderrLog = Join-Path $LogDirectory "$stamp.$safeLabel.err.log"

function Write-LogTail {
    param(
        [string]$Path,
        [string]$Title,
        [int]$Lines = 80
    )

    if (Test-Path -LiteralPath $Path) {
        Write-Host "--- $Title tail ($Path) ---"
        Get-Content -LiteralPath $Path -Tail $Lines
    }
}

function Stop-ProcessTree {
    param([int]$RootProcessId)

    $children = @()
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" -ErrorAction SilentlyContinue)
    }
    catch {
        $children = @()
    }

    foreach ($child in $children) {
        Stop-ProcessTree -RootProcessId ([int]$child.ProcessId)
    }

    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

function ConvertTo-StartProcessArgument {
    param([string]$Argument)

    if ($null -eq $Argument) {
        return '""'
    }

    if ($Argument -notmatch '[\s"]') {
        return $Argument
    }

    $escaped = $Argument -replace '"', '\"'
    return '"' + $escaped + '"'
}

$processArguments = @($Arguments | ForEach-Object { ConvertTo-StartProcessArgument -Argument $_ })
$commandLine = "$FilePath $($processArguments -join ' ')"
Write-Host "BOUNDED_COMMAND_START label=$Label timeout_seconds=$TimeoutSeconds"
Write-Host "WorkingDirectory: $WorkingDirectory"
Write-Host "Command: $commandLine"
Write-Host "StdoutLog: $stdoutLog"
Write-Host "StderrLog: $stderrLog"

$process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $processArguments `
    -WorkingDirectory $WorkingDirectory `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Host "PID: $($process.Id)"

$completed = $process.WaitForExit($TimeoutSeconds * 1000)
if (-not $completed) {
    Write-Host "BOUNDED_COMMAND_TIMEOUT label=$Label pid=$($process.Id) timeout_seconds=$TimeoutSeconds"
    Stop-ProcessTree -RootProcessId $process.Id
    Write-LogTail -Path $stdoutLog -Title "stdout"
    Write-LogTail -Path $stderrLog -Title "stderr"
    throw "Command timed out after $TimeoutSeconds seconds: $commandLine"
}

$process.Refresh()
$exitCode = $process.ExitCode
Write-Host "BOUNDED_COMMAND_EXIT label=$Label exit_code=$exitCode"

if ($exitCode -ne 0) {
    Write-LogTail -Path $stdoutLog -Title "stdout"
    Write-LogTail -Path $stderrLog -Title "stderr"
    throw "Command failed with exit code ${exitCode}: $commandLine"
}

Write-LogTail -Path $stdoutLog -Title "stdout" -Lines 20
Write-LogTail -Path $stderrLog -Title "stderr" -Lines 20
