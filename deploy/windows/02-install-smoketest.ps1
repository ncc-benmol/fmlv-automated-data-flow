<#
.SYNOPSIS
    Installs the FMLV deployment smoke test as an auto-starting Windows service.

.DESCRIPTION
    Step 2 of the deployment smoke test (DESIGN.md 8.3). Wraps the trivial FastAPI
    service in deploy\smoketest\smoke_service.py as a Windows service using NSSM, opens
    the port on the local Windows Firewall, starts it, and verifies it responds.

    Proves, in one go: uv runs on this host, a Python process can be registered as a
    service, and the service answers on the network. Reboot the VM afterwards to prove
    the fourth thing -- that it comes back on its own.

    Must be run from an ELEVATED PowerShell. Safe to re-run: an existing service of the
    same name is removed and reinstalled.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\02-install-smoketest.ps1

.EXAMPLE
    # Bind a different port, and run as a named account rather than LocalSystem
    .\02-install-smoketest.ps1 -Port 8100 -ServiceAccount 'NCC\svc_fmlv'
#>
[CmdletBinding()]
param(
    [string] $ServiceName = 'FMLVSmokeTest',
    [int]    $Port = 8099,

    # Where NSSM, the uv cache and the logs live. Deliberately outside the repo so a
    # `git clean` can't take the service's own state with it.
    [string] $RootDir = 'C:\fmlv',

    # Full path to uv.exe. Autodetected if omitted -- but note the service account may
    # not share your PATH, which is why the resolved path is baked into the service.
    [string] $UvPath,

    # Leave empty for LocalSystem. See TODO.md Phase 8b: LocalSystem is simplest but has
    # more privilege than this needs, and the real deployment should revisit it.
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
$serviceScript = Join-Path $repoRoot 'deploy\smoketest\smoke_service.py'
if (-not (Test-Path $serviceScript)) {
    throw "Could not find the smoke test script at $serviceScript"
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

Write-Section 'Configuration'
[PSCustomObject]@{
    ServiceName = $ServiceName
    Port        = $Port
    Script      = $serviceScript
    Uv          = $UvPath
    RootDir     = $RootDir
    Account     = if ($ServiceAccount) { $ServiceAccount } else { 'LocalSystem' }
} | Format-List

# --- Directories -------------------------------------------------------------------

$toolsDir = Join-Path $RootDir 'tools'
$logDir   = Join-Path $RootDir 'logs'
$cacheDir = Join-Path $RootDir 'uv-cache'
foreach ($dir in @($RootDir, $toolsDir, $logDir, $cacheDir)) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}

# --- NSSM --------------------------------------------------------------------------

Write-Section 'NSSM'
$nssmExe = Join-Path $toolsDir 'nssm.exe'
if (Test-Path $nssmExe) {
    Write-Host "Already present at $nssmExe" -ForegroundColor Green
} else {
    $zipPath = Join-Path $env:TEMP 'nssm-2.24.zip'
    $extractDir = Join-Path $env:TEMP 'nssm-extract'
    Write-Host 'Downloading NSSM 2.24 from https://nssm.cc/release/nssm-2.24.zip ...'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' `
                          -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    } catch {
        throw ("Could not download NSSM: {0}`n" -f $_.Exception.Message) +
              "If this VM has no outbound access, download nssm-2.24.zip on your own " +
              "machine, copy nssm.exe (win64) to $nssmExe, and re-run."
    }
    if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
    $arch = if ([Environment]::Is64BitOperatingSystem) { 'win64' } else { 'win32' }
    $src = Get-ChildItem -Path $extractDir -Recurse -Filter 'nssm.exe' |
           Where-Object { $_.FullName -like "*\$arch\*" } |
           Select-Object -First 1
    if (-not $src) { throw "nssm.exe ($arch) not found inside the downloaded archive." }
    Copy-Item $src.FullName $nssmExe -Force
    Remove-Item $zipPath, $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Installed to $nssmExe" -ForegroundColor Green
}

