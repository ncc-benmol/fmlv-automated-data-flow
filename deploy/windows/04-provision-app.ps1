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
    under `-RootDir` (default `C:\fmlv`), so this doesn't re-download what's already
    on the box. Run this as yourself, not elevated -- 05-install-app-service.ps1 is
    the one that needs Administrator.

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
# don't each pull their own copy of every dependency and Python build.
$env:UV_CACHE_DIR = Join-Path $RootDir 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $RootDir 'python'

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
