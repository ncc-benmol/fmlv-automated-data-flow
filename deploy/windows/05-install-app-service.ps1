<#
.SYNOPSIS
    Installs the FMLV review app as an auto-starting Windows service.

.DESCRIPTION
    Step 2 of the real deployment (TODO.md Phase 8b). Wraps
    `uv run uvicorn src.webapp.serve:app` as a Windows service using NSSM (the same
    binary the smoke test installed to `C:\fmlv\tools\nssm.exe`), opens the port on
    the local Windows Firewall, starts it, and verifies it responds.

    Runs as LocalSystem by default -- the same account the deployment smoke test
    proved works on this VM (TODO.md 8a). The service holds NCC login credentials in
    `.env`; if that account's privilege ever becomes a concern, pass
    -ServiceAccount/-ServicePassword for a dedicated local account instead. No code
    change needed either way.

    Must be run from an ELEVATED PowerShell, after 04-provision-app.ps1. Safe to
    re-run: an existing service of the same name is removed and reinstalled.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\05-install-app-service.ps1

.EXAMPLE
    # Bind a different port, and run as a named account rather than LocalSystem
    .\05-install-app-service.ps1 -Port 8001 -ServiceAccount 'NCC-AI1\svc_fmlv'
#>
[CmdletBinding()]
param(
    [string] $ServiceName = 'FMLVReviewApp',
    [int]    $Port = 8000,

    # Shared with the smoke test: NSSM, the uv cache and uv-managed Python builds.
    [string] $RootDir = 'C:\fmlv',

    [string] $UvPath,

    # Leave empty for LocalSystem.
    [string] $ServiceAccount,
    [string] $ServicePassword
)

$ErrorActionPreference = 'Stop'

function Write-Section($Text) {
    Write-Host ''
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

# --- Preconditions -----------------------------------------------------------------

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This script must be run from an elevated PowerShell (Run as Administrator).'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$envFile = Join-Path $repoRoot '.env'
if (-not (Test-Path $envFile)) {
    throw "$envFile not found. Create it (see .env.example) with real NCC credentials before installing the service."
}

$dataDir = Join-Path $repoRoot 'data'
if (-not (Test-Path $dataDir)) {
    throw "$dataDir not found. Run 04-provision-app.ps1 first."
}

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

$nssmExe = Join-Path $RootDir 'tools\nssm.exe'
if (-not (Test-Path $nssmExe)) {
    throw "$nssmExe not found. Run 02-install-smoketest.ps1 at least once first -- it installs NSSM, which this script reuses."
}

Write-Section 'Configuration'
[PSCustomObject]@{
    ServiceName = $ServiceName
    Port        = $Port
    RepoRoot    = $repoRoot
    Uv          = $UvPath
    Nssm        = $nssmExe
    Account     = if ($ServiceAccount) { $ServiceAccount } else { 'LocalSystem' }
} | Format-List

$logDir = Join-Path $RootDir 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

# --- Install the service ------------------------------------------------------------

Write-Section 'Service'
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing the existing '$ServiceName' service first ..."
    & $nssmExe stop $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
    & $nssmExe remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
}

$appArgs = "run uvicorn src.webapp.serve:app --host 0.0.0.0 --port $Port"
& $nssmExe install $ServiceName $UvPath $appArgs
if ($LASTEXITCODE -ne 0) { throw "nssm install failed (exit $LASTEXITCODE)." }

# AppDirectory matters twice over: it's how uv finds pyproject.toml to run `uvicorn`
# in the project's environment, and it's the working directory paths.py resolves
# DATA_DIR/CONFIG_DIR ("data", "config") against.
& $nssmExe set $ServiceName AppDirectory $repoRoot                          | Out-Null
& $nssmExe set $ServiceName DisplayName 'FMLV review app'                   | Out-Null
& $nssmExe set $ServiceName Description  'FMLV data-flow review app (uvicorn), see DESIGN.md.' | Out-Null
& $nssmExe set $ServiceName Start SERVICE_AUTO_START                        | Out-Null

& $nssmExe set $ServiceName AppStdout (Join-Path $logDir 'fmlv-app.out.log') | Out-Null
& $nssmExe set $ServiceName AppStderr (Join-Path $logDir 'fmlv-app.err.log') | Out-Null
& $nssmExe set $ServiceName AppRotateFiles 1        | Out-Null
& $nssmExe set $ServiceName AppRotateOnline 1       | Out-Null
& $nssmExe set $ServiceName AppRotateBytes 1048576  | Out-Null

# Same shared cache the smoke test and 04-provision-app.ps1 used -- without this the
# service account gets its own empty cache and re-downloads/rebuilds everything.
& $nssmExe set $ServiceName AppEnvironmentExtra `
    "UV_CACHE_DIR=$(Join-Path $RootDir 'uv-cache')" `
    "UV_PYTHON_INSTALL_DIR=$(Join-Path $RootDir 'python')" | Out-Null

& $nssmExe set $ServiceName AppExit Default Restart | Out-Null
& $nssmExe set $ServiceName AppRestartDelay 5000    | Out-Null

if ($ServiceAccount) {
    & $nssmExe set $ServiceName ObjectName $ServiceAccount $ServicePassword | Out-Null
    Write-Host "Service will run as $ServiceAccount"
}

Write-Host 'Service registered.' -ForegroundColor Green

# --- Firewall -----------------------------------------------------------------------

Write-Section 'Firewall'
$ruleName = "$ServiceName (TCP $Port)"
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host 'Inbound rule already exists.' -ForegroundColor Green
} else {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port -Profile Any | Out-Null
    Write-Host "Opened inbound TCP $Port on the local Windows Firewall." -ForegroundColor Green
}
Write-Host 'Note: this only opens the *host* firewall. Reaching this port from your own' -ForegroundColor Yellow
Write-Host 'machine also needs the VM address IT confirmed for the smoke test, 192.168.16.43' -ForegroundColor Yellow
Write-Host '(TODO.md 8a) -- ask IT to open this port on that address if it is not already.' -ForegroundColor Yellow

# --- Start and verify ---------------------------------------------------------------

Write-Section 'Starting'
Start-Service -Name $ServiceName
$deadline = (Get-Date).AddSeconds(60)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $healthy) {
    Write-Host 'Service did not answer within 60 seconds.' -ForegroundColor Red
    Get-Service -Name $ServiceName | Format-List Name, Status, StartType
    Write-Host "Check the logs: $logDir\fmlv-app.err.log"
    throw 'FMLV review app service failed to come up.'
}

Write-Host 'Service is up.' -ForegroundColor Green

$ips = Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -ne '127.0.0.1' } |
       Select-Object -ExpandProperty IPAddress

Write-Section 'Next steps'
Write-Host "1. From THIS machine:  http://127.0.0.1:$Port/"
foreach ($ip in $ips) {
    Write-Host "2. From YOUR machine: http://${ip}:$Port/   (use 192.168.16.43 -- the other address is not routed to the office LAN)"
}
Write-Host '3. Trigger a real run from the browser and confirm it completes.'
Write-Host "4. Once this is confirmed working: .\03-uninstall-smoketest.ps1 (if not already done)."
