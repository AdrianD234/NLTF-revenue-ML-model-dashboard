<#
.SYNOPSIS
    Run a CI tier locally in the clean-room container.

.DESCRIPTION
    This is the local authority for governed model questions. It never runs the
    suite against your working checkout: it creates a disposable detached git
    worktree at an exact commit, mounts THAT into the container, and deletes it
    afterwards. Your checkout is not read, not locked and not modified.

    Byte-exactness comes from the repository pinning `* -text` in .gitattributes,
    so a worktree checkout reproduces committed bytes without line-ending
    translation. The wrapper verifies this rather than assuming it.

    No locally installed Python is required. Everything runs inside the image.

.PARAMETER Tier
    fast | affected | full | profile | replay | pack-status | databricks-bundle | shell

.PARAMETER Base
    Base ref for the `affected` tier's change plan. Default origin/main.

.PARAMETER Ref
    Commit to test. Default HEAD. Uncommitted work is NOT included - commit it
    (or stash to a temporary commit) first; that is what makes the result mean
    something.

.PARAMETER Engine
    Engine argument passed through to the replay tier.

.EXAMPLE
    pwsh -File scripts/ci_local.ps1 -Tier fast
    pwsh -File scripts/ci_local.ps1 -Tier affected -Base origin/main
    pwsh -File scripts/ci_local.ps1 -Tier full
    pwsh -File scripts/ci_local.ps1 -Tier profile
    pwsh -File scripts/ci_local.ps1 -Tier replay -Engine ar1
#>
[CmdletBinding()]
param(
    [ValidateSet('fast', 'affected', 'full', 'profile', 'replay', 'pack-status', 'databricks-bundle', 'shell')]
    [string]$Tier = 'fast',

    [string]$Base = 'origin/main',
    [string]$Ref = 'HEAD',
    [string]$Engine = '',
    [switch]$Rebuild,
    [switch]$KeepWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Fail([string]$Message, [int]$Code = 2) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit $Code
}

# ---------------------------------------------------------------------------
# 1. Docker must be reachable - natively, or through WSL
# ---------------------------------------------------------------------------
# Docker Engine installed inside WSL publishes NO Windows-side docker.exe. This
# script therefore cannot assume a native client: when one is absent but WSL is
# present, it delegates the whole tier to scripts/ci_local.sh inside the
# distribution, against a checkout on the Linux filesystem.
#
# That last part matters for more than tidiness. /mnt/c is a 9p mount, and
# bind-mounting a large tree from it into a container is slow enough to distort
# a timed run - which would make every benchmark this project produces suspect.
Write-Section 'Checking Docker'
$docker = Get-Command docker -ErrorAction SilentlyContinue

if (-not $docker) {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) {
        Fail @'
Docker is not on PATH, and WSL is not available either.

The container is the only local environment that matches CI (Python 3.11), so
governed questions cannot be settled without it.

Install Docker ENGINE inside WSL - not Docker Desktop, which carries a
commercial licensing requirement for government entities and larger
organisations:

    wsl
    bash ci/install_docker_engine_wsl.sh

Until then the honest fallback is the hosted CI, or the developer .venv for
non-governed work only - it is a different Python and numpy build and cannot
settle a numerical disagreement. See ci/README.md.
'@
    }

    Write-Host 'No Windows docker client; delegating to Docker Engine inside WSL.' -ForegroundColor Cyan

    # Does the distribution have a working daemon the current user can reach?
    & wsl.exe -- bash -lc 'docker version --format "{{.Server.Os}}" >/dev/null 2>&1'
    if ($LASTEXITCODE -ne 0) {
        & wsl.exe -- bash -lc 'sudo -n docker version >/dev/null 2>&1'
        if ($LASTEXITCODE -eq 0) {
            Fail @'
Docker inside WSL works only under sudo, and this wrapper cannot supply a
password non-interactively.

Either grant your WSL user direct access (note: docker group membership is
equivalent to passwordless root inside that distribution - a real privilege
decision, which is why the installer does not do it for you):

    wsl -- bash -lc "sudo usermod -aG docker \$USER"
    wsl --shutdown

...or run the tiers yourself from inside WSL:

    wsl
    cd ~/nltf-ci/repo
    sudo scripts/ci_local.sh --tier fast
'@
        }
        Fail @'
Docker is installed in WSL but the daemon is not responding. Inside WSL:

    sudo systemctl status docker
    sudo systemctl start docker
'@
    }

    # Mirror the Windows checkout into the Linux filesystem and run there.
    $linuxRepo = '$HOME/nltf-ci/repo'
    $winRepoForWsl = (& wsl.exe -- wslpath -a "$RepoRoot").Trim()
    $tierArgsForSh = @("--tier", $Tier, "--base", $Base, "--ref", $Ref)
    if ($Engine) { $tierArgsForSh += @("--engine", $Engine) }
    if ($Rebuild) { $tierArgsForSh += "--rebuild" }
    $joined = $tierArgsForSh -join ' '

    $bootstrap = @"
