#Requires -Version 5.1
<#
.SYNOPSIS
    Remove FactoryOps startup tasks and stop the server. Does not delete data.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\FactoryOps'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
Stop-FactoryOpsServerTask -Layout $layout
foreach ($name in @('FactoryOps Server', 'FactoryOps Browser', 'FactoryOps Backup')) {
    & schtasks.exe /Delete /TN $name /F | Out-Null
}
Write-Host 'FactoryOps startup tasks are removed. Database, media, backups, and the environment file were not deleted.'
Write-Host "Data remains in $($layout.Data)"
