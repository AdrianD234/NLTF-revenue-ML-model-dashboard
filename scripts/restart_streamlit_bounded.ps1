param(
    [string]$Python = "",
    [int]$Port = 8501,
    [string]$App = "app.py",
    [string]$Root = "",
    [int]$StartupTimeoutSeconds = 90,
    [int]$StopTimeoutSeconds = 20,
    [switch]$ReuseHealthy
)

$ErrorActionPreference = "Stop"

if ($StopTimeoutSeconds -le 0) {
    throw "StopTimeoutSeconds must be positive."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $ScriptDir
}
$Root = (Resolve-Path -LiteralPath $Root).Path

$appUrl = "http://localhost:$Port"
$healthUrl = "$appUrl/_stcore/health"
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

if ($ReuseHealthy -and (Test-StreamlitHealth -Url $healthUrl)) {
    Write-Output "STREAMLIT_READY $appUrl existing_listener=true"
    exit 0
}

if (Test-Path -LiteralPath $pidPath) {
    $pidText = (Get-Content -LiteralPath $pidPath -ErrorAction Stop | Select-Object -First 1)
    $streamlitPid = 0
    if ([int]::TryParse($pidText, [ref]$streamlitPid) -and $streamlitPid -gt 0) {
        $process = Get-Process -Id $streamlitPid -ErrorAction SilentlyContinue
        if ($process) {
            Write-Output "STREAMLIT_STOP pid=$streamlitPid"
            Stop-Process -Id $streamlitPid -Force -ErrorAction SilentlyContinue
            try {
                Wait-Process -Id $streamlitPid -Timeout $StopTimeoutSeconds -ErrorAction Stop
            }
            catch {
                throw "Streamlit PID $streamlitPid did not exit within $StopTimeoutSeconds seconds."
            }
        }
    }
}

& (Join-Path $ScriptDir "start_streamlit_bounded.ps1") `
    -Python $Python `
    -Port $Port `
    -App $App `
    -Root $Root `
    -StartupTimeoutSeconds $StartupTimeoutSeconds
