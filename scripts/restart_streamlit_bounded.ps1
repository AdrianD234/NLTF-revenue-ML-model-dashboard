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
    param(
        [int]$Port,
        [int]$TimeoutMilliseconds = 1500
    )

    $client = $null
    $waitHandle = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $asyncResult = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $waitHandle = $asyncResult.AsyncWaitHandle
        if (-not $waitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        $stream = $client.GetStream()
        $stream.ReadTimeout = $TimeoutMilliseconds
        $stream.WriteTimeout = $TimeoutMilliseconds

        # Avoid Invoke-WebRequest here; on this Windows host it has previously
        # ignored its timeout and left startup commands stuck for hours.
        $request = "GET /_stcore/health HTTP/1.1`r`nHost: localhost:$Port`r`nConnection: close`r`n`r`n"
        $requestBytes = [System.Text.Encoding]::ASCII.GetBytes($request)
        $stream.Write($requestBytes, 0, $requestBytes.Length)

        $buffer = New-Object byte[] 128
        $read = $stream.Read($buffer, 0, $buffer.Length)
        if ($read -le 0) {
            return $false
        }

        $status = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $read)
        return $status.StartsWith("HTTP/1.1 200") -or $status.StartsWith("HTTP/1.0 200")
    }
    catch {
        return $false
    }
    finally {
        if ($waitHandle) {
            $waitHandle.Dispose()
        }
        if ($client) {
            $client.Close()
            $client.Dispose()
        }
    }
}

if ($ReuseHealthy -and (Test-StreamlitHealth -Port $Port)) {
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
