<#
.SYNOPSIS
    Prepares the checked-out FMLV repo on the VM to run the real review app.

.DESCRIPTION
    Step 1 of the real deployment (TODO.md Phase 8b). Assumes 01-bootstrap.ps1 has
    already put `uv` and Python 3.14 on this host, and that the smoke test
    (deploy\windows\02-install-smoketest.ps1) proved the host can run and serve a
    Python service at all.

    Installs the project's own dependencies with `uv sync`, fetches the Playwright
    Chromium build the fetchers need, and creates the `data\` directory the app reads
    and writes at runtime (`src\paths.py`'s `DATA_DIR`, relative to the working
    directory the service is started from).

    Reuses the same shared uv cache and managed Python install the smoke test set up
    under `-RootDir` (default `C:\fmlv`) -- so this doesn't re-download what's already
    on the box, but also so it MUST be run elevated: the FMLVSmokeTest service has
    been writing into that cache as LocalSystem on every start since 02-install-
    smoketest.ps1 installed it, and an unelevated session -- even under an admin
    account -- runs with a filtered token that can't touch what SYSTEM has written.

    Playwright's browser cache is pinned to `<RootDir>\ms-playwright` for the same
    reason, but in the opposite direction: left at its default, Chromium installs
    under *this account's* profile, and 05-install-app-service.ps1's LocalSystem
    service would find nothing there. Both this script and that one must agree on
    `PLAYWRIGHT_BROWSERS_PATH` -- it's set here at install time and again there as
    the service's environment, matching the existing UV_CACHE_DIR/UV_PYTHON_INSTALL_DIR
    pattern.

    Safe to re-run: `uv sync` and `playwright install` are both idempotent.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\04-provision-app.ps1
#>
[CmdletBinding()]
param(
    [string] $RootDir = 'C:\fmlv',
    [string] $UvPath
)

$ErrorActionPreference = 'Stop'

function Write-Section($Text) {
    Write-Host ''
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This script must be run from an elevated PowerShell (Run as Administrator) -- the shared C:\fmlv cache is only writable by SYSTEM/Administrators (see the .DESCRIPTION above).'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

if (-not $UvPath) {
    $found = Get-Command uv -ErrorAction SilentlyContinue
    if ($found) {
        $UvPath = $found.Source
    } else {
        $guess = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
        if (Test-Path $guess) { $UvPath = $guess }
    }
}
if (-not $UvPath -or -not (Test-Path $UvPath)) {
    throw 'uv.exe not found. Run 01-bootstrap.ps1 first, or pass -UvPath explicitly.'
}

Write-Section 'Configuration'
[PSCustomObject]@{
    RepoRoot = $repoRoot
    Uv       = $UvPath
    RootDir  = $RootDir
} | Format-List

# Same shared cache the smoke test warmed, so the service account (and this sync)
# don't each pull their own copy of every dependency and Python build. Playwright's
# browser cache needs the same treatment and for the same reason: left at its default,
# it installs under *this* account's profile, but the service runs as LocalSystem,
# whose profile is a different, empty directory -- it would find nothing there.
$env:UV_CACHE_DIR = Join-Path $RootDir 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $RootDir 'python'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $RootDir 'ms-playwright'

Write-Section 'uv sync'
Push-Location $repoRoot
try {
    & $UvPath sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
}
Write-Host 'Dependencies installed.' -ForegroundColor Green

Write-Section 'Playwright Chromium'
Push-Location $repoRoot
try {
    & $UvPath run playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "playwright install failed (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
}
Write-Host 'Chromium installed.' -ForegroundColor Green

Write-Section 'data\ directory'
# DATA_DIR in src\paths.py is the relative path "data", resolved against the working
# directory the process is started from -- 05-install-app-service.ps1 sets NSSM's
# AppDirectory to $repoRoot so this is where the service will look.
$dataDir = Join-Path $repoRoot 'data'
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Write-Host "Created $dataDir" -ForegroundColor Green
} else {
    Write-Host "Already exists: $dataDir" -ForegroundColor Green
}

Write-Section '.env'
$envFile = Join-Path $repoRoot '.env'
if (Test-Path $envFile) {
    Write-Host "Found $envFile" -ForegroundColor Green
} else {
    Write-Warning "$envFile is missing. The service needs NCC_LOGIN_EMAIL / NCC_LOGIN_PASSWORD."
    Write-Warning "Copy .env.example to .env and fill in real credentials before starting the service."
}

Write-Section 'Done'
Write-Host 'Next: run 05-install-app-service.ps1 from an *elevated* PowerShell.' -ForegroundColor Yellow
