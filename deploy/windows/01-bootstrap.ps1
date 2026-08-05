<#
.SYNOPSIS
    Prepares a bare Windows Server VM to run Python services with uv.

.DESCRIPTION
    Step 1 of the deployment smoke test (DESIGN.md 8.3). Inventories the box, installs
    uv if it isn't already there, and reports whether outbound internet works -- which
    is open question 9 and matters far more to this project than anything else here.

    Safe to re-run: every step checks before it acts.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\01-bootstrap.ps1
#>
[CmdletBinding()]
param(
    # Skip the uv install and only report on the machine.
    [switch] $InventoryOnly
)

$ErrorActionPreference = 'Stop'

function Write-Section($Text) {
    Write-Host ''
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Section 'Machine inventory'
$os = Get-CimInstance Win32_OperatingSystem
[PSCustomObject]@{
    Hostname       = $env:COMPUTERNAME
    OS             = $os.Caption
    Version        = $os.Version
    Architecture   = $os.OSArchitecture
    MemoryGB       = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    User           = "$env:USERDOMAIN\$env:USERNAME"
    IsAdmin        = Test-Admin
    PSVersion      = $PSVersionTable.PSVersion.ToString()
} | Format-List

Write-Host 'IP addresses (these are what you will browse to from your own machine):'
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -ne '127.0.0.1' } |
    Select-Object IPAddress, InterfaceAlias, PrefixLength |
    Format-Table -AutoSize

if (-not (Test-Admin)) {
    Write-Warning 'Not running as Administrator. Installing a service (step 02) will fail.'
}

Write-Section 'Outbound internet check (DESIGN.md open question 9)'
# A proxy or an outbound allowlist would affect fetching far more than anything else in
# the design, so find out now rather than while debugging a scraper.
$targets = @(
    @{ Name = 'PyPI';        Url = 'https://pypi.org/simple/' },
    @{ Name = 'astral.sh';   Url = 'https://astral.sh/uv/install.ps1' },
    @{ Name = 'GitHub';      Url = 'https://github.com' },
    @{ Name = 'NCC website'; Url = 'https://www.thencc.org.uk' }
)
foreach ($t in $targets) {
    try {
        $r = Invoke-WebRequest -Uri $t.Url -UseBasicParsing -TimeoutSec 15 -Method Head
        Write-Host ("  {0,-14} OK (HTTP {1})" -f $t.Name, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("  {0,-14} FAILED: {1}" -f $t.Name, $_.Exception.Message) -ForegroundColor Red
    }
}
if ($env:HTTP_PROXY -or $env:HTTPS_PROXY) {
    Write-Warning "Proxy environment variables are set: HTTP_PROXY=$env:HTTP_PROXY HTTPS_PROXY=$env:HTTPS_PROXY"
    Write-Warning 'Note this in TODO.md -- the service will need the same variables passed to it.'
}

if ($InventoryOnly) {
    Write-Section 'Inventory only -- stopping here'
    return
}

Write-Section 'uv'
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    Write-Host "Already installed at $($uv.Source)" -ForegroundColor Green
} else {
    Write-Host 'Installing uv from https://astral.sh/uv/install.ps1 ...'
    # The official installer puts uv in the *user* profile, which is deliberate: it means
    # this step needs no admin rights. Step 02 resolves the full path rather than relying
    # on PATH, because the service account will not share this profile.
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

    $candidate = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path (Join-Path $candidate 'uv.exe')) {
        $env:Path = "$candidate;$env:Path"
    }
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        throw 'uv was installed but is not on PATH. Open a new PowerShell window and re-run.'
    }
    Write-Host "Installed at $($uv.Source)" -ForegroundColor Green
}

& $uv.Source --version

Write-Section 'Python 3.14'
# uv manages its own Python builds, so nothing needs to be installed system-wide. The
# project pins 3.14 in .python-version; the smoke test itself only needs 3.11+.
& $uv.Source python install 3.14
& $uv.Source python list

Write-Section 'Done'
Write-Host 'Next: run 02-install-smoketest.ps1 from an *elevated* PowerShell.' -ForegroundColor Yellow
Write-Host "uv path (step 02 needs it if it can't autodetect): $($uv.Source)"
