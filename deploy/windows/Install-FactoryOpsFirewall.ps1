#Requires -Version 5.1
<#
.SYNOPSIS
  Allow inbound TCP to FactoryOps from the private factory subnet only.

.DESCRIPTION
  The rule is named "FactoryOps LAN". Profile is Private. RemoteAddress
  defaults to LocalSubnet. Public profiles and internet-wide ranges are refused.
#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [string]$RemoteAddress = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

Assert-FactoryOpsAdministrator

if ($Port -eq 0 -or -not $RemoteAddress) {
    $config = Read-FactoryOpsConfig
    if ($Port -eq 0) {
        $Port = [int]$config.port
    }
    if (-not $RemoteAddress) {
        $RemoteAddress = [string]$config.firewallRemoteAddress
    }
}

$refused = @('Any', '*', '0.0.0.0/0', '0.0.0.0-255.255.255.255', 'Internet')
if ($refused -contains $RemoteAddress) {
    throw 'Refusing a firewall rule that allows the public internet. Use LocalSubnet or a factory private range.'
}
if ($Port -lt 1 -or $Port -gt 65535) {
    throw 'Port must be between 1 and 65535.'
}

$existing = Get-NetFirewallRule -DisplayName $script:FactoryOpsFirewallName -ErrorAction SilentlyContinue
if (-not $existing) {
    New-NetFirewallRule `
        -DisplayName $script:FactoryOpsFirewallName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $Port `
        -Profile Private `
        -RemoteAddress $RemoteAddress | Out-Null
} else {
    Set-NetFirewallRule `
        -DisplayName $script:FactoryOpsFirewallName `
        -Enabled True `
        -Profile Private `
        -Action Allow `
        -Direction Inbound | Out-Null
    $existing | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $Port
    $existing | Set-NetFirewallAddressFilter -RemoteAddress $RemoteAddress
}

Write-Host ("Firewall rule '{0}' allows TCP {1} from {2} on the Private profile only." -f $script:FactoryOpsFirewallName, $Port, $RemoteAddress)
