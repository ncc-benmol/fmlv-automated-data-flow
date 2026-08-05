<#
.SYNOPSIS
    Checks the smoke test service from a developer machine, not from the VM itself.

.DESCRIPTION
    Run this on YOUR machine, not on the VM. Answering from the VM's own localhost
    proves the service runs; answering from here proves it is reachable, which is the
    half of DESIGN.md open question 9 the smoke test exists to settle.

    Diagnoses the three failure modes separately, because they need different fixes:
    name doesn't resolve (DNS), host unreachable (network/routing), port closed
    (host firewall, network firewall, or the service isn't running).

.EXAMPLE
    .\check-from-local.ps1 -VmHost FMLVSRV01

.EXAMPLE
    .\check-from-local.ps1 -VmHost 10.20.30.40 -Port 8099
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $VmHost,
    [int]    $Port = 8099
)

$ErrorActionPreference = 'Continue'

Write-Host ''
Write-Host "=== Checking http://${VmHost}:$Port from $env:COMPUTERNAME ===" -ForegroundColor Cyan

Write-Host ''
Write-Host '1. DNS resolution ...' -NoNewline
try {
    $addresses = [Net.Dns]::GetHostAddresses($VmHost) | ForEach-Object { $_.IPAddressToString }
    Write-Host " OK -> $($addresses -join ', ')" -ForegroundColor Green
} catch {
    Write-Host ' FAILED' -ForegroundColor Red
    Write-Host "   $VmHost does not resolve. Try the IP address instead, or ask IT for the FQDN."
}

Write-Host '2. ICMP ping ...' -NoNewline
if (Test-Connection -ComputerName $VmHost -Count 2 -Quiet -ErrorAction SilentlyContinue) {
    Write-Host ' OK' -ForegroundColor Green
} else {
    # Not fatal on its own: plenty of hardened Windows Servers drop ICMP by default.
    Write-Host ' no reply (not necessarily a problem -- ICMP is often blocked)' -ForegroundColor Yellow
}

Write-Host "3. TCP $Port ..." -NoNewline
$tcp = Test-NetConnection -ComputerName $VmHost -Port $Port -WarningAction SilentlyContinue
if ($tcp.TcpTestSucceeded) {
    Write-Host ' OPEN' -ForegroundColor Green
} else {
    Write-Host ' CLOSED / filtered' -ForegroundColor Red
    Write-Host '   In order of likelihood:'
    Write-Host '     a. The service is not running   -> on the VM: Get-Service FMLVSmokeTest'
    Write-Host '     b. It bound to 127.0.0.1 only   -> it must bind 0.0.0.0'
    Write-Host '     c. Windows Firewall on the VM   -> 02-install-smoketest.ps1 adds the rule'
    Write-Host '     d. A network firewall in between -> this one is a request to IT'
    exit 1
}

Write-Host '4. HTTP GET /api/time ...' -NoNewline
try {
    $r = Invoke-RestMethod -Uri "http://${VmHost}:$Port/api/time" -TimeoutSec 10
    Write-Host ' OK' -ForegroundColor Green
    Write-Host ''
    $r | Format-List
    Write-Host ''
    Write-Host 'SUCCESS: the VM is serving, and this machine can reach it.' -ForegroundColor Green
    Write-Host "Answered by host '$($r.hostname)' running as '$($r.running_as)'."
    Write-Host "Browse it: http://${VmHost}:$Port/"
} catch {
    Write-Host ' FAILED' -ForegroundColor Red
    Write-Host "   The port is open but HTTP failed: $($_.Exception.Message)"
    exit 1
}
