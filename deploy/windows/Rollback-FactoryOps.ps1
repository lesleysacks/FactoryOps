#Requires -Version 5.1
<#
.SYNOPSIS
    Put a previous application snapshot back. Does not change the database unless asked.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Release,
    [string]$InstallRoot = 'C:\FactoryOps',
    [string]$Backup = '',
    [switch]$RestoreDatabase,
    [string]$ConfirmReplace = ''
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\FactoryOps.Common.ps1"
Assert-FactoryOpsWindows
if (-not (Test-Path $Release)) {
    throw "Release snapshot does not exist: $Release"
}
$layout = Get-FactoryOpsLayout -InstallRoot $InstallRoot
Stop-FactoryOpsServerTask -Layout $layout
Copy-FactoryOpsCode -Source $Release -Destination $layout.App
if ($RestoreDatabase) {
    if (-not $Backup) {
        throw 'Pass -Backup with the verified backup directory to restore the database.'
    }
    & "$PSScriptRoot\Restore-FactoryOps.ps1" -InstallRoot $layout.Root -Backup $Backup -Target $layout.Data -ReplaceLive -ConfirmReplace $ConfirmReplace
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& schtasks.exe /Run /TN 'FactoryOps Server' | Out-Null
Write-Host "Code restored from $Release. Database files were left in place unless -RestoreDatabase was confirmed."
