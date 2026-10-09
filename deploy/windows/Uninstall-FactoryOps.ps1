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
