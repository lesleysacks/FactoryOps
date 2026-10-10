#Requires -Version 5.1
<#
.SYNOPSIS
  Remove FactoryOps startup tasks, the firewall rule, and the kiosk shortcut.

.DESCRIPTION
  This does not delete the database, uploaded photos, logs, or .env.
  Confirmation is required.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'FactoryOps.Common.ps1')

Assert-FactoryOpsAdministrator

$config = $null
$configPath = Get-FactoryOpsConfigPath
if (Test-Path -LiteralPath $configPath) {
    $config = Read-FactoryOpsConfig
}

$target = 'FactoryOps scheduled tasks, firewall rule, and kiosk shortcut'
if (-not $PSCmdlet.ShouldProcess($target, 'Uninstall FactoryOps startup integration. This does not delete the database or media.')) {
    Write-Host 'Uninstall cancelled. Nothing was removed.'
    exit 1
}

& (Join-Path $PSScriptRoot 'Stop-FactoryOps.ps1')

foreach ($name in @($script:FactoryOpsServerTask, $script:FactoryOpsBackupTask)) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host ("Unregistered task {0}" -f $name)
    }
}

& (Join-Path $PSScriptRoot 'Remove-FactoryOpsFirewall.ps1') -Confirm:$false

if ($config -and $config.kioskStartupShortcut -and (Test-Path -LiteralPath ([string]$config.kioskStartupShortcut))) {
    Remove-Item -LiteralPath ([string]$config.kioskStartupShortcut) -Force
    Write-Host ("Removed kiosk shortcut {0}" -f $config.kioskStartupShortcut)
}

if ($config) {
    Write-Host ("Database left in place: {0}" -f $config.databasePath)
    Write-Host ("Media left in place: {0}" -f $config.mediaRoot)
    Write-Host ("Logs left in place: {0}" -f $config.logDir)
    Write-Host ("Backups left in place: {0}" -f $config.backupDir)
    Write-Host ("Config left in place: {0}" -f $configPath)
}
Write-Host 'Uninstall finished. The database was not deleted.'
exit 0
