param(
    [string]$Python = "C:\Users\Adrian Desilvestro\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [int]$Port = 8502,
    [int]$StartupTimeoutSeconds = 90
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $Root "scripts\verify_dashboard.ps1") -Python $Python -Port $Port -StartupTimeoutSeconds $StartupTimeoutSeconds
