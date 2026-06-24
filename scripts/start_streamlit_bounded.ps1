param(
    [string]$Python = "",
    [int]$Port = 8501,
    [string]$App = "app.py",
    [string]$Root = "",
    [int]$StartupTimeoutSeconds = 90,
    [switch]$ReuseHealthy
)

$ErrorActionPreference = "Stop"

if ($StartupTimeoutSeconds -le 0) {
    throw "StartupTimeoutSeconds must be positive."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $ScriptDir
}
$Root = (Resolve-Path -LiteralPath $Root).Path

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

$appPath = Join-Path $Root $App
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "Streamlit app not found: $appPath"
}

$appUrl = "http://localhost:$Port"
$healthUrl = "$appUrl/_stcore/health"
$logDir = Join-Path $Root "artifacts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$serverLog = Join-Path $logDir "streamlit.$Port.out.log"
$serverErr = Join-Path $logDir "streamlit.$Port.err.log"
$pidPath = Join-Path $Root ".streamlit_$Port.pid"

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

$existing = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -in @("Listen", "Bound") })
if ($existing.Count -gt 0) {
    if ($ReuseHealthy -and (Test-StreamlitHealth -Url $healthUrl)) {
        Write-Output "STREAMLIT_READY $appUrl existing_listener=true"
        exit 0
    }

    throw "Port $Port is already in use. Use -ReuseHealthy only when the existing listener is the dashboard you want."
}

$env:PYTHONPATH = $Root
$args = @(
    "-m", "streamlit", "run", $App,
    "--server.port", "$Port",
    "--server.headless", "true",
    "--browser.gatherUsageStats", "false"
)

Write-Host "STREAMLIT_START port=$Port timeout_seconds=$StartupTimeoutSeconds"
Write-Host "Root: $Root"
Write-Host "Python: $Python"
Write-Host "StdoutLog: $serverLog"
Write-Host "StderrLog: $serverErr"

$process = Start-Process `
    -FilePath $Python `
    -ArgumentList $args `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $serverLog `
    -RedirectStandardError $serverErr `
    -PassThru

$process.Id | Set-Content -LiteralPath $pidPath

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
$ok = $false
while ((Get-Date) -lt $deadline) {
    if (Test-StreamlitHealth -Url $healthUrl) {
        $ok = $true
        break
    }

    $process.Refresh()
    if ($process.HasExited) {
        break
    }

    Start-Sleep -Seconds 2
}

if (-not $ok) {
    $process.Refresh()
    Write-Host "STREAMLIT_START_FAILED pid=$($process.Id) exited=$($process.HasExited)"
    Write-LogTail -Path $serverLog -Title "stdout"
    Write-LogTail -Path $serverErr -Title "stderr"
    if (-not $process.HasExited) {
        Stop-ProcessTree -RootProcessId $process.Id
    }
    throw "Streamlit did not become healthy at $appUrl within $StartupTimeoutSeconds seconds"
}

Write-Output "STREAMLIT_READY $appUrl pid=$($process.Id)"