# --- Pre-warm the uv cache ----------------------------------------------------------

Write-Section 'Pre-warming the uv cache'
# The service account does not share your user profile, so point uv's cache and managed
# Python installs at a shared location and populate them *now*, as an interactive user
# with a visible error message, rather than on first service start where a failure would
# surface only as "the service started and then stopped".
$env:UV_CACHE_DIR = $cacheDir
$env:UV_PYTHON_INSTALL_DIR = Join-Path $RootDir 'python'
Write-Host 'Resolving the script dependencies (fastapi, uvicorn) ...'
& $UvPath run --script $serviceScript --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "uv could not prepare the smoke test environment (exit $LASTEXITCODE). Fix this before installing the service."
}
Write-Host 'Dependencies resolved.' -ForegroundColor Green

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

$appArgs = "run --script `"$serviceScript`" --host 0.0.0.0 --port $Port"
& $nssmExe install $ServiceName $UvPath $appArgs
if ($LASTEXITCODE -ne 0) { throw "nssm install failed (exit $LASTEXITCODE)." }

& $nssmExe set $ServiceName AppDirectory $repoRoot                       | Out-Null
& $nssmExe set $ServiceName DisplayName 'FMLV deployment smoke test'     | Out-Null
& $nssmExe set $ServiceName Description  'Trivial date/time service proving this host can run and serve a Python service (DESIGN.md 8.3).' | Out-Null
& $nssmExe set $ServiceName Start SERVICE_AUTO_START                     | Out-Null

# Logs are the only window into a service that fails at startup -- rotate them so they
# can be left on indefinitely.
& $nssmExe set $ServiceName AppStdout (Join-Path $logDir 'smoketest.out.log') | Out-Null
& $nssmExe set $ServiceName AppStderr (Join-Path $logDir 'smoketest.err.log') | Out-Null
& $nssmExe set $ServiceName AppRotateFiles 1        | Out-Null
& $nssmExe set $ServiceName AppRotateOnline 1       | Out-Null
& $nssmExe set $ServiceName AppRotateBytes 1048576  | Out-Null

# Without these the service account gets its own empty cache and re-downloads everything.
& $nssmExe set $ServiceName AppEnvironmentExtra `
    "UV_CACHE_DIR=$cacheDir" `
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
Write-Host 'Note: this only opens the *host* firewall. A network firewall between you and' -ForegroundColor Yellow
Write-Host 'the VM is a separate conversation with IT (DESIGN.md open question 9).' -ForegroundColor Yellow

# --- Start and verify ---------------------------------------------------------------

Write-Section 'Starting'
Start-Service -Name $ServiceName
$deadline = (Get-Date).AddSeconds(60)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 3
        if ($r.status -eq 'ok') { $healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $healthy) {
    Write-Host 'Service did not answer within 60 seconds.' -ForegroundColor Red
    Get-Service -Name $ServiceName | Format-List Name, Status, StartType
    Write-Host "Check the logs: $logDir\smoketest.err.log"
    throw 'Smoke test service failed to come up.'
}

Write-Host 'Service is up.' -ForegroundColor Green
Write-Host ''
Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/time" | Format-List

$ips = Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -ne '127.0.0.1' } |
       Select-Object -ExpandProperty IPAddress

Write-Section 'Next steps'
Write-Host "1. From THIS machine:  http://127.0.0.1:$Port/"
foreach ($ip in $ips) {
    Write-Host "2. From YOUR machine: http://${ip}:$Port/   (or use the hostname $env:COMPUTERNAME)"
}
Write-Host "   ...or run deploy\windows\check-from-local.ps1 -VmHost $env:COMPUTERNAME -Port $Port"
Write-Host '3. Reboot the VM and check it comes back on its own without logging in.'
Write-Host "4. When finished: .\03-uninstall-smoketest.ps1"
