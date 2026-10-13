#Requires -Version 5.1
<#
.SYNOPSIS
  Remove the FactoryOps LAN firewall rule. Confirmation is required.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

Assert-FactoryOpsAdministrator

$existing = Get-NetFirewallRule -DisplayName $script:FactoryOpsFirewallName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host 'FactoryOps LAN firewall rule is not present.'
    exit 0
}
if (-not $PSCmdlet.ShouldProcess($script:FactoryOpsFirewallName, 'Remove the FactoryOps firewall rule')) {
    Write-Host 'Firewall rule left in place.'
    exit 1
}
Remove-NetFirewallRule -DisplayName $script:FactoryOpsFirewallName
Write-Host 'Removed FactoryOps LAN firewall rule.'
exit 0
