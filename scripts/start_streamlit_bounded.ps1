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

$alreadyHealthy = Test-StreamlitHealth -Port $Port
if ($alreadyHealthy) {
    if ($ReuseHealthy) {
        Write-Output "STREAMLIT_READY $appUrl existing_listener=true"
        exit 0
    }

    throw "Port $Port already serves a healthy Streamlit endpoint. Use -ReuseHealthy or scripts\restart_streamlit_bounded.ps1 for an intentional restart."
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
    if (Test-StreamlitHealth -Port $Port) {
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
