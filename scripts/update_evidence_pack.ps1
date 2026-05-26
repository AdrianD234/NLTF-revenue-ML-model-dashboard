param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePack,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Target = Join-Path $Root "data\dashboard_evidence_pack"
$MaxFileBytes = 50MB
$AllowedRootFiles = @("manifest.json", "README.md", "data_inventory.csv")
$ForbiddenDirs = @("sources", "tables_csv", "logs", "screenshots")

function Resolve-ExistingDirectory {
    param([string]$PathText)
    $resolved = Resolve-Path -LiteralPath $PathText -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $resolved.Path -PathType Container)) {
        throw "Not a directory: $PathText"
    }
    return $resolved.Path
}

function Assert-SlimEvidencePack {
    param([string]$PackPath)

    if (!(Test-Path -LiteralPath (Join-Path $PackPath "manifest.json"))) {
        throw "Source pack is missing manifest.json: $PackPath"
    }
    $dataDir = Join-Path $PackPath "data"
    if (!(Test-Path -LiteralPath $dataDir -PathType Container)) {
        throw "Source pack is missing data folder: $dataDir"
    }
    $parquetFiles = @(Get-ChildItem -LiteralPath $dataDir -Filter "*.parquet" -File)
    if ($parquetFiles.Count -eq 0) {
        throw "Source pack has no data/*.parquet files: $dataDir"
    }
    foreach ($dirName in $ForbiddenDirs) {
        if (Test-Path -LiteralPath (Join-Path $PackPath $dirName)) {
            throw "Source pack contains forbidden raw-output directory: $dirName"
        }
    }
    $badFiles = New-Object System.Collections.Generic.List[string]
    foreach ($file in Get-ChildItem -LiteralPath $PackPath -Recurse -File -Force) {
        $relative = [System.IO.Path]::GetRelativePath($PackPath, $file.FullName)
        $parts = $relative -split '[\\/]'
        $allowed = $false
        if ($parts.Count -eq 1 -and $AllowedRootFiles -contains $file.Name) {
            $allowed = $true
        }
        elseif ($parts[0] -eq "docs") {
            $allowed = $true
        }
        elseif ($parts[0] -eq "data" -and $file.Extension -eq ".parquet") {
            $allowed = $true
        }
        if (-not $allowed) {
            $badFiles.Add($relative)
        }
        if ($file.Length -gt $MaxFileBytes) {
            $badFiles.Add("$relative exceeds 50 MB")
        }
    }
    if ($badFiles.Count -gt 0) {
        throw "Source pack contains forbidden files: $($badFiles -join ', ')"
    }
}

$SourceResolved = Resolve-ExistingDirectory $SourcePack
$TargetResolved = Resolve-ExistingDirectory $Target
$RepoDataRoot = Resolve-ExistingDirectory (Join-Path $Root "data")
if (-not $TargetResolved.StartsWith($RepoDataRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace target outside repo data root: $TargetResolved"
}

Assert-SlimEvidencePack -PackPath $SourceResolved

Write-Host "Replacing evidence pack:"
Write-Host "  Source: $SourceResolved"
Write-Host "  Target: $TargetResolved"

Get-ChildItem -LiteralPath $TargetResolved -Force | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $SourceResolved -Force | Copy-Item -Destination $TargetResolved -Recurse -Force

Assert-SlimEvidencePack -PackPath $TargetResolved

if ($Verify) {
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (!(Test-Path -LiteralPath $python)) {
        $python = "python"
    }
    & pwsh -File (Join-Path $Root "scripts\verify_dashboard.ps1") -Python $python -DataRoot "data\dashboard_evidence_pack" -Port 8501
    if ($LASTEXITCODE -ne 0) {
        throw "verify_dashboard.ps1 failed."
    }
    & $python (Join-Path $Root "scripts\check_streamlit_deploy_readiness.py")
    if ($LASTEXITCODE -ne 0) {
        throw "check_streamlit_deploy_readiness.py failed."
    }
}

Write-Host ""
Write-Host "Evidence pack updated. Review git diff, then run:"
Write-Host 'git add -- data/dashboard_evidence_pack scripts/update_evidence_pack.ps1 scripts/check_streamlit_deploy_readiness.py requirements.txt requirements-dev.txt runtime.txt .streamlit/config.toml docs/STREAMLIT_CLOUD_DEPLOYMENT.md README.md app.py model_dashboard/evidence_pack.py'
Write-Host 'git commit -m "Prepare Streamlit Cloud evidence pack deployment"'
