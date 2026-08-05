<#
.SYNOPSIS
    Removes the FMLV deployment smoke test service and its firewall rule.

.DESCRIPTION
    Step 3 of the deployment smoke test (DESIGN.md 8.3). The smoke test has no business
    outliving the question it answers, so tearing it down is a checked-in script rather
    than a thing someone remembers to do.

    Leaves C:\fmlv\tools\nssm.exe and the uv cache in place -- the real deployment
    (TODO.md Phase 8b) wants both. Pass -RemoveRoot to delete them too.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\03-uninstall-smoketest.ps1
#>
[CmdletBinding()]
param(
    [string] $ServiceName = 'FMLVSmokeTest',
    [int]    $Port = 8099,
    [string] $RootDir = 'C:\fmlv',
    [switch] $RemoveRoot
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This script must be run from an elevated PowerShell (Run as Administrator).'
}

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    $nssmExe = Join-Path $RootDir 'tools\nssm.exe'
    if (Test-Path $nssmExe) {
        & $nssmExe stop $ServiceName confirm | Out-Null
        Start-Sleep -Seconds 2
        & $nssmExe remove $ServiceName confirm | Out-Null
    } else {
        # NSSM is gone but the service isn't -- fall back to the built-in tooling.
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        & sc.exe delete $ServiceName | Out-Null
    }
    Write-Host "Removed the '$ServiceName' service." -ForegroundColor Green
} else {
    Write-Host "No '$ServiceName' service found -- nothing to remove."
}

$ruleName = "$ServiceName (TCP $Port)"
$rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($rule) {
    Remove-NetFirewallRule -DisplayName $ruleName
    Write-Host "Removed the firewall rule '$ruleName'." -ForegroundColor Green
} else {
    Write-Host "No firewall rule '$ruleName' found."
}

if ($RemoveRoot) {
    if (Test-Path $RootDir) {
        Remove-Item $RootDir -Recurse -Force
        Write-Host "Deleted $RootDir (nssm, logs and the uv cache)." -ForegroundColor Green
    }
} else {
    Write-Host ''
    Write-Host "Left in place for the real deployment: $RootDir"
    Write-Host '  (nssm.exe, the uv cache, and the smoke test logs). Pass -RemoveRoot to delete.'
}
