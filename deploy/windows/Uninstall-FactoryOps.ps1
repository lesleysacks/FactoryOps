#Requires -Version 5.1
<#
.SYNOPSIS
    Disable FactoryOps and optionally remove program files. Keeps production data by default.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps',
    [switch]$RemoveProgram,
    [switch]$RemoveFirewall,
    [switch]$DeleteData,
    [string]$ConfirmDeleteData = ''
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
& "$PSScriptRoot\Disable-FactoryOps.ps1" -InstallRoot $layout.Root
if ($RemoveFirewall) {
    & netsh.exe advfirewall firewall delete rule name="FactoryOps LAN" | Out-Null
}
if ($RemoveProgram) {
    foreach ($dir in @($layout.App, (Join-Path $layout.Root 'venv'), $layout.Static, $layout.Releases)) {
        if (Test-Path $dir) {
            Remove-Item -Path $dir -Recurse -Force
        }
    }
    Write-Host 'Program files removed. Data, backups, logs, and config were kept.'
}
if ($DeleteData) {
    if ($ConfirmDeleteData -ne 'DELETE FACTORY DATA') {
        throw 'Refusing to delete production data. Re-run with -ConfirmDeleteData "DELETE FACTORY DATA" only if you intend to destroy the database, media, and backups.'
    }
    foreach ($dir in @($layout.Data, $layout.Backups, $layout.Logs, (Split-Path $layout.EnvFile))) {
        if (Test-Path $dir) {
            Remove-Item -Path $dir -Recurse -Force
        }
    }
    Write-Host 'Production data directories were deleted because confirmation was provided.'
} else {
    Write-Host "Production data is still at $($layout.Data)"
}
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