set -e
mkdir -p `$HOME/nltf-ci
if [ ! -d $linuxRepo/.git ]; then
  echo 'Cloning into the Linux filesystem (first run only)...'
  git clone --no-checkout '$winRepoForWsl' $linuxRepo
fi
cd $linuxRepo
git remote set-url origin '$winRepoForWsl'
git fetch --quiet origin '+refs/heads/*:refs/remotes/origin/*'
git checkout --quiet --detach $(& git -C $RepoRoot rev-parse $Ref)
exec bash scripts/ci_local.sh $joined
"@

    & wsl.exe -- bash -lc $bootstrap
    exit $LASTEXITCODE
}

& docker version --format '{{.Server.Os}}' 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail @'
Docker is installed but the daemon is not responding.

If you installed Docker Engine inside WSL, run the tiers from inside WSL with
scripts/ci_local.sh - the Windows-side `docker` client will not reach a daemon
that only listens inside the distribution. Check it there with:

    sudo systemctl status docker
'@
}
$serverOs = (& docker version --format '{{.Server.Os}}' 2>$null)
if ($serverOs -and $serverOs.Trim() -ne 'linux') {
    Fail "Docker is in $serverOs-container mode; this image needs Linux containers."
}
Write-Host "Docker OK (linux containers)"

# ---------------------------------------------------------------------------
# 2. Resolve the exact source SHA
# ---------------------------------------------------------------------------
Write-Section 'Resolving source'
$Sha = (& git -C $RepoRoot rev-parse $Ref 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $Sha) { Fail "Cannot resolve ref '$Ref'." }
$Sha = $Sha.Trim()
$ShortSha = $Sha.Substring(0, 12)
Write-Host "Testing commit $Sha"

$dirty = (& git -C $RepoRoot status --porcelain)
if ($dirty) {
    Write-Host 'NOTE: your checkout has uncommitted changes. They are NOT included;' -ForegroundColor Yellow
    Write-Host "      this run tests committed state $ShortSha." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 3. Refuse concurrent runs
# ---------------------------------------------------------------------------
# A pack build racing a full pytest, or two full suites at once, produces
# results that cannot be attributed to either. Serialise rather than explain.
$LockPath = Join-Path $RepoRoot 'artifacts/ci_local/.lock'
New-Item -ItemType Directory -Force -Path (Split-Path $LockPath) | Out-Null
if (Test-Path $LockPath) {
    $held = Get-Content $LockPath -Raw -ErrorAction SilentlyContinue
    Fail @"
Another local CI run holds the lock:
$held
Wait for it, or remove $LockPath if that run is definitely dead.
"@
}
"tier=$Tier sha=$ShortSha pid=$PID started=$((Get-Date).ToUniversalTime().ToString('o'))" |
    Set-Content -Path $LockPath -Encoding utf8

$WorktreePath = Join-Path ([System.IO.Path]::GetTempPath()) "nltf-ci-$ShortSha-$PID"
$OutDir = Join-Path $RepoRoot "artifacts/ci_local/$ShortSha"
$ExitCode = 1
$Elapsed = $null

try {
    # -----------------------------------------------------------------------
    # 4. Disposable, byte-exact source copy
    # -----------------------------------------------------------------------
    Write-Section 'Creating disposable worktree'
    & git -C $RepoRoot worktree add --detach --quiet $WorktreePath $Sha
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the disposable worktree.' }
    Write-Host "Worktree: $WorktreePath"

    # Prove byte-exactness rather than trusting .gitattributes to still say so.
    $drift = (& git -C $WorktreePath status --porcelain)
    if ($drift) {
        Fail @"
The freshly created worktree is already dirty, which means checkout is not
byte-exact (most likely a .gitattributes line-ending rule changed):

$drift

Refusing to run: a numerical result from a tree that does not match the commit
is not evidence.
"@
    }
    Write-Host 'Worktree is byte-exact against the commit.'

    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

    # -----------------------------------------------------------------------
    # 5. Build the image
    # -----------------------------------------------------------------------
    Write-Section 'Building the CI image'
    $buildArgs = @('build', '-f', (Join-Path $RepoRoot 'ci/Dockerfile'), '-t', 'nltf-ci:local', $RepoRoot)
    if ($Rebuild) { $buildArgs += '--no-cache' }
    $env:DOCKER_BUILDKIT = '1'
    & docker @buildArgs
    if ($LASTEXITCODE -ne 0) { Fail 'Image build failed.' $LASTEXITCODE }

    # -----------------------------------------------------------------------
    # 6. Work out what this tier has to run
    # -----------------------------------------------------------------------
    $tierArgs = @()
    if ($Tier -eq 'affected') {
        Write-Section 'Planning affected tests'
        # The planner runs inside the container so no host Python is needed, but
        # it needs the git history, which the disposable worktree shares.
        $planJson = & docker run --rm `
            -v "${WorktreePath}:/work" `
            -v "${RepoRoot}/.git:/repo/.git:ro" `
            -w /work --entrypoint python nltf-ci:local `
            scripts/ci_plan.py --base $Base --head $Sha --format json
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Planner failed; escalating this run to the full tier.' -ForegroundColor Yellow
            $Tier = 'full'
        }
        else {
            $planJson | Set-Content -Path (Join-Path $OutDir 'ci_plan.json') -Encoding utf8
            $plan = $planJson | ConvertFrom-Json
            Write-Host "scopes: $($plan.scopes -join ', ')  risk: $($plan.risk_level)"
            if ($plan.requires_full_assurance) {
                Write-Host 'Plan requires full assurance; running the full tier.' -ForegroundColor Yellow
                $Tier = 'full'
            }
            else {
                $tierArgs = @($plan.required_test_paths)
                if (-not $tierArgs -or $tierArgs.Count -eq 0) {
                    Write-Host 'Plan selected no tests. Nothing to run.' -ForegroundColor Green
                    $ExitCode = 0
                    return
                }
                Write-Host "selected $($tierArgs.Count) test path(s)"
            }
        }
    }
    elseif ($Tier -eq 'replay' -and $Engine) {
        $tierArgs = @('--engine', $Engine)
    }

    # -----------------------------------------------------------------------
    # 7. Run the tier
    # -----------------------------------------------------------------------
    Write-Section "Running tier: $Tier"
    $started = Get-Date
    & docker run --rm `
        -e CI_SOURCE_SHA=$Sha `
        -e CI_OUT_DIR=/out `
        -v "${WorktreePath}:/work" `
        -v "${OutDir}:/out" `
        nltf-ci:local $Tier @tierArgs
    $ExitCode = $LASTEXITCODE
    $elapsed = (Get-Date) - $started

    $Elapsed = (Get-Date) - $started

    Write-Host ''
    Write-Host ("Tier '{0}' finished in {1:mm\:ss} with exit code {2}" -f $Tier, $Elapsed, $ExitCode)
    Write-Host "Artefacts: $OutDir"
}
finally {
    # -----------------------------------------------------------------------
    # 8. Did the run mutate the source copy?
    # -----------------------------------------------------------------------
    # In `finally` on purpose. The container's own EXIT trap is the primary
    # gate, but if the container is killed, the run is interrupted, or docker
    # itself fails, that trap never fires - and those are exactly the cases
    # where a half-finished write is most likely to have been left behind.
    # This check must therefore survive every exit path too, and it must run
    # BEFORE the worktree is removed.
    if ($WorktreePath -and (Test-Path $WorktreePath)) {
        Write-Section 'Checking the run did not mutate the source copy'
        # No path exclusions: artifacts/ and data/ are precisely where a
        # governed value would move. The container gate knows which scratch
        # paths are legitimately writable; here we report everything and let
        # the reader judge.
        $mutated = (& git -C $WorktreePath status --porcelain)
        if ($mutated) {
            Write-Host 'The run left the source copy modified:' -ForegroundColor Yellow
            Write-Host ($mutated -join [Environment]::NewLine)
            $mutated | Set-Content -Path (Join-Path $OutDir 'tracked_mutations.txt') -Encoding utf8
            # A tier that mutated governed content must not report success.
            if ($ExitCode -eq 0) {
                Write-Host 'FAILING: governed or tracked content moved during this tier.' -ForegroundColor Red
                $ExitCode = 3
            }
        }
        else {
            Write-Host 'Source copy is unchanged.'
        }

        if ($OutDir -and (Test-Path $OutDir)) {
            [pscustomobject]@{
                tier            = $Tier
                source_sha      = $Sha
                base            = $Base
                exit_code       = $ExitCode
                elapsed_seconds = if ($Elapsed) { [math]::Round($Elapsed.TotalSeconds, 1) } else { $null }
                tracked_mutated = [bool]$mutated
                output_dir      = $OutDir
            } | ConvertTo-Json | Set-Content -Path (Join-Path $OutDir "result_$Tier.json") -Encoding utf8
        }
    }

    # -----------------------------------------------------------------------
    # 9. Always clean up. The checkout must be exactly as we found it.
    # -----------------------------------------------------------------------
    if (-not $KeepWorktree -and (Test-Path $WorktreePath)) {
        & git -C $RepoRoot worktree remove --force $WorktreePath 2>&1 | Out-Null
        if (Test-Path $WorktreePath) {
            Remove-Item -Recurse -Force $WorktreePath -ErrorAction SilentlyContinue
        }
        & git -C $RepoRoot worktree prune 2>&1 | Out-Null
    }
    Remove-Item -Force $LockPath -ErrorAction SilentlyContinue
}

exit $ExitCode
